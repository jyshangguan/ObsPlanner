from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astroplan import FixedTarget, Observer, moon_illumination
from astropy.coordinates import AltAz, get_body, get_sun
from astropy.time import Time
from astropy.utils import iers

from obsplanner.targets import Target

from .constraints import VisibilityConstraints

# Offline-first: never hard-fail when bundled IERS predictions age past astropy's 30-day default; UT1-UTC age is irrelevant for visibility plotting.
iers.conf.auto_download = False
iers.conf.auto_max_age = None


@dataclass(frozen=True)
class ObservingWindow:
    start: Time
    end: Time

    @property
    def duration_hours(self) -> float:
        return float((self.end - self.start).to_value(u.hour))


@dataclass(frozen=True)
class VisibilityResult:
    target: Target
    observer: Observer
    observing_date: date
    times: Time
    altitude: np.ndarray
    azimuth: np.ndarray
    airmass: np.ndarray
    moon_altitude: np.ndarray
    moon_separation: np.ndarray
    moon_illuminated_fraction: float
    sun_altitude: np.ndarray
    observable: np.ndarray
    windows: tuple[ObservingWindow, ...]
    evening_twilight: Time | None
    morning_twilight: Time | None
    rise_time: Time | None
    transit_time: Time | None
    set_time: Time | None
    warning: str | None = None

    @property
    def best_window(self) -> ObservingWindow | None:
        return max(self.windows, key=lambda window: window.duration_hours, default=None)

    @property
    def maximum_altitude(self) -> float:
        return float(np.nanmax(self.altitude))

    @property
    def minimum_airmass(self) -> float:
        finite = self.airmass[np.isfinite(self.airmass)]
        return float(np.min(finite)) if finite.size else float("nan")


def observing_date_for_local_time(local_datetime: datetime) -> date:
    """Return the evening date for the observing night containing a local time."""
    return (local_datetime - timedelta(hours=12)).date()


def _safe_event(method, reference: Time, target: FixedTarget, which: str) -> Time | None:
    try:
        event = method(reference, target, which=which)
        if np.any(np.ma.getmaskarray(event.value)):
            return None
        return event
    except (ValueError, TypeError):
        return None


def _night_bounds(
    observer: Observer, observing_date: date
) -> tuple[Time, Time, Time | None, Time | None, str | None]:
    timezone = observer.timezone
    if isinstance(timezone, str):
        timezone = ZoneInfo(timezone)
    local_noon = datetime.combine(observing_date, time(12, 0), tzinfo=timezone)
    reference = Time(local_noon)

    warning = None
    evening = morning = None
    try:
        evening = observer.twilight_evening_astronomical(reference, which="next")
        morning = observer.twilight_morning_astronomical(evening, which="next")
        masked = bool(np.any(np.ma.getmaskarray(evening.value))) or bool(
            np.any(np.ma.getmaskarray(morning.value))
        )
        if masked or morning <= evening:
            raise ValueError("Astronomical twilight is not defined.")
    except (ValueError, TypeError):
        evening = morning = None
        warning = (
            "Astronomical twilight is not defined for this site and date. "
            "The Sun-altitude constraint still applies."
        )

    try:
        sunset = observer.sun_set_time(reference, which="next")
        sunrise = observer.sun_rise_time(sunset, which="next")
        masked = bool(np.any(np.ma.getmaskarray(sunset.value))) or bool(
            np.any(np.ma.getmaskarray(sunrise.value))
        )
        if masked or sunrise <= sunset:
            raise ValueError("Sunset or sunrise is not defined.")
        # Include a little daylight so all twilight stages are visible.
        return (
            sunset - 30 * u.minute,
            sunrise + 30 * u.minute,
            evening,
            morning,
            warning,
        )
    except (ValueError, TypeError):
        start = Time(local_noon + timedelta(hours=6))
        end = Time(local_noon + timedelta(hours=18))
        warning = (
            "Sunset or sunrise is not defined for this site and date. "
            "Using 18:00–06:00 local time; Sun altitude is still shown and applied."
        )
        return start, end, evening, morning, warning


