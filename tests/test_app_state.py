from streamlit.testing.v1 import AppTest


def _element(elements, label):
    return next(element for element in elements if element.label == label)


def test_palomar_selection_survives_adding_a_target():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert app.session_state.filtered_state["targets"] == []
    assert _element(app.text_input, "Target name").value == ""
    assert _element(app.text_input, "Coordinates (RA, Dec)").value == ""

    _element(app.selectbox, "Observatory").select("palomar")
    app.run(timeout=30)
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


def test_evening_box_lists_every_twilight_stage():
    app = AppTest.from_file("app.py").run(timeout=30)
    evening_box = next(
        item.value for item in app.markdown if "Evening times" in item.value
    )

    assert "Sunset:" in evening_box
    assert "Civil twilight:" in evening_box
    assert "Nautical twilight:" in evening_box
    assert "Astronomical twilight:" in evening_box


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
