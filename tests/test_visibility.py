from datetime import date
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from astropy.time import Time

from obsplanner.observatories import load_observatories
from obsplanner.plotting import (
    airmass_to_altitude,
    altitude_to_airmass,
    plot_combined_visibility,
    plot_sky,
    plot_visibility,
)
from obsplanner.plotting.plots import _time_axis_labeler
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
    assert figure.get_size_inches() == pytest.approx((12.5, 8.35))
    assert len(figure.axes) == 1
    assert figure.axes[0].get_ylabel() == "Airmass [sec(z)]"
    assert figure.axes[0].child_axes[0].get_ylabel() == "Altitude (degrees)"
    assert figure.axes[0].xaxis.label.get_fontsize() == pytest.approx(12)
    assert figure.axes[0].yaxis.label.get_fontsize() == pytest.approx(12)
    assert (
        figure.axes[0].child_axes[0].yaxis.label.get_fontsize()
        == pytest.approx(12)
    )
    assert figure.axes[0].title.get_fontsize() == pytest.approx(14)
    assert expected_label in figure.axes[0].get_xlabel()
    labels = [line.get_label() for line in figure.axes[0].get_lines()]
    assert "Moon altitude" in labels
    moon_line = next(
        line
        for line in figure.axes[0].get_lines()
        if line.get_label() == "Moon altitude"
    )
    assert moon_line.get_linestyle() == "--"
    assert len(figure.axes[0].texts) == 0
    title = figure.axes[0].get_title()
    assert "Moon fraction" in title
    assert title.endswith(" · Moon separation ≥ 30°")
    assert "2026-03-15" in figure.axes[0].get_title()
    assert "Paranal Observatory" in figure.axes[0].get_title()
    legend_labels = [
        text.get_text() for text in figure.axes[0].get_legend().get_texts()
    ]
    assert legend_labels == [
        "NGC 3783",
        "Moon altitude",
    ]
    assert figure.axes[0].get_ylim() == pytest.approx((3.0, 0.97))
    assert all(
        text.get_fontsize() == pytest.approx(12.3)
        for text in figure.axes[0].get_legend().get_texts()
    )


def test_palomar_local_time_axis_uses_observer_timezone():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["palomar"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target,
        observer,
        date(2026, 8, 8),
        constraints,
        cadence_minutes=30,
        show_daytime=True,
    )
    current_time = Time("2026-08-09T01:50:00")

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
    elapsed_hours = float(current_line.get_xdata()[0])
    axis_label = figure.axes[0].xaxis.get_major_formatter()(elapsed_hours, 0)

    assert axis_label == "18:50"
    assert "America/Los_Angeles" in figure.axes[0].get_xlabel()


def test_palomar_current_time_marker_appears_during_plotted_night():
    target = parse_manual_coordinates("18:36:56", "+38:47:01", "Vega")
    observer = load_observatories()["palomar"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target,
        observer,
        date(2026, 8, 8),
        constraints,
        cadence_minutes=30,
    )
    current_time = Time("2026-08-09T02:10:00")

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
    elapsed_hours = float(current_line.get_xdata()[0])

    assert figure.axes[0].xaxis.get_major_formatter()(elapsed_hours, 0) == "19:10"
    assert current_line.get_color() == "#d62728"


@pytest.mark.parametrize(
    "current_time",
    [Time("2026-01-15T12:34:00"), Time("2026-08-09T01:50:00")],
    ids=("january", "august"),
)
def test_local_time_axis_matches_every_observatory_timezone(current_time):
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    constraints = VisibilityConstraints()

    for site in load_observatories().values():
        observer = site.to_observer()
        timezone = ZoneInfo(site.timezone)
        local_date = current_time.to_datetime(timezone=timezone).date()
        result = calculate_visibility(
            target,
            observer,
            local_date,
            constraints,
            cadence_minutes=120,
            show_daytime=True,
        )
        elapsed_hours = float((current_time - result.times[0]).to_value("hour"))
        formatter, axis_label = _time_axis_labeler(result, "Local time")
        expected = current_time.to_datetime(timezone=timezone).strftime("%H:%M")

        assert formatter(elapsed_hours, 0) == expected, site.name
        assert site.timezone in axis_label


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
    assert current_line.get_color() == "#d62728"
    assert current_line.get_linewidth() == pytest.approx(2.0)
    assert current_line.get_color() == "#d62728"
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
    assert figure.get_size_inches() == pytest.approx((12.5, 8.35))
    legend_labels = [
        text.get_text() for text in figure.axes[0].get_legend().get_texts()
    ]
    assert legend_labels == ["NGC 3783", "PDS 456"]
    solid_lines = {
        line.get_label(): line for line in figure.axes[0].get_lines()
    }
    assert solid_lines["NGC 3783"].get_color() == "#123456"
    assert solid_lines["PDS 456"].get_color() == "#abcdef"
    assert len(figure.axes[0].texts) == 0
    assert "Moon separation ≥ 30°" in figure.axes[0].get_title()