def _full_day_bounds(
    observer: Observer, observing_date: date
) -> tuple[Time, Time, Time | None, Time | None, str | None]:
    """Return the 24 hours from local noon that contain an observing night."""
    timezone = observer.timezone
    if isinstance(timezone, str):
        timezone = ZoneInfo(timezone)
    local_noon = datetime.combine(observing_date, time(12, 0), tzinfo=timezone)
    start = Time(local_noon)
    end = start + 24 * u.hour

    evening = morning = None
    warning = None
    try:
        evening = observer.twilight_evening_astronomical(start, which="next")
        morning = observer.twilight_morning_astronomical(evening, which="next")
        masked = bool(np.any(np.ma.getmaskarray(evening.value))) or bool(
            np.any(np.ma.getmaskarray(morning.value))
        )
        if masked or morning <= evening:
            raise ValueError("Astronomical twilight is not defined.")
    except (ValueError, TypeError):
        evening = morning = None
        warning = (
            "Astronomical twilight is not defined for this site and date. "
            "The Sun-altitude constraint still applies."
        )
    return start, end, evening, morning, warning


def find_observing_windows(
    times: Time, observable: np.ndarray
) -> tuple[ObservingWindow, ...]:
    """Convert a boolean sample mask into contiguous observing windows."""
    mask = np.asarray(observable, dtype=bool)
    if mask.size == 0 or not np.any(mask):
        return ()
    changes = np.diff(np.pad(mask.astype(int), (1, 1)))
    starts = np.flatnonzero(changes == 1)
    stops = np.flatnonzero(changes == -1) - 1
    return tuple(
        ObservingWindow(start=times[start], end=times[stop])
        for start, stop in zip(starts, stops)
    )


def calculate_visibility(
    target: Target,
    observer: Observer,
    observing_date: date,
    constraints: VisibilityConstraints | None = None,
    cadence_minutes: int = 5,
    show_daytime: bool = False,
) -> VisibilityResult:
    """Calculate visibility for a local observing night or its full 24-hour day."""
    constraints = constraints or VisibilityConstraints()
    if cadence_minutes <= 0:
        raise ValueError("Cadence must be positive.")

    bounds = _full_day_bounds if show_daytime else _night_bounds
    start, end, evening, morning, warning = bounds(observer, observing_date)
    duration_minutes = float((end - start).to_value(u.minute))
    offsets = np.arange(0, duration_minutes + cadence_minutes, cadence_minutes)
    offsets = offsets[offsets <= duration_minutes + 1e-8]
    times = start + offsets * u.minute

    frame = AltAz(obstime=times, location=observer.location)
    altaz = target.coord.transform_to(frame)
    altitude = np.asarray(altaz.alt.to_value(u.deg), dtype=float)
    azimuth = np.asarray(altaz.az.to_value(u.deg), dtype=float)

    raw_airmass = np.asarray(altaz.secz.value, dtype=float)
    airmass = np.where((altitude > 0) & np.isfinite(raw_airmass), raw_airmass, np.nan)

    moon = get_body("moon", times, observer.location).transform_to(frame)
    moon_altitude = np.asarray(moon.alt.to_value(u.deg), dtype=float)
    moon_separation = np.asarray(altaz.separation(moon).to_value(u.deg))
    moon_fraction = float(moon_illumination(times[len(times) // 2]))
    sun_altitude = np.asarray(
        get_sun(times).transform_to(frame).alt.to_value(u.deg), dtype=float
    )

    observable = (
        (altitude >= constraints.minimum_altitude)
        & np.isfinite(airmass)
        & (airmass <= constraints.maximum_airmass)
        & (moon_separation >= constraints.minimum_moon_separation)
        & (sun_altitude <= -18.0)
    )
    windows = find_observing_windows(times, observable)

    fixed_target = FixedTarget(coord=target.coord, name=target.name)
    reference = times[len(times) // 2]
    rise = _safe_event(observer.target_rise_time, reference, fixed_target, "nearest")
    transit = _safe_event(
        observer.target_meridian_transit_time, reference, fixed_target, "nearest"
    )
    set_time = _safe_event(observer.target_set_time, reference, fixed_target, "nearest")

    return VisibilityResult(
        target=target,
        observer=observer,
        observing_date=observing_date,
        times=times,
        altitude=altitude,
        azimuth=azimuth,
        airmass=airmass,
        moon_altitude=moon_altitude,
        moon_separation=moon_separation,
        moon_illuminated_fraction=moon_fraction,
        sun_altitude=sun_altitude,
        observable=observable,
        windows=windows,
        evening_twilight=evening,
        morning_twilight=morning,
        rise_time=rise,
        transit_time=transit,
        set_time=set_time,
        warning=warning,
    )
