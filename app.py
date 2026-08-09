from __future__ import annotations

import base64
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import streamlit as st
from astropy.time import Time

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
APP_LOGO = PROJECT_ROOT / "assets" / "ObsPlanner.png"

from obsplanner.observatories import (  # noqa: E402
    ObservatoryCatalogError,
    load_observatories,
)
from obsplanner.plotting import (  # noqa: E402
    TIME_AXES,
    plot_combined_visibility,
    plot_sky,
    plot_visibility,
)
from obsplanner.targets import (  # noqa: E402
    Target,
    TargetResolutionError,
    parse_coordinate_pair,
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
    page_icon=str(APP_LOGO),
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
        [data-testid="stSidebarHeader"] {
            height: 3.25rem;
            min-height: 3.25rem;
        }
        [data-testid="stSidebarContent"] {
            padding-top: 0.2rem;
        }
        .obsplanner-brand {
            align-items: center;
            display: flex;
            gap: 0.75rem;
            margin: 0 0 0.3rem;
        }
        .obsplanner-brand img {
            border-radius: 0.7rem;
            height: 3rem;
            width: 3rem;
        }
        .obsplanner-brand-name {
            color: var(--text-color);
            font-size: 2rem;
            font-weight: 700;
            line-height: 1;
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


def remember_selected_observatory() -> None:
    """Persist the site across reruns that occur before its widget is rendered."""
    st.session_state.observatory_preference = st.session_state.selected_observatory


if "targets" not in st.session_state:
    st.session_state.targets = []
if "target_colors" not in st.session_state:
    st.session_state.target_colors = {}

try:
    catalog = observatory_catalog()
except ObservatoryCatalogError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    logo_data = base64.b64encode(APP_LOGO.read_bytes()).decode("ascii")
    st.markdown(
        (
            '<div class="obsplanner-brand">'
            f'<img src="data:image/png;base64,{logo_data}" alt="ObsPlanner logo">'
            '<span class="obsplanner-brand-name">ObsPlanner</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.caption("Astronomical visibility planner")

    st.header("Targets")
    add_mode = st.radio(
        "Add targets",
        ("One by one", "Upload CSV"),
        horizontal=True,
    )

    if add_mode == "One by one":
        name_column, resolve_column = st.columns([5, 1], vertical_alignment="bottom")
        with name_column:
            target_name = st.text_input(
                "Target name", value="PDS 456", key="target_name_input"
            )
        with resolve_column:
            resolve_name = st.button(
                "🔍",
                help="Resolve this target name with SIMBAD",
                width="stretch",
            )
        if resolve_name:
            try:
                with st.spinner(f"Resolving {target_name} with SIMBAD…"):
                    resolved_target = cached_resolve_target(target_name)
                st.session_state.target_coordinates_input = (
                    f"{resolved_target.coord.icrs.ra.deg:.6f}, "
                    f"{resolved_target.coord.icrs.dec.deg:+.6f}"
                )
            except TargetResolutionError as exc:
                st.error(str(exc))

        coordinate_text = st.text_input(
            "Coordinates (RA, Dec)",
            value="262.082500, -14.932200",
            key="target_coordinates_input",
            help=(
                "Use sexagesimal RA and Dec or decimal degrees, separated "
                "by a comma."
            ),
        )
        if st.button("Add target", width="stretch"):
            try:
                new_target = parse_coordinate_pair(coordinate_text, target_name)
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

    current_plot_mode = (
        "Separate panels"
        if st.session_state.get("separate_panels", False)
        else "Combined panel"
    )
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

    with st.popover("Settings", width="stretch"):
        time_axis = st.radio(
            "Plot time axis",
            TIME_AXES,
            horizontal=True,
            help=(
                "LST is apparent local sidereal time at the selected "
                "observatory. It is shown on the same evenly sampled timeline."
            ),
        )
        show_moon = st.toggle(
            "Show the Moon",
            value=True,
            help="Show or hide the Moon in both plots.",
        )
        show_sky_plot = st.toggle("Show sky plot", value=True)
        separate_panels = st.toggle(
            "Separate panels",
            value=False,
            key="separate_panels",
            help="Show one observability plot per target instead of combining them.",
        )
        plot_mode = "Separate panels" if separate_panels else "Combined panel"
        show_daytime = st.toggle(
            "Show the daytime",
            value=False,
            help=(
                "Extend the plot to the complete 24-hour observing day, from "
                "local noon on the selected date to local noon the next day."
            ),
        )
        refresh_label = st.selectbox(
            "Current-time update frequency",
            ("10 seconds", "30 seconds", "1 minute", "5 minutes"),
            index=0,
            help=(
                "How often the visibility plot updates the current-time "
                "indicator."
            ),
        )
        maximum_airmass = st.slider(
            "Maximum airmass", 1.0, 3.0, 2.0, 0.1
        )
        minimum_moon_separation = st.slider(
            "Minimum Moon separation (degrees)", 0, 180, 30, 5
        )

site_keys = sorted(catalog, key=lambda key: catalog[key].name)
preferred_site = st.session_state.get("observatory_preference", "paranal")
if preferred_site not in site_keys:
    preferred_site = "paranal"
default_index = site_keys.index(preferred_site)
if show_sky_plot:
    controls_column, sky_column = st.columns([3, 1], vertical_alignment="top")
else:
    controls_column = st.container()
    sky_column = None

with controls_column:
    site_column, _top_spacer = st.columns([1.15, 2.0])
    with site_column:
        selected_key = st.selectbox(
            "Observatory",
        site_keys,
        index=default_index,
        format_func=lambda key: catalog[key].name,
        key="selected_observatory",
        on_change=remember_selected_observatory,
    )
        site = catalog[selected_key]
        st.caption(
            f"{site.latitude:.4f}°, {site.longitude:.4f}° · "
            f"{site.elevation:.0f} m · {site.timezone}"
        )
    date_column, time_column, _control_spacer = st.columns([0.75, 0.85, 1.55])
    with time_column:
        use_current_sky_time = st.toggle(
            "Current time",
            value=True,
            help=(
                "Use the current time and lock the observing date to the current "
                "date at the selected observatory."
            ),
        )
        if show_sky_plot and not use_current_sky_time:
            sky_clock_time = st.time_input(
                "Sky plot time",
                value=time(0, 0),
                step=60,
                help=f"Local time at {site.name} ({site.timezone}).",
            )
    with date_column:
        observatory_today = datetime.now(ZoneInfo(site.timezone)).date()
        observing_date = st.date_input(
            "Observing date",
            value=observatory_today,
            key=(
                f"current_observing_date_{selected_key}_{observatory_today}"
                if use_current_sky_time
                else f"observing_date_{selected_key}"
            ),
            disabled=use_current_sky_time,
            help=f"Calendar date at {site.name} ({site.timezone}).",
        )

refresh_intervals = {
    "10 seconds": "10s",
    "30 seconds": "30s",
    "1 minute": "1m",
    "5 minutes": "5m",
}
refresh_interval = refresh_intervals[refresh_label]

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
                show_daytime=show_daytime,
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

# Timed fragments rerun independently of the full app. Keep their complete
# plotting context in session state so an observatory change cannot leave a
# fragment using objects captured during an earlier full render.
st.session_state.active_plot_context = {
    "observatory_key": selected_key,
    "observer": observer,
    "results": results,
    "constraints": constraints,
    "time_axis": time_axis,
    "plot_mode": plot_mode,
    "target_colors": dict(st.session_state.target_colors),
    "show_moon": show_moon,
}

if sky_column is not None:
    with sky_column:
        if use_current_sky_time:

            @st.fragment(run_every=refresh_interval)
            def render_current_sky_plot():
                context = st.session_state.active_plot_context
                sky_figure = plot_sky(
                    [result.target for result in context["results"]],
                    context["observer"],
                    Time.now(),
                    colors=context["target_colors"],
                    show_moon=context["show_moon"],
                )
                st.pyplot(sky_figure, width="stretch")
                plt.close(sky_figure)

            render_current_sky_plot()
        else:
            selected_sky_time = Time(
                datetime.combine(
                    observing_date,
                    sky_clock_time,
                    tzinfo=ZoneInfo(site.timezone),
                )
            )
            sky_figure = plot_sky(
                st.session_state.targets,
                observer,
                selected_sky_time,
                colors=st.session_state.target_colors,
                show_moon=show_moon,
            )
            st.pyplot(sky_figure, width="stretch")
            plt.close(sky_figure)

st.markdown('<div class="plot-spacer"></div>', unsafe_allow_html=True)


@st.fragment(run_every=refresh_interval)
def render_visibility_plots():
    context = st.session_state.active_plot_context
    plot_results = context["results"]
    plot_constraints = context["constraints"]
    target_colors = context["target_colors"]
    current_time = Time.now()
    if context["plot_mode"] == "Combined panel":
        visibility_figure = plot_combined_visibility(
            plot_results,
            plot_constraints,
            context["time_axis"],
            colors=target_colors,
            show_moon=context["show_moon"],
            current_time=current_time,
        )
        st.pyplot(visibility_figure, width="stretch")
        plt.close(visibility_figure)
    else:
        for result in plot_results:
            visibility_figure = plot_visibility(
                result,
                plot_constraints,
                context["time_axis"],
                color=target_colors.get(
                    result.target.name, DEFAULT_COLORS[0]
                ),
                show_moon=context["show_moon"],
                current_time=current_time,
            )
            st.pyplot(visibility_figure, width="stretch")
            plt.close(visibility_figure)


render_visibility_plots()

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

st.markdown(
    '<span id="obsplanner-app-ready" style="display:none"></span>',
    unsafe_allow_html=True,
)