def test_combined_plot_can_leave_legend_to_the_ui():
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    target = parse_manual_coordinates(
        "11:39:01", "-37:44:20", "NGC 3783"
    )
    result = calculate_visibility(
        target,
        observer,
        date(2026, 3, 15),
        constraints,
        cadence_minutes=30,
    )

    figure = plot_combined_visibility(
        [result],
        constraints,
        colors={"NGC 3783": "#123456"},
        show_legend=False,
    )

    assert figure.axes[0].get_legend() is None
    labels = [line.get_label() for line in figure.axes[0].get_lines()]
    assert "NGC 3783" in labels
    assert "Moon altitude" in labels
    assert "Airmass limit" not in labels
    target_line = next(
        line for line in figure.axes[0].get_lines()
        if line.get_label() == "NGC 3783"
    )
    assert target_line.get_linewidth() == pytest.approx(1.0)
    assert target_line.get_alpha() == pytest.approx(1.0)
    assert target_line.get_zorder() > max(
        patch.get_zorder() for patch in figure.axes[0].patches
    )
    assert target_line.get_gid() == "obs-target-0-solid"
    assert all(
        patch.get_alpha() == pytest.approx(0.5)
        for patch in figure.axes[0].patches
    )


def test_sky_plot_shows_all_targets_with_matching_colors_and_labels():
    targets = [
        parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783"),
        parse_manual_coordinates("17:28:19", "-14:15:56", "PDS 456"),
    ]
    colors = {"NGC 3783": "#123456", "PDS 456": "#abcdef"}

    observer = load_observatories()["paranal"].to_observer()
    observation_time = Time("2026-03-15T04:00:00")
    figure = plot_sky(
        targets,
        observer,
        observation_time,
        colors=colors,
        show_moon=False,
    )
    sky_axis = figure.axes[0]

    assert sky_axis.name == "polar"
    assert sky_axis.get_title().startswith("Sky plot\nParanal Observatory ·")
    assert len(sky_axis.collections) == 2
    assert [text.get_text() for text in sky_axis.texts] == [
        "NGC 3783",
        "PDS 456",
    ]
    assert all(text.get_fontsize() == pytest.approx(12) for text in sky_axis.texts)
    assert [text.get_color() for text in sky_axis.texts] == ["#123456", "#abcdef"]
    assert [collection.get_facecolor()[0][:3] for collection in sky_axis.collections] == [
        pytest.approx((0x12 / 255, 0x34 / 255, 0x56 / 255)),
        pytest.approx((0xab / 255, 0xcd / 255, 0xef / 255)),
    ]


def test_sky_plot_includes_the_moon_by_default():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()

    figure = plot_sky(
        [target],
        observer,
        Time("2026-03-15T04:00:00"),
        colors={"NGC 3783": "#123456"},
    )

    assert [text.get_text() for text in figure.axes[0].texts] == [
        "NGC 3783",
        "Moon",
    ]


def test_single_visibility_plot_accepts_target_color():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=30
    )

    figure = plot_visibility(result, constraints, color="#123456")
    target_lines = [
        line for line in figure.axes[0].get_lines()
        if line.get_label() in {"NGC 3783", "Moon separation < 30°"}
    ]
    assert target_lines
    assert all(line.get_color() == "#123456" for line in target_lines)


def test_airmass_and_altitude_scales_are_equivalent():
    assert airmass_to_altitude(1.0) == pytest.approx(90.0)
    assert airmass_to_altitude(2.0) == pytest.approx(30.0)
    assert altitude_to_airmass(90.0) == pytest.approx(1.0)
    assert altitude_to_airmass(30.0) == pytest.approx(2.0)


def _sky_plot_targets():
    return [
        parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783"),
        parse_manual_coordinates("17:28:19", "-14:15:56", "PDS 456"),
    ]


