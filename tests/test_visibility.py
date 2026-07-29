from datetime import date

import numpy as np
import pytest
from astropy.time import Time

from obsplanner.observatories import load_observatories
from obsplanner.plotting import (
    airmass_to_altitude,
    altitude_to_airmass,
    plot_combined_visibility,
    plot_visibility,
)
from obsplanner.targets import parse_manual_coordinates
from obsplanner.visibility import (
    VisibilityConstraints,
    calculate_visibility,
    find_observing_windows,
)


def test_find_observing_windows():
    times = Time(
        [
            "2026-08-01T00:00:00",
            "2026-08-01T00:05:00",
            "2026-08-01T00:10:00",
            "2026-08-01T00:15:00",
            "2026-08-01T00:20:00",
        ]
    )
    windows = find_observing_windows(
        times, np.array([False, True, True, False, True])
    )
    assert len(windows) == 2
    assert windows[0].duration_hours == pytest.approx(5 / 60)
    assert windows[1].duration_hours == 0


def test_visibility_result_shapes_and_constraints():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints(30, 2, 30)
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=10
    )

    size = len(result.times)
    assert size > 20
    assert result.altitude.shape == (size,)
    assert result.airmass.shape == (size,)
    assert result.moon_altitude.shape == (size,)
    assert result.moon_separation.shape == (size,)
    assert 0 <= result.moon_illuminated_fraction <= 1
    assert result.observable.shape == (size,)
    assert np.all(result.altitude[result.observable] >= 30)
    assert np.all(result.airmass[result.observable] <= 2)
    assert np.all(result.moon_separation[result.observable] >= 30)
    assert np.all(result.sun_altitude[result.observable] <= -18)


def test_show_daytime_uses_a_full_24_hour_observing_day():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    result = calculate_visibility(
        target,
        observer,
        date(2026, 3, 15),
        cadence_minutes=30,
        show_daytime=True,
    )

    duration = float((result.times[-1] - result.times[0]).to_value("hour"))
    local_start = result.times[0].to_datetime(timezone=observer.timezone)
    assert duration == pytest.approx(24)
    assert local_start.hour == 12
    assert len(result.times) == 49
    assert np.any(result.sun_altitude > 0)
    assert np.any(result.sun_altitude <= -18)


def test_night_only_remains_the_default():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    result = calculate_visibility(
        target,
        observer,
        date(2026, 3, 15),
        cadence_minutes=30,
    )

    duration = float((result.times[-1] - result.times[0]).to_value("hour"))
    assert duration < 24


def test_strict_altitude_can_remove_all_windows():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["palomar"].to_observer()
    result = calculate_visibility(
        target,
        observer,
        date(2026, 3, 15),
        VisibilityConstraints(minimum_altitude=80),
        cadence_minutes=15,
    )
    assert not result.observable.any()
    assert result.windows == ()


@pytest.mark.parametrize(
    ("time_axis", "expected_label"),
    [
        ("Local time", "America/Santiago"),
        ("UTC", "UTC"),
        ("LST", "sidereal"),
    ],
)
def test_combined_plot_time_axes(time_axis, expected_label):
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=30
    )

    figure = plot_visibility(result, constraints, time_axis)
    assert len(figure.axes) == 1
    assert figure.axes[0].get_ylabel() == "Airmass [sec(z)]"
    assert figure.axes[0].child_axes[0].get_ylabel() == "Altitude (degrees)"
    assert expected_label in figure.axes[0].get_xlabel()
    labels = [line.get_label() for line in figure.axes[0].get_lines()]
    assert "Moon altitude" in labels
    moon_line = next(
        line
        for line in figure.axes[0].get_lines()
        if line.get_label() == "Moon altitude"
    )
    assert moon_line.get_linestyle() == "--"
    assert any(
        "Moon separation ≥ 30°" in text.get_text()
        for text in figure.axes[0].texts
    )
    summary = "\n".join(text.get_text() for text in figure.axes[0].texts)
    assert "ICRS" not in summary
    assert "Rise" not in summary
    assert "Transit" not in summary
    assert "Set" not in summary
    assert "Maximum altitude" not in summary
    assert "Minimum airmass" not in summary
    assert figure.axes[0].texts[0].get_fontsize() == pytest.approx(11.5)
    assert "Moon fraction" in figure.axes[0].get_title()
    assert "2026-03-15" in figure.axes[0].get_title()
    assert "Paranal Observatory" in figure.axes[0].get_title()
    legend_labels = [
        text.get_text() for text in figure.axes[0].get_legend().get_texts()
    ]
    assert legend_labels == [
        "NGC 3783",
        "Moon altitude",
        "Airmass limit",
    ]
    assert all(
        text.get_fontsize() == pytest.approx(12.3)
        for text in figure.axes[0].get_legend().get_texts()
    )


