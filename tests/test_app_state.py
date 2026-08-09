from streamlit.testing.v1 import AppTest


def _element(elements, label):
    return next(element for element in elements if element.label == label)


def test_palomar_selection_survives_adding_a_target():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert app.session_state.filtered_state["targets"] == []

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