def test_sky_plot_selection_is_bold_and_drawn_on_top():
    targets = _sky_plot_targets()
    colors = {"NGC 3783": "#123456", "PDS 456": "#abcdef"}
    observer = load_observatories()["paranal"].to_observer()

    figure = plot_sky(
        targets,
        observer,
        Time("2026-03-15T04:00:00"),
        colors=colors,
        show_moon=False,
        selected="NGC 3783",
    )
    sky_axis = figure.axes[0]

    # The selected target is drawn last, so it ends up on top.
    assert [text.get_text() for text in sky_axis.texts] == [
        "PDS 456",
        "NGC 3783",
    ]
    selected_label = sky_axis.texts[-1]
    other_label = sky_axis.texts[0]
    assert selected_label.get_fontweight() == "bold"
    assert selected_label.get_color() == "#ffea00"
    assert other_label.get_fontweight() == "normal"
    assert other_label.get_color() == "#abcdef"
    assert selected_label.get_fontsize() == 14
    assert other_label.get_fontsize() == 12
    label_frame = selected_label.get_bbox_patch()
    assert label_frame is not None
    assert label_frame.get_facecolor() == (0.1, 0.1, 0.1, 0.75)
    assert label_frame.get_edgecolor()[:3] == pytest.approx(
        (1.0, 234 / 255, 0.0)
    )
    assert other_label.get_bbox_patch() is None
    assert selected_label.get_zorder() > other_label.get_zorder()
    selected_marker = sky_axis.collections[-1]
    other_marker = sky_axis.collections[0]
    assert list(selected_marker.get_sizes()) == [70]
    assert selected_marker.get_facecolors()[0][:3] == pytest.approx(
        (1.0, 234 / 255, 0.0)
    )
    assert list(other_marker.get_sizes()) == [30]
    assert selected_marker.get_zorder() > other_marker.get_zorder()
    assert selected_marker.get_zorder() > 4  # above the Moon's label zorder


def test_sky_plot_without_selection_keeps_input_order_and_normal_weight():
    targets = _sky_plot_targets()
    colors = {"NGC 3783": "#123456", "PDS 456": "#abcdef"}
    observer = load_observatories()["paranal"].to_observer()

    figure = plot_sky(
        targets,
        observer,
        Time("2026-03-15T04:00:00"),
        colors=colors,
        show_moon=False,
    )
    sky_axis = figure.axes[0]

    assert [text.get_text() for text in sky_axis.texts] == [
        "NGC 3783",
        "PDS 456",
    ]
    assert all(text.get_fontweight() == "normal" for text in sky_axis.texts)
    assert all(text.get_fontsize() == 12 for text in sky_axis.texts)
    assert all(text.get_bbox_patch() is None for text in sky_axis.texts)
    zorders = [collection.get_zorder() for collection in sky_axis.collections]
    assert zorders == [3, 3]
    sizes = [list(c.get_sizes()) for c in sky_axis.collections]
    assert sizes == [[30], [30]]


def test_sky_plot_ignores_an_unknown_selected_name():
    targets = _sky_plot_targets()
    colors = {"NGC 3783": "#123456", "PDS 456": "#abcdef"}
    observer = load_observatories()["paranal"].to_observer()

    figure = plot_sky(
        targets,
        observer,
        Time("2026-03-15T04:00:00"),
        colors=colors,
        show_moon=False,
        selected="Not in the list",
    )
    sky_axis = figure.axes[0]

    assert [text.get_text() for text in sky_axis.texts] == [
        "NGC 3783",
        "PDS 456",
    ]
    assert all(text.get_fontweight() == "normal" for text in sky_axis.texts)
    assert all(text.get_fontsize() == 12 for text in sky_axis.texts)
    assert all(text.get_bbox_patch() is None for text in sky_axis.texts)


def test_single_visibility_plot_uses_target_index_in_curve_gids():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    observer = load_observatories()["paranal"].to_observer()
    constraints = VisibilityConstraints()
    result = calculate_visibility(
        target, observer, date(2026, 3, 15), constraints, cadence_minutes=30
    )

    figure = plot_visibility(result, constraints, target_index=3)
    gids = {line.get_gid() for line in figure.axes[0].get_lines()}
    assert "obs-target-3-solid" in gids
    assert "obs-target-3-dashed" in gids


def test_calculator_never_hard_fails_on_stale_iers_predictions():
    from astropy.utils import iers

    assert iers.conf.auto_download is False
    assert iers.conf.auto_max_age is None