def test_moon_curve_can_be_hidden():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=30
    )

    figure = plot_visibility(
        result, constraints, "Local time", show_moon=False
    )
    line_labels = [line.get_label() for line in figure.axes[0].get_lines()]
    legend_labels = [
        text.get_text() for text in figure.axes[0].get_legend().get_texts()
    ]
    assert "Moon altitude" not in line_labels
    assert "Moon altitude" not in legend_labels
    assert "Moon separation < 30°" not in legend_labels


def test_current_time_marker_is_drawn_inside_single_target_night():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=30
    )
    current_time = result.times[len(result.times) // 2]

    figure = plot_visibility(
        result,
        constraints,
        "Local time",
        current_time=current_time,
    )

    current_line = next(
        line
        for line in figure.axes[0].get_lines()
        if line.get_label() == "Current time"
    )
    expected_hours = float((current_time - result.times[0]).to_value("hour"))
    assert current_line.get_xdata()[0] == pytest.approx(expected_hours)
    assert current_line.get_color() == "#00cfe8"
    assert current_line.get_linewidth() == pytest.approx(0.8)
    assert current_line.get_linestyle() == "--"


def test_current_time_marker_works_in_combined_plot_and_hides_outside_night():
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=30
    )
    colors = {"NGC 3783": "#123456"}
    inside = result.times[len(result.times) // 2]

    visible_figure = plot_combined_visibility(
        [result],
        constraints,
        colors=colors,
        current_time=inside,
    )
    visible_labels = [
        line.get_label() for line in visible_figure.axes[0].get_lines()
    ]
    assert "Current time" in visible_labels

    hidden_figure = plot_combined_visibility(
        [result],
        constraints,
        colors=colors,
        current_time=Time("2026-03-17T00:00:00"),
    )
    hidden_labels = [
        line.get_label() for line in hidden_figure.axes[0].get_lines()
    ]
    assert "Current time" not in hidden_labels


def test_combined_plot_uses_target_colors():
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    targets = [
        parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783"),
        parse_manual_coordinates("17:28:19", "-14:15:56", "PDS 456"),
    ]
    results = [
        calculate_visibility(
            target,
            observer,
            date(2026, 3, 15),
            constraints,
            cadence_minutes=30,
        )
        for target in targets
    ]
    colors = {"NGC 3783": "#123456", "PDS 456": "#abcdef"}

    figure = plot_combined_visibility(
        results,
        constraints,
        "UTC",
        colors=colors,
        show_moon=False,
    )
    legend_labels = [
        text.get_text() for text in figure.axes[0].get_legend().get_texts()
    ]
    assert legend_labels == ["NGC 3783", "PDS 456", "Airmass limit"]
    solid_lines = {
        line.get_label(): line for line in figure.axes[0].get_lines()
    }
    assert solid_lines["NGC 3783"].get_color() == "#123456"
    assert solid_lines["PDS 456"].get_color() == "#abcdef"
    combined_summary = "\n".join(
        text.get_text() for text in figure.axes[0].texts
    )
    assert "max " not in combined_summary


def test_airmass_and_altitude_scales_are_equivalent():
    assert airmass_to_altitude(1.0) == pytest.approx(90.0)
    assert airmass_to_altitude(2.0) == pytest.approx(30.0)
    assert altitude_to_airmass(90.0) == pytest.approx(1.0)
    assert altitude_to_airmass(30.0) == pytest.approx(2.0)
