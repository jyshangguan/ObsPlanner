import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from streamlit.testing.v1 import AppTest


def _element(elements, label):
    return next(element for element in elements if element.label == label)


def _run_target_editor(app, changes, button=None):
    """Send browser-style editor state; AppTest has no data-editor edit API."""
    if button:
        _element(app.button, button).click()
    states = app._tree.get_widget_states()
    editor = states.widgets.add()
    editor.id = app.dataframe[0].proto.id
    editor.string_value = json.dumps(
        {"edited_rows": changes, "added_rows": [], "deleted_rows": []}
    )
    app._run(states, timeout=30)


def test_target_edits_survive_returning_to_planner():
    app = AppTest.from_file("app.py").run(timeout=30)
    _element(app.text_input, "Target name").set_value("Vega")
    _element(app.text_input, "Coordinates (RA, Dec)").set_value("10, +20")
    _element(app.button, "Add target").click().run(timeout=30)
    _element(app.button, "☰").click().run(timeout=30)
    changes = {0: {"note": "Observe twice", "exptime": "3 x 300", "tag": "P1"}}
    _run_target_editor(app, changes)
    _run_target_editor(app, changes, "Back to planner")

    target = app.session_state["targets"][0]
    assert (target.note, target.exptime, target.tag) == ("Observe twice", "3 x 300", "P1")
    assert app.session_state["content_page"] == "planner"
    # Refresh AppTest's tree after navigation removes the editor/color widgets.
    app._run(timeout=30)
    _element(app.button, "☰").click().run(timeout=30)
    row = app.dataframe[0].value.iloc[0]
    assert (row["note"], row["exptime"], row["tag"]) == ("Observe twice", "3 x 300", "P1")
    _run_target_editor(app, {0: {"exptime": "4 x 300"}}, "Apply target changes")
    target = app.session_state["targets"][0]
    assert (target.note, target.exptime, target.tag) == ("Observe twice", "4 x 300", "P1")
    assert not app.exception


def test_reopening_active_target_table_preserves_pending_edits():
    app = AppTest.from_file("app.py").run(timeout=30)
    _element(app.text_input, "Target name").set_value("Vega")
    _element(app.text_input, "Coordinates (RA, Dec)").set_value("10, +20")
    _element(app.button, "Add target").click().run(timeout=30)
    _element(app.button, "☰").click().run(timeout=30)
    changes = {0: {"note": "Keep this note"}}
    _run_target_editor(app, changes)
    _run_target_editor(app, changes, "☰")
    assert app.session_state["target_information_editor"]["edited_rows"] == changes
    _run_target_editor(app, changes, "Apply target changes")
    assert app.session_state["targets"][0].note == "Keep this note"
    assert not app.exception


def test_invalid_target_edits_block_navigation_without_losing_draft():
    app = AppTest.from_file("app.py").run(timeout=30)
    _element(app.text_input, "Target name").set_value("Vega")
    _element(app.text_input, "Coordinates (RA, Dec)").set_value("10, +20")
    _element(app.button, "Add target").click().run(timeout=30)
    _element(app.button, "☰").click().run(timeout=30)
    changes = {0: {"dec": 100, "note": "Keep this draft"}}
    _run_target_editor(app, changes, "Back to planner")
    assert app.session_state["content_page"] == "targets"
    assert app.error
    assert app.session_state["targets"][0].coord.dec.deg == 20
    assert app.session_state["target_information_editor"]["edited_rows"] == changes
    changes[0]["dec"] = 25
    _run_target_editor(app, changes, "Back to planner")
    assert app.session_state["targets"][0].note == "Keep this draft"
    assert app.session_state["targets"][0].coord.dec.deg == 25
    assert app.session_state["content_page"] == "planner"
    assert not app.exception


