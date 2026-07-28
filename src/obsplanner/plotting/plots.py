from __future__ import annotations

from collections.abc import Mapping, Sequence
from zoneinfo import ZoneInfo

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, MultipleLocator

from obsplanner.visibility import VisibilityConstraints, VisibilityResult

TIME_AXES = ("Local time", "UTC", "LST")


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


def _observation_summary(
    result: VisibilityResult, constraints: VisibilityConstraints
) -> str:
    return f"Moon separation ≥ {constraints.minimum_moon_separation:.0f}°"


def _combined_summary(
    results: Sequence[VisibilityResult], constraints: VisibilityConstraints
) -> str:
    return f"Moon separation ≥ {constraints.minimum_moon_separation:.0f}°"


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
            linewidth=0,
            label=label if category not in seen else None,
            zorder=0,
        )
        seen.add(category)


def plot_visibility(
    result: VisibilityResult,
    constraints: VisibilityConstraints,
    time_axis: str = "Local time",
    *,
    show_moon: bool = True,
) -> plt.Figure:
    """Plot one visibility curve with equivalent airmass and altitude scales."""
    elapsed_hours = np.asarray(
        (result.times - result.times[0]).to_value(u.hour), dtype=float
    )
    display_airmass = np.where(
        (result.airmass >= 1) & (result.airmass <= 3.0),
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
        (result.moon_altitude > 0) & (moon_curve >= 1) & (moon_curve <= 3.0),
        moon_curve,
        np.nan,
    )

    figure, airmass_axis = plt.subplots(
        figsize=(12.5, 4.8), constrained_layout=True
    )
    figure.get_layout_engine().set(h_pad=0.12, w_pad=0.08)
    altitude_axis = airmass_axis.secondary_yaxis(
        "right", functions=(airmass_to_altitude, altitude_to_airmass)
    )
    _shade_sky(airmass_axis, elapsed_hours, result.sun_altitude)

    visibility_line = airmass_axis.plot(
        elapsed_hours,
        target_clear_of_moon,
        color="#ff4b4b",
        linewidth=2.5,
        label=result.target.name,
        zorder=5,
    )[0]
    moon_limited_line = airmass_axis.plot(
        elapsed_hours,
        target_close_to_moon,
        color="#ff4b4b",
        linewidth=2.5,
        linestyle="--",
        label=(
            f"Moon separation < "
            f"{constraints.minimum_moon_separation:.0f}°"
        ),
        zorder=5,
    )[0]
    moon_line = None
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

    airmass_limit = airmass_axis.axhline(
        constraints.maximum_airmass,
        color="#ff8fa3",
        linestyle=":",
        linewidth=1.5,
        label="Airmass limit",
        zorder=3,
    )
    formatter, x_label = _time_axis_labeler(result, time_axis)
    airmass_axis.xaxis.set_major_locator(MultipleLocator(1))
    airmass_axis.xaxis.set_major_formatter(formatter)
    airmass_axis.set_xlabel(x_label)
    airmass_axis.set_xlim(elapsed_hours[0], elapsed_hours[-1])
    # Leave a small physical margin above airmass 1.0 so Streamlit's image
    # rendering cannot clip the upper tick or top spine.
    airmass_axis.set_ylim(3.0, 0.97)
    airmass_axis.set_ylabel("Airmass [sec(z)]", color="#d62728")
    airmass_axis.tick_params(axis="y", colors="#d62728")
    altitude_axis.set_ylabel("Altitude (degrees)", color="#9c6500")
    altitude_axis.tick_params(axis="y", colors="#9c6500")
    altitude_axis.set_yticks([20, 30, 45, 60, 90])

    airmass_axis.grid(color="white", linestyle=":", linewidth=0.9, alpha=0.7)
    airmass_axis.set_title(
        f"{result.observer.name} · {result.observing_date.isoformat()} · "
        f"Moon fraction {result.moon_illuminated_fraction:.0%}",
        pad=8,
    )
    airmass_axis.text(
        0.985,
        0.975,
        _observation_summary(result, constraints),
        transform=airmass_axis.transAxes,
        ha="right",
        va="top",
        fontsize=11.5,
        linespacing=1.35,
        color="#111111",
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": "white",
            "edgecolor": "#555555",
            "linewidth": 0.6,
            "alpha": 0.55,
        },
        zorder=10,
    )

    legend_handles = [visibility_line]
    if moon_line is not None:
        legend_handles.append(moon_line)
    legend_handles.append(airmass_limit)
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
    altitude_axis = airmass_axis.secondary_yaxis(
        "right", functions=(airmass_to_altitude, altitude_to_airmass)
    )
    _shade_sky(airmass_axis, elapsed_hours, reference.sun_altitude)

    legend_handles = []
    for result in results:
        color = colors.get(result.target.name, "#ff4b4b")
        display_airmass = np.where(
            (result.airmass >= 1) & (result.airmass <= 3.0),
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
            linewidth=2.5,
            label=result.target.name,
            zorder=5,
        )[0]
        airmass_axis.plot(
            elapsed_hours,
            np.where(~separation_passes, display_airmass, np.nan),
            color=color,
            linewidth=2.5,
            linestyle="--",
            label="_nolegend_",
            zorder=5,
        )
        legend_handles.append(solid_line)

    if show_moon:
        moon_curve = altitude_to_airmass(reference.moon_altitude)
        moon_curve = np.where(
            (reference.moon_altitude > 0)
            & (moon_curve >= 1)
            & (moon_curve <= 3.0),
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
        legend_handles.append(moon_line)

    airmass_limit = airmass_axis.axhline(
        constraints.maximum_airmass,
        color="#ff8fa3",
        linestyle=":",
        linewidth=1.5,
        label="Airmass limit",
        zorder=3,
    )
    legend_handles.append(airmass_limit)

    formatter, x_label = _time_axis_labeler(reference, time_axis)
    airmass_axis.xaxis.set_major_locator(MultipleLocator(1))
    airmass_axis.xaxis.set_major_formatter(formatter)
    airmass_axis.set_xlabel(x_label)
    airmass_axis.set_xlim(elapsed_hours[0], elapsed_hours[-1])
    airmass_axis.set_ylim(3.0, 0.97)
    airmass_axis.set_ylabel("Airmass [sec(z)]", color="#d62728")
    airmass_axis.tick_params(axis="y", colors="#d62728")
    altitude_axis.set_ylabel("Altitude (degrees)", color="#9c6500")
    altitude_axis.tick_params(axis="y", colors="#9c6500")
    altitude_axis.set_yticks([20, 30, 45, 60, 90])
    airmass_axis.grid(color="white", linestyle=":", linewidth=0.9, alpha=0.7)
    airmass_axis.set_title(
        f"{reference.observer.name} · {reference.observing_date.isoformat()} · "
        f"Moon fraction {reference.moon_illuminated_fraction:.0%}",
        pad=8,
    )
    airmass_axis.text(
        0.985,
        0.975,
        _combined_summary(results, constraints),
        transform=airmass_axis.transAxes,
        ha="right",
        va="top",
        fontsize=11.5,
        linespacing=1.35,
        color="#111111",
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": "white",
            "edgecolor": "#555555",
            "linewidth": 0.6,
            "alpha": 0.55,
        },
        zorder=10,
    )
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
