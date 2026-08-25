from __future__ import annotations

from collections.abc import Mapping, Sequence
from zoneinfo import ZoneInfo

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import AltAz, get_body, get_sun
from astropy.time import Time
from matplotlib.ticker import FuncFormatter, MultipleLocator

from obsplanner.targets import Target


SELECTED_TARGET_COLOR = "#ffea00"
from obsplanner.visibility import VisibilityConstraints, VisibilityResult

TIME_AXES = ("Local time", "UTC", "LST")


def plot_sky(
    targets: Sequence[Target],
    observer,
    observation_time: Time,
    *,
    colors: Mapping[str, str],
    show_moon: bool = True,
    selected: str | None = None,
) -> plt.Figure:
    """Plot target positions in the local sky at one instant.

    When ``selected`` names one of the targets, that target is drawn on top
    of every other marker with an enlarged bold label framed by a
    dark framed label. Its marker and label use the same bright yellow as the
    selected observability curve, regardless of its assigned target color.
    """
    figure = plt.figure(figsize=(5.2, 5.2), constrained_layout=True)
    sky_axis = figure.add_subplot(111, projection="polar")
    observation_time = Time(observation_time)
    frame = AltAz(obstime=observation_time, location=observer.location)

    horizon_radius = 1.0
    outer_radius = np.sqrt(2.0)
    sky_axis.set_theta_zero_location("N")
    # Astronomical sky charts are viewed from inside the celestial sphere:
    # east is on the left and west is on the right.
    sky_axis.set_theta_direction(1)
    sky_axis.set_ylim(0, outer_radius)
    sky_axis.axhspan(
        horizon_radius,
        outer_radius,
        color="#d9d9d9",
        alpha=0.45,
        zorder=0,
    )
    sky_axis.axhline(horizon_radius, color="#555555", linewidth=1.2, zorder=1)

    # Draw the selected target last so it sits on top of the other markers.
    ordered_targets = sorted(
        targets, key=lambda candidate: candidate.name == selected
    )
    for target in ordered_targets:
        is_selected = selected is not None and target.name == selected
        altaz = target.coord.transform_to(frame)
        azimuth = altaz.az.radian
        altitude = altaz.alt.to_value(u.deg)
        # Lambert azimuthal equal-area radius. The horizon is r=1; the shaded
        # outer annulus contains targets currently below the horizon.
        radius = np.sqrt(2.0) * np.sin(np.radians(90.0 - altitude) / 2.0)
        color = (
            SELECTED_TARGET_COLOR
            if is_selected
            else colors.get(target.name, "#ff4b4b")
        )
        sky_axis.scatter(
            azimuth,
            radius,
            s=70 if is_selected else 30,
            color=color,
            edgecolor="#333333" if is_selected else "white",
            linewidth=1.2 if is_selected else 0.7,
            zorder=6 if is_selected else 3,
        )
        if is_selected:
            sky_axis.annotate(
                target.name,
                (azimuth, radius),
                xytext=(7, 5),
                textcoords="offset points",
                color=color,
                fontsize=14,
                ha="left",
                va="bottom",
                annotation_clip=False,
                fontweight="bold",
                zorder=7,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=(0.1, 0.1, 0.1, 0.75),
                    edgecolor=SELECTED_TARGET_COLOR,
                ),
            )

    if show_moon:
        moon = get_body("moon", observation_time, observer.location).transform_to(
            frame
        )
        moon_azimuth = moon.az.radian
        moon_altitude = moon.alt.to_value(u.deg)
        moon_radius = np.sqrt(2.0) * np.sin(
            np.radians(90.0 - moon_altitude) / 2.0
        )
        moon_color = "#d4a900"
        sky_axis.scatter(
            moon_azimuth,
            moon_radius,
            s=95,
            color=moon_color,
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        sky_axis.annotate(
            "Moon",
            (moon_azimuth, moon_radius),
            xytext=(7, 5),
            textcoords="offset points",
            color=moon_color,
            fontsize=14,
            ha="left",
            va="bottom",
            annotation_clip=False,
            zorder=4,
        )
        sun = get_sun(observation_time).transform_to(frame)
        sun_azimuth = sun.az.radian
        sun_altitude = sun.alt.to_value(u.deg)
        sun_radius = np.sqrt(2.0) * np.sin(
            np.radians(90.0 - sun_altitude) / 2.0
        )
        sun_color = "#d62728"
        sky_axis.scatter(
            sun_azimuth,
            sun_radius,
            s=95,
            color=sun_color,
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        sky_axis.annotate(
            "Sun",
            (sun_azimuth, sun_radius),
            xytext=(7, 5),
            textcoords="offset points",
            color=sun_color,
            fontsize=14,
            ha="left",
            va="bottom",
            annotation_clip=False,
            zorder=4,
        )

    altitude_ticks = np.array([60, 30, 0, -30, -60])
    radial_ticks = np.sqrt(2.0) * np.sin(
        np.radians(90.0 - altitude_ticks) / 2.0
    )
    sky_axis.set_yticks(radial_ticks)
    sky_axis.set_yticklabels([f"{value}°" for value in altitude_ticks])
    sky_axis.set_rlabel_position(225)
    sky_axis.set_thetagrids(
        [0, 45, 90, 135, 180, 225, 270, 315],
        ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    )
    timezone = observer.timezone
    local_time = observation_time.to_datetime(timezone=timezone)
    sky_axis.set_title(
        f"Sky plot\n{observer.name} · "
        f"{local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        fontsize=11,
        pad=12,
    )
    sky_axis.grid(color="#8a8a8a", linestyle=":", linewidth=0.8, alpha=0.65)
    return figure


def airmass_to_altitude(airmass):
    """Convert geometric airmass sec(z) to altitude in degrees."""
    values = np.asarray(airmass, dtype=float)
    return np.degrees(np.arcsin(np.clip(1.0 / values, -1.0, 1.0)))


def altitude_to_airmass(altitude):
    """Convert altitude in degrees to geometric airmass sec(z)."""
    sine_altitude = np.sin(np.radians(np.asarray(altitude, dtype=float)))
    return np.divide(
        1.0,
        sine_altitude,
        out=np.full_like(sine_altitude, np.inf),
        where=np.abs(sine_altitude) > 1e-12,
    )


def _time_axis_labeler(result: VisibilityResult, mode: str):
    if mode not in TIME_AXES:
        raise ValueError(f"Time-axis mode must be one of: {', '.join(TIME_AXES)}.")

    timezone = result.observer.timezone
    if isinstance(timezone, str):
        timezone = ZoneInfo(timezone)

    def label(elapsed_hours: float, _position: int) -> str:
        sample_time = result.times[0] + elapsed_hours * u.hour
        if mode == "LST":
            sidereal = result.observer.local_sidereal_time(
                sample_time, kind="apparent"
            )
            return sidereal.to_string(
                unit=u.hour, sep=":", fields=2, precision=0, pad=True
            )
        display_timezone = ZoneInfo("UTC") if mode == "UTC" else timezone
        return sample_time.to_datetime(timezone=display_timezone).strftime("%H:%M")

    if mode == "LST":
        axis_label = "Local sidereal time (apparent)"
    elif mode == "UTC":
        axis_label = "UTC"
    else:
        axis_label = f"Local time ({getattr(timezone, 'key', timezone)})"
    return FuncFormatter(label), axis_label


def _shade_sky(ax, elapsed_hours: np.ndarray, sun_altitude: np.ndarray) -> None:
    """Shade daylight, twilight stages, and astronomical night."""
    stages = (
        ("#fff3b0", "Day"),
        ("#b8eef2", "Civil twilight"),
        ("#36c5e8", "Nautical twilight"),
        ("#3155d9", "Astronomical twilight"),
        ("#101066", "Astronomical night"),
    )
    categories = np.select(
        [
            sun_altitude > 0,
            sun_altitude > -6,
            sun_altitude > -12,
            sun_altitude > -18,
        ],
        [0, 1, 2, 3],
        default=4,
    )
    edges = np.empty(len(elapsed_hours) + 1)
    edges[0], edges[-1] = elapsed_hours[0], elapsed_hours[-1]
    edges[1:-1] = (elapsed_hours[:-1] + elapsed_hours[1:]) / 2
    run_starts = np.r_[0, np.flatnonzero(np.diff(categories)) + 1]
    run_stops = np.r_[run_starts[1:], len(categories)]
    seen: set[int] = set()
    for start, stop in zip(run_starts, run_stops):
        category = int(categories[start])
        color, label = stages[category]
        ax.axvspan(
            edges[start],
            edges[stop],
            color=color,
            alpha=0.5,
            linewidth=0,
            label=label if category not in seen else None,
            zorder=0,
        )
        seen.add(category)


def _add_current_time_marker(
    ax,
    result: VisibilityResult,
    current_time: Time | None,
):
    """Draw the current time when it falls inside the plotted observing night."""
    if current_time is None:
        return None
    current_time = Time(current_time)
    if current_time < result.times[0] or current_time > result.times[-1]:
        return None
    elapsed_hours = float((current_time - result.times[0]).to_value(u.hour))
    return ax.axvline(
        elapsed_hours,
        color="#d62728",
        linewidth=2.0,
        linestyle="--",
        label="Current time",
        zorder=8,
    )


def plot_visibility(
    result: VisibilityResult,
    constraints: VisibilityConstraints,
    time_axis: str = "Local time",
    *,
    color: str = "#ff4b4b",
    show_moon: bool = True,
    current_time: Time | None = None,
    show_legend: bool = True,
    target_index: int = 0,
) -> plt.Figure:
    """Plot one visibility curve with equivalent airmass and altitude scales.

    ``target_index`` identifies the target in the curve group ids so several
    separate panels can be told apart by the interactive legend.
    """
    elapsed_hours = np.asarray(
        (result.times - result.times[0]).to_value(u.hour), dtype=float
    )
    display_airmass = np.where(
        (result.airmass >= 1)
        & (result.airmass <= constraints.maximum_airmass),
        result.airmass,
        np.nan,
    )
    moon_separation_passes = (
        result.moon_separation >= constraints.minimum_moon_separation
    )
    target_clear_of_moon = np.where(
        moon_separation_passes, display_airmass, np.nan
    )
    target_close_to_moon = np.where(
        ~moon_separation_passes, display_airmass, np.nan
    )
    moon_curve = altitude_to_airmass(result.moon_altitude)
    moon_curve = np.where(
        (result.moon_altitude > 0)
        & (moon_curve >= 1)
        & (moon_curve <= constraints.maximum_airmass),
        moon_curve,
        np.nan,
    )
    sun_curve = altitude_to_airmass(result.sun_altitude)
    sun_curve = np.where(
        (result.sun_altitude > 0)
        & (sun_curve >= 1)
        & (sun_curve <= constraints.maximum_airmass),
        sun_curve,
        np.nan,
    )
    figure, airmass_axis = plt.subplots(
        figsize=(12.5, 4.8), constrained_layout=True
    )
    figure.get_layout_engine().set(h_pad=0.12, w_pad=0.08)
    _shade_sky(airmass_axis, elapsed_hours, result.sun_altitude)

    visibility_line = airmass_axis.plot(
        elapsed_hours,
        target_clear_of_moon,
        color=color,
        alpha=1.0,
        linewidth=1.0,
        label=result.target.name,
        zorder=5,
    )[0]
    visibility_line.set_gid(f"obs-target-{target_index}-solid")
    moon_limited_line = airmass_axis.plot(
        elapsed_hours,
        target_close_to_moon,
        color=color,
        alpha=1.0,
        linewidth=1.0,
        linestyle="--",
        label=(
            f"Moon separation < "
            f"{constraints.minimum_moon_separation:.0f}°"
        ),
        zorder=5,
    )[0]
    moon_limited_line.set_gid(f"obs-target-{target_index}-dashed")
    moon_line = None
    sun_line = None
    if show_moon:
        moon_line = airmass_axis.plot(
            elapsed_hours,
            moon_curve,
            color="#fff2a8",
            linewidth=2.0,
            linestyle="--",
            label="Moon altitude",
            zorder=4,
        )[0]
        moon_line.set_gid("obs-body-moon-solid")
        sun_line = airmass_axis.plot(
            elapsed_hours,
            sun_curve,
            color="#d62728",
            linewidth=3.0,
            linestyle="--",
            label="Sun altitude",
            zorder=4,
        )[0]
        sun_line.set_gid("obs-body-sun-solid")

    current_time_line = _add_current_time_marker(
        airmass_axis, result, current_time
    )
    formatter, x_label = _time_axis_labeler(result, time_axis)
    tick_interval = 2 if elapsed_hours[-1] - elapsed_hours[0] > 16 else 1
    airmass_axis.xaxis.set_major_locator(MultipleLocator(tick_interval))
    airmass_axis.xaxis.set_major_formatter(formatter)
    airmass_axis.set_xlabel(x_label, fontsize=12)
    airmass_axis.set_xlim(elapsed_hours[0], elapsed_hours[-1])
    # Leave a small physical margin above airmass 1.0 so Streamlit's image
    # rendering cannot clip the upper tick or top spine.
    airmass_axis.set_ylim(constraints.maximum_airmass, 0.97)
    airmass_axis.set_ylabel(
        "Airmass [sec(z)]", color="#d62728", fontsize=12
    )
    airmass_axis.tick_params(axis="y", colors="#d62728")
    airmass_axis.grid(color="white", linestyle=":", linewidth=0.9, alpha=0.7)
    airmass_axis.set_title(
        f"{result.observer.name} · {result.observing_date.isoformat()} · "
        f"Moon fraction {result.moon_illuminated_fraction:.0%} · "
        f"Moon separation ≥ {constraints.minimum_moon_separation:.0f}°",
        pad=8,
        fontsize=14,
    )

    legend_handles = [visibility_line]
    if moon_line is not None:
        legend_handles.append(moon_line)
    if sun_line is not None:
        legend_handles.append(sun_line)
    if current_time_line is not None:
        legend_handles.append(current_time_line)
    if show_legend:
        airmass_axis.legend(
            handles=legend_handles,
            loc="center left",
            bbox_to_anchor=(1.06, 0.5),
            ncols=1,
            fontsize=12.3,
            framealpha=0.85,
            borderaxespad=0.5,
        )
    return figure


def plot_combined_visibility(
    results: Sequence[VisibilityResult],
    constraints: VisibilityConstraints,
    time_axis: str = "Local time",
    *,
    colors: Mapping[str, str],
    show_moon: bool = True,
    current_time: Time | None = None,
    show_legend: bool = True,
    include_targets: bool = True,
) -> plt.Figure:
    """Plot several targets together with user-selected colors."""
    if not results:
        raise ValueError("At least one visibility result is required.")
    reference = results[0]
    for result in results[1:]:
        if len(result.times) != len(reference.times) or not np.allclose(
            result.times.jd, reference.times.jd
        ):
            raise ValueError("Combined targets must use the same observing night.")

    elapsed_hours = np.asarray(
        (reference.times - reference.times[0]).to_value(u.hour), dtype=float
    )
    figure, airmass_axis = plt.subplots(
        figsize=(12.5, 4.8), constrained_layout=True
    )
    figure.get_layout_engine().set(h_pad=0.12, w_pad=0.08)
    _shade_sky(airmass_axis, elapsed_hours, reference.sun_altitude)

    legend_handles = []
    plotted_results = results if include_targets else ()
    for target_index, result in enumerate(plotted_results):
        color = colors.get(result.target.name, "#ff4b4b")
        display_airmass = np.where(
            (result.airmass >= 1)
            & (result.airmass <= constraints.maximum_airmass),
            result.airmass,
            np.nan,
        )
        separation_passes = (
            result.moon_separation >= constraints.minimum_moon_separation
        )
        solid_line = airmass_axis.plot(
            elapsed_hours,
            np.where(separation_passes, display_airmass, np.nan),
            color=color,
            alpha=1.0,
            linewidth=1.0,
            label=result.target.name,
            zorder=5,
        )[0]
        solid_line.set_gid(f"obs-target-{target_index}-solid")
        dashed_line = airmass_axis.plot(
            elapsed_hours,
            np.where(~separation_passes, display_airmass, np.nan),
            color=color,
            alpha=1.0,
            linewidth=1.0,
            linestyle="--",
            label="_nolegend_",
            zorder=5,
        )[0]
        dashed_line.set_gid(f"obs-target-{target_index}-dashed")
        legend_handles.append(solid_line)

    if show_moon:
        moon_curve = altitude_to_airmass(reference.moon_altitude)
        moon_curve = np.where(
            (reference.moon_altitude > 0)
            & (moon_curve >= 1)
            & (moon_curve <= constraints.maximum_airmass),
            moon_curve,
            np.nan,
        )
        moon_line = airmass_axis.plot(
            elapsed_hours,
            moon_curve,
            color="#fff2a8",
            linewidth=2.0,
            linestyle="--",
            label="Moon altitude",
            zorder=4,
        )[0]
        moon_line.set_gid("obs-body-moon-solid")
        legend_handles.append(moon_line)
        sun_curve = altitude_to_airmass(reference.sun_altitude)
        sun_curve = np.where(
            (reference.sun_altitude > 0)
            & (sun_curve >= 1)
            & (sun_curve <= constraints.maximum_airmass),
            sun_curve,
            np.nan,
        )
        sun_line = airmass_axis.plot(
            elapsed_hours,
            sun_curve,
            color="#d62728",
            linewidth=3.0,
            linestyle="--",
            label="Sun altitude",
            zorder=4,
        )[0]
        sun_line.set_gid("obs-body-sun-solid")
        legend_handles.append(sun_line)

    current_time_line = _add_current_time_marker(
        airmass_axis, reference, current_time
    )
    if current_time_line is not None:
        legend_handles.append(current_time_line)

    formatter, x_label = _time_axis_labeler(reference, time_axis)
    tick_interval = 2 if elapsed_hours[-1] - elapsed_hours[0] > 16 else 1
    airmass_axis.xaxis.set_major_locator(MultipleLocator(tick_interval))
    airmass_axis.xaxis.set_major_formatter(formatter)
    airmass_axis.set_xlabel(x_label, fontsize=12)
    airmass_axis.set_xlim(elapsed_hours[0], elapsed_hours[-1])
    airmass_axis.set_ylim(constraints.maximum_airmass, 0.97)
    airmass_axis.set_ylabel(
        "Airmass [sec(z)]", color="#d62728", fontsize=12
    )
    airmass_axis.tick_params(axis="y", colors="#d62728")
    airmass_axis.grid(color="white", linestyle=":", linewidth=0.9, alpha=0.7)
    airmass_axis.set_title(
        f"{reference.observer.name} · {reference.observing_date.isoformat()} · "
        f"Moon fraction {reference.moon_illuminated_fraction:.0%} · "
        f"Moon separation ≥ {constraints.minimum_moon_separation:.0f}°",
        pad=8,
        fontsize=14,
    )
    if show_legend:
        airmass_axis.legend(
            handles=legend_handles,
            loc="center left",
            bbox_to_anchor=(1.06, 0.5),
            ncols=1,
            fontsize=12.3,
            framealpha=0.85,
            borderaxespad=0.5,
        )
    return figure