def test_palomar_selection_survives_adding_a_target():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert app.session_state.filtered_state["targets"] == []
    assert _element(app.text_input, "Target name").value == ""
    assert _element(app.text_input, "Coordinates (RA, Dec)").value == ""
    assert _element(app.selectbox, "Observatory").value == "palomar"

    _element(app.text_input, "Target name").set_value("Vega")
    _element(app.text_input, "Coordinates (RA, Dec)").set_value(
        "18:36:56, +38:47:01"
    )
    _element(app.button, "Add target").click()
    app.run(timeout=30)

    assert _element(app.selectbox, "Observatory").value == "palomar"
    context = app.session_state.filtered_state["active_plot_context"]
    assert context["observatory_key"] == "palomar"
    assert context["observer"].name == "Palomar Observatory"
    assert all(
        result.observer.name == "Palomar Observatory"
        for result in context["results"]
    )
    assert [target.name for target in app.session_state.filtered_state["targets"]] == [
        "Vega"
    ]
    assert not app.exception


def test_update_controls_only_appear_in_the_frozen_app():
    app = AppTest.from_file("app.py").run(timeout=30)

    # A source checkout cannot self-update, so the Settings popover must
    # not offer update controls at all.
    assert all(
        item.label != "Check for updates" for item in app.button
    )
    assert not app.exception


def test_sun_legend_context_requires_moon_and_daytime_toggles():
    app = AppTest.from_file("app.py").run(timeout=30)
    context = app.session_state.filtered_state["active_plot_context"]
    assert context["show_moon"] is True
    assert context["show_daytime"] is False

    _element(app.toggle, "Show the daytime").set_value(True)
    app.run(timeout=30)
    context = app.session_state.filtered_state["active_plot_context"]
    assert context["show_daytime"] is True

    _element(app.toggle, "Show the Moon & Sun").set_value(False)
    app.run(timeout=30)
    context = app.session_state.filtered_state["active_plot_context"]
    assert context["show_moon"] is False
    assert context["show_daytime"] is True
    assert not app.exception


def test_evening_box_lists_every_twilight_stage():
    app = AppTest.from_file("app.py").run(timeout=30)
    evening_box = next(
        item.value for item in app.markdown if "Evening times" in item.value
    )

    assert "Sunset:" in evening_box
    assert "Civil twilight:" in evening_box
    assert "Naut. twilight:" in evening_box
    assert "Astro. twilight:" in evening_box


def test_fixed_sky_time_is_a_typed_hhmm_field_beside_editable_date():
    app = AppTest.from_file("app.py").run(timeout=30)
    _element(app.toggle, "Current time").set_value(False)
    app.run(timeout=30)

    assert not _element(app.date_input, "Observing date").disabled
    time_field = _element(app.text_input, "Time (HH:MM)")
    time_field.set_value("21:37")
    app.run(timeout=30)

    assert _element(app.text_input, "Time (HH:MM)").value == "21:37"
    assert not app.error
    assert not app.exception


def test_observatory_clock_follows_selection():
    app = AppTest.from_file("app.py").run(timeout=30)

    for key, name, timezone in (
        ("xinglong", "Xinglong", "Asia/Shanghai"),
        ("palomar", "Palomar", "America/Los_Angeles"),
    ):
        _element(app.selectbox, "Observatory").set_value(key)
        before = datetime.now(ZoneInfo(timezone))
        app.run(timeout=30)
        after = datetime.now(ZoneInfo(timezone))

        clock_labels = [
            item.value for item in app.markdown
            if '<div class="observer-clock-name">' in item.value
        ]
        assert clock_labels[0] == f'<div class="observer-clock-name">{name}</div>'
        assert "UTC" in clock_labels[1]
        clock_values = [
            re.search(r"\d{2}:\d{2}:\d{2}", item.value).group()
            for item in app.markdown
            if '<div class="observer-clock-time">' in item.value
        ]
        expected_times = {
            (before + timedelta(seconds=second)).strftime("%H:%M:%S")
            for second in range(int((after - before).total_seconds()) + 2)
        }
        assert clock_values[0] in expected_times
        assert not app.exception


