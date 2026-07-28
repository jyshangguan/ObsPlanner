from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from obsplanner.observatories import (  # noqa: E402
    ObservatoryCatalogError,
    load_observatories,
)
from obsplanner.plotting import (  # noqa: E402
    TIME_AXES,
    plot_combined_visibility,
    plot_visibility,
)
from obsplanner.targets import (  # noqa: E402
    Target,
    TargetResolutionError,
    parse_manual_coordinates,
    parse_target_csv,
    resolve_target,
)
from obsplanner.visibility import (  # noqa: E402
    VisibilityConstraints,
    calculate_visibility,
)

st.set_page_config(
    page_title="ObsPlanner",
    page_icon="🔭",
    layout="wide",
)
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 4.5rem;
            padding-bottom: 1rem;
        }
        .plot-spacer {
            height: 0.75rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_COLORS = (
    "#ff4b4b",
    "#4da6ff",
    "#ff9f40",
    "#9b59b6",
    "#2ecc71",
    "#e84393",
    "#00b894",
    "#6c5ce7",
)


@st.cache_data
def observatory_catalog():
    return load_observatories(PROJECT_ROOT / "data" / "observatories.yaml")


@st.cache_data(ttl=3600, show_spinner=False)
def cached_resolve_target(name: str):
    return resolve_target(name)


def add_targets(new_targets: list[Target]) -> tuple[int, list[str]]:
    existing = {target.name.casefold() for target in st.session_state.targets}
    added = 0
    skipped: list[str] = []
    for target in new_targets:
        if target.name.casefold() in existing:
            skipped.append(target.name)
            continue
        st.session_state.targets.append(target)
        index = len(st.session_state.targets) - 1
        st.session_state.target_colors.setdefault(
            target.name, DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
        )
        existing.add(target.name.casefold())
        added += 1
    return added, skipped


if "targets" not in st.session_state:
    st.session_state.targets = [
        parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    ]
if "target_colors" not in st.session_state:
    st.session_state.target_colors = {"NGC 3783": DEFAULT_COLORS[0]}

try:
    catalog = observatory_catalog()
except ObservatoryCatalogError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.title("🔭 ObsPlanner")
    st.caption("Astronomical visibility planner")

    st.header("Targets")
    add_mode = st.radio(
        "Add targets",
        ("One by one", "Upload CSV"),
        horizontal=True,
    )

    if add_mode == "One by one":
        entry_method = st.radio(
            "Coordinate source",
            ("Resolve name", "Enter coordinates"),
            horizontal=True,
        )
        if entry_method == "Resolve name":
            with st.form("resolve_target_form"):
                target_name = st.text_input("Target name", value="PDS 456")
                add_individual = st.form_submit_button(
                    "Add target", width="stretch"
                )
            if add_individual:
                try:
                    with st.spinner(f"Resolving {target_name} with SIMBAD…"):
                        new_target = cached_resolve_target(target_name)
                    added, skipped = add_targets([new_target])
                    if added:
                        st.rerun()
                    st.warning(f"“{skipped[0]}” is already in the target list.")
                except TargetResolutionError as exc:
                    st.error(str(exc))
        else:
            coordinate_format = st.radio(
                "Coordinate format",
                ("Sexagesimal", "Decimal degrees"),
                horizontal=True,
            )
            decimal_coordinates = coordinate_format == "Decimal degrees"
            with st.form("manual_target_form"):
                display_name = st.text_input("Target name", value="PDS 456")
                if decimal_coordinates:
                    ra_default, dec_default = "262.0825", "-14.9322"
                    ra_label = "Right ascension (degrees)"
                else:
                    ra_default, dec_default = "17:28:19.8", "-14:55:56"
                    ra_label = "Right ascension (hours)"
                ra_text = st.text_input(ra_label, value=ra_default)
                dec_text = st.text_input("Declination (degrees)", value=dec_default)
                add_individual = st.form_submit_button(
                    "Add target", width="stretch"
                )
            if add_individual:
                try:
                    new_target = parse_manual_coordinates(
                        ra_text,
                        dec_text,
                        display_name,
                        decimal_degrees=decimal_coordinates,
                    )
                    added, skipped = add_targets([new_target])
                    if added:
                        st.rerun()
                    st.warning(f"“{skipped[0]}” is already in the target list.")
                except TargetResolutionError as exc:
                    st.error(str(exc))
    else:
        uploaded_catalog = st.file_uploader(
            "Target CSV",
            type=("csv",),
            help=(
                "Required columns: name, ra, dec. Sexagesimal RA uses hours; "
                "numeric RA uses decimal degrees."
            ),
        )
        st.caption("Required columns: `name`, `ra`, `dec`")
        if st.button(
            "Import targets",
            disabled=uploaded_catalog is None,
            width="stretch",
        ):
            try:
                imported_targets = parse_target_csv(uploaded_catalog.getvalue())
                added, skipped = add_targets(imported_targets)
                if added:
                    st.session_state.import_notice = (
                        f"Imported {added} target"
                        f"{'s' if added != 1 else ''}."
                    )
                    if skipped:
                        st.session_state.import_notice += (
                            " Skipped existing: " + ", ".join(skipped) + "."
                        )
                    st.rerun()
                st.warning("All uploaded targets are already in the list.")
            except TargetResolutionError as exc:
                st.error(str(exc))

    if "import_notice" in st.session_state:
        st.success(st.session_state.pop("import_notice"))

    st.header("Night and constraints")
    observing_date = st.date_input("Observing date", value=date.today())
    maximum_airmass = st.slider("Maximum airmass", 1.0, 3.0, 2.0, 0.1)
    minimum_moon_separation = st.slider(
        "Minimum Moon separation (degrees)", 0, 180, 30, 5
    )
    show_moon = st.toggle(
        "Show the Moon",
        value=True,
        help="Show or hide the Moon-altitude curve in the visibility plot.",
    )
    time_axis = st.radio(
        "Plot time axis",
        TIME_AXES,
        horizontal=True,
        help=(
            "LST is apparent local sidereal time at the selected observatory. "
            "It is shown on the same evenly sampled timeline."
        ),
    )

    current_plot_mode = st.session_state.get("plot_mode", "Combined panel")
    st.header(f"Current targets ({len(st.session_state.targets)})")
    for index, listed_target in enumerate(list(st.session_state.targets)):
        if current_plot_mode == "Combined panel":
            name_column, color_column, remove_column = st.columns([3.5, 1.2, 1])
            current_color = st.session_state.target_colors.setdefault(
                listed_target.name,
                DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
            )
            with color_column:
                st.session_state.target_colors[listed_target.name] = st.color_picker(
                    f"{listed_target.name} color",
                    value=current_color,
                    key=f"target_color_{listed_target.name}",
                    label_visibility="collapsed",
                )
        else:
            name_column, remove_column = st.columns([4, 1])
        name_column.write(listed_target.name)
        if remove_column.button(
            "✕",
            key=f"remove_target_{index}_{listed_target.name}",
            help=f"Remove {listed_target.name}",
        ):
            st.session_state.targets.pop(index)
            st.session_state.target_colors.pop(listed_target.name, None)
            st.rerun()
    if st.session_state.targets and st.button(
        "Clear target list", width="stretch"
    ):
        st.session_state.targets = []
        st.session_state.target_colors = {}
        st.rerun()

site_keys = sorted(catalog, key=lambda key: catalog[key].name)
default_index = site_keys.index("paranal")
site_column, layout_column = st.columns([1.15, 1])
with site_column:
    selected_key = st.selectbox(
        "Observatory",
        site_keys,
        index=default_index,
        format_func=lambda key: catalog[key].name,
    )
    site = catalog[selected_key]
    st.caption(
        f"{site.latitude:.4f}°, {site.longitude:.4f}° · "
        f"{site.elevation:.0f} m · {site.timezone}"
    )
with layout_column:
    plot_mode = st.radio(
        "Plot layout",
        ("Combined panel", "Separate panels"),
        horizontal=True,
        key="plot_mode",
    )

if not st.session_state.targets:
    st.info("Add at least one target in the sidebar to create a visibility plot.")
    st.stop()

constraints = VisibilityConstraints(
    minimum_altitude=0.0,
    maximum_airmass=float(maximum_airmass),
    minimum_moon_separation=float(minimum_moon_separation),
)
try:
    observer = site.to_observer()
    with st.spinner("Calculating target visibility…"):
        results = [
            calculate_visibility(
                target,
                observer,
                observing_date,
                constraints,
            )
            for target in st.session_state.targets
        ]
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(
        "The visibility calculation could not be completed. "
        "Please check the inputs and try again."
    )
    with st.expander("Technical details"):
        st.exception(exc)
    st.stop()

st.markdown('<div class="plot-spacer"></div>', unsafe_allow_html=True)
if plot_mode == "Combined panel":
    visibility_figure = plot_combined_visibility(
        results,
        constraints,
        time_axis,
        colors=st.session_state.target_colors,
        show_moon=show_moon,
    )
    st.pyplot(visibility_figure, width="stretch")
    plt.close(visibility_figure)
else:
    for result in results:
        visibility_figure = plot_visibility(
            result,
            constraints,
            time_axis,
            show_moon=show_moon,
        )
        st.pyplot(visibility_figure, width="stretch")
        plt.close(visibility_figure)

st.markdown(
    "**Background darkness:** pale yellow is daylight (Sun above 0°); "
    "light cyan is civil twilight (0° to −6°); cyan is nautical twilight "
    "(−6° to −12°); blue is astronomical twilight (−12° to −18°); and "
    "dark blue is astronomical night (Sun below −18°)."
)
st.caption(
    "Each target curve is dashed where its Moon separation is below "
    f"{minimum_moon_separation}° and solid where that separation constraint "
    "passes. Full observability also requires astronomical night, the target "
    f"above the horizon, and airmass ≤ {maximum_airmass:.1f}. Results are "
    "planning aids; confirm final constraints with the facility."
)
warnings = sorted({result.warning for result in results if result.warning})
for warning in warnings:
    st.warning(warning)