def test_live_palomar_and_remote_observer_clocks_are_available():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert _element(app.toggle, "Show the Moon & Sun").value
    assert any(
        "Current times" in item.value for item in app.markdown
    )
    assert any(
        re.search(r"\d{2}:\d{2}:\d{2}", item.value)
        for item in app.markdown
    )
    assert any(
        "observer-clock-name" in item.value and "Palomar" in item.value
        for item in app.markdown
    )
    clock_labels = [
        item.value
        for item in app.markdown
        if '<div class="observer-clock-name">' in item.value
    ]
    assert "Palomar" in clock_labels[0]
    assert "UTC" in clock_labels[1]

    _element(app.button, "＋").click()
    app.run(timeout=30)
    first_remote = _element(app.selectbox, "Remote observer 1 time zone")
    first_remote.set_value("Asia/Shanghai")
    app.run(timeout=30)

    assert _element(app.button, "Asia/Shanghai")
    assert not any(
        item.label == "Remote observer 1 time zone" for item in app.selectbox
    )
    _element(app.button, "＋").click()
    app.run(timeout=30)
    second_remote = _element(app.selectbox, "Remote observer 2 time zone")
    second_remote.set_value("Europe/London")
    app.run(timeout=30)

    assert _element(app.button, "Europe/London")
    _element(app.button, "Asia/Shanghai").click()
    app.run(timeout=30)
    assert _element(app.selectbox, "Remote observer 1 time zone").placeholder == (
        "Asia/Shanghai"
    )
    assert not app.exception


def test_targets_with_the_same_tag_share_color_changes():
    app = AppTest.from_file("app.py").run(timeout=30)
    for name, coordinates in (("First", "10, +20"), ("Second", "11, +21")):
        _element(app.text_input, "Target name").set_value(name)
        _element(app.text_input, "Coordinates (RA, Dec)").set_value(coordinates)
        _element(app.button, "Add target").click()
        app.run(timeout=30)

    app.session_state["target_tags"] = {
        "First": "program A",
        "Second": "program A",
    }
    app.run(timeout=30)
    _element(app.button, "☰").click()
    app.run(timeout=30)
    _element(app.color_picker, "Tag: program A").set_value("#123456")
    app.run(timeout=30)

    colors = app.session_state.filtered_state["target_colors"]
    assert colors["First"] == "#123456"
    assert colors["Second"] == "#123456"
    assert not app.exception


def test_target_tags_are_tooltips_and_not_inline_inputs():
    app = AppTest.from_file("app.py").run(timeout=30)
    _element(app.text_input, "Target name").set_value("Tagged")
    _element(app.text_input, "Coordinates (RA, Dec)").set_value("10, +20")
    _element(app.button, "Add target").click()
    app.run(timeout=30)
    app.session_state["target_tags"] = {"Tagged": "P1"}
    app.run(timeout=30)

    assert not any(item.label == "Tagged tag" for item in app.text_input)
    tooltip = next(item.value for item in app.markdown if "<strong>Tag:" in item.value)
    assert "P1" in tooltip
    assert "<strong>Exptime:" in tooltip
    assert "<strong>Note:" in tooltip
    assert any("color: #ff4b4b" in item.value for item in app.markdown)
    assert not app.color_picker
    _element(app.button, "☰").click()
    app.run(timeout=30)

    assert any(item.value == "Current targets" for item in app.title)
    assert _element(app.button, "Apply target changes")
    assert _element(app.button, "Back to planner")


def test_display_settings_can_hide_a_tag_group_from_plots():
    app = AppTest.from_file("app.py").run(timeout=30)
    for name, coordinates in (("First", "10, +20"), ("Second", "11, +21")):
        _element(app.text_input, "Target name").set_value(name)
        _element(app.text_input, "Coordinates (RA, Dec)").set_value(coordinates)
        _element(app.button, "Add target").click()
        app.run(timeout=30)

    app.session_state["target_tags"] = {"First": "P1", "Second": "P2"}
    app.run(timeout=30)
    _element(app.button, "☰").click()
    app.run(timeout=30)
    _element(app.toggle, "Show P2").set_value(False)
    app.run(timeout=30)
    _element(app.button, "Back to planner").click()
    app.run(timeout=30)

    results = app.session_state.filtered_state["active_plot_context"]["results"]
    assert [result.target.name for result in results] == ["First"]
    assert not app.exception
