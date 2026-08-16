from __future__ import annotations

import base64
import html
import io
import json
import re
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import streamlit as st
from astropy.time import Time
from matplotlib.lines import Line2D

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
        .import-popup {
            animation: import-popup-cycle 3s ease-in-out forwards;
            background: #effbf3;
            border: 2px solid #8bd3a7;
            border-radius: 0.75rem;
            box-shadow: 0 0.3rem 1rem rgba(25, 90, 50, 0.14);
            color: #147a3d;
            font-size: 1.05rem;
            font-weight: 600;
            left: 50%;
            max-width: min(36rem, calc(100vw - 2rem));
            opacity: 0;
            padding: 0.8rem 1.25rem;
            pointer-events: none;
            position: fixed;
            text-align: center;
            top: 1rem;
            transform: translate(-50%, -0.75rem);
            visibility: hidden;
            width: max-content;
            z-index: 1000000;
        }
        @keyframes import-popup-cycle {
            0% {
                opacity: 0;
                transform: translate(-50%, -0.75rem);
                visibility: visible;
            }
            15%, 75% {
                opacity: 1;
                transform: translate(-50%, 0);
                visibility: visible;
            }
            100% {
                opacity: 0;
                transform: translate(-50%, -0.5rem);
                visibility: hidden;
            }
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


def _target_cache_key(target: Target):
    icrs = target.coord.icrs
    return (target.name, icrs.ra.deg, icrs.dec.deg)


@st.cache_data(
    show_spinner=False, hash_funcs={Target: _target_cache_key}
)
def cached_visibility(
    target: Target,
    observatory_key: str,
    observing_date,
    maximum_airmass: float,
    minimum_moon_separation: float,
    show_daytime: bool,
):
    """Visibility depends only on these inputs, so reuse it across reruns."""
    site = observatory_catalog()[observatory_key]
    return calculate_visibility(
        target,
        site.to_observer(),
        observing_date,
        VisibilityConstraints(
            minimum_altitude=0.0,
            maximum_airmass=maximum_airmass,
            minimum_moon_separation=minimum_moon_separation,
        ),
        show_daytime=show_daytime,
    )


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
                "Target name", value="", key="target_name_input"
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
            value="",
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

    current_plot_mode = (
        "Separate panels"
        if st.session_state.get("separate_panels", False)
        else "Combined panel"
    )
    st.header(f"Current targets ({len(st.session_state.targets)})")
    target_list = st.container(height=300, border=False)
    with target_list:
        for index, listed_target in enumerate(list(st.session_state.targets)):
            if current_plot_mode == "Combined panel":
                name_column, color_column, remove_column = st.columns([3.5, 1.2, 1])
                current_color = st.session_state.target_colors.setdefault(
                    listed_target.name,
                    DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
                )
                with color_column:
                    st.session_state.target_colors[listed_target.name] = (
                        st.color_picker(
                            f"{listed_target.name} color",
                            value=current_color,
                            key=f"target_color_{listed_target.name}",
                            label_visibility="collapsed",
                        )
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
            "Maximum airmass", 1.0, 3.0, 3.0, 0.1
        )
        minimum_moon_separation = st.slider(
            "Minimum Moon separation (degrees)", 0, 180, 30, 5
        )

if "import_notice" in st.session_state:
    import_notice = html.escape(st.session_state.pop("import_notice"))
    st.markdown(
        f'<div class="import-popup">{import_notice}</div>',
        unsafe_allow_html=True,
    )

site_keys = sorted(catalog, key=lambda key: catalog[key].name)
preferred_site = st.session_state.get("observatory_preference", "palomar")
if preferred_site not in site_keys:
    preferred_site = "palomar"
default_index = site_keys.index(preferred_site)
if show_sky_plot:
    controls_column, sky_column = st.columns([3, 1], vertical_alignment="top")
else:
    controls_column = st.container()
    sky_column = None

with controls_column:
    site_column, twilight_column = st.columns(
        [1.15, 2.0], vertical_alignment="top"
    )
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
        st.session_state.setdefault("use_current_time", True)
        use_current_sky_time = bool(st.session_state.use_current_time)
        date_column, fixed_time_column = st.columns([1.7, 1])
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
        sky_clock_time = None
        if not use_current_sky_time:
            with fixed_time_column:
                sky_clock_text = st.text_input(
                    "Time (HH:MM)",
                    value="00:00",
                    key=f"fixed_sky_time_{selected_key}",
                    help=f"Local time at {site.name} ({site.timezone}).",
                )
                try:
                    sky_clock_time = datetime.strptime(
                        sky_clock_text.strip(), "%H:%M"
                    ).time()
                except ValueError:
                    st.error("Enter time as HH:MM, for example 21:30.")
        use_current_sky_time = st.toggle(
            "Current time",
            key="use_current_time",
            help=(
                "Use the current time and lock the observing date to the current "
                "date at the selected observatory."
            ),
        )
    with twilight_column:
        twilight_placeholder = st.empty()

refresh_intervals = {
    "10 seconds": "10s",
    "30 seconds": "30s",
    "1 minute": "1m",
    "5 minutes": "5m",
}
refresh_interval = refresh_intervals[refresh_label]

observer = site.to_observer()
local_noon = Time(
    datetime.combine(
        observing_date,
        time(12, 0),
        tzinfo=ZoneInfo(site.timezone),
    )
)
try:
    sunset = observer.sun_set_time(local_noon, which="next")
    civil_twilight = observer.twilight_evening_civil(local_noon, which="next")
    nautical_twilight = observer.twilight_evening_nautical(
        local_noon, which="next"
    )
    evening_twilight = observer.twilight_evening_astronomical(
        local_noon, which="next"
    )
    sunset_local = sunset.to_datetime(timezone=ZoneInfo(site.timezone))
    civil_twilight_local = civil_twilight.to_datetime(
        timezone=ZoneInfo(site.timezone)
    )
    nautical_twilight_local = nautical_twilight.to_datetime(
        timezone=ZoneInfo(site.timezone)
    )
    twilight_local = evening_twilight.to_datetime(
        timezone=ZoneInfo(site.timezone)
    )
    evening_times_html = (
        "<div>"
        '<div style="font-weight:600; margin-bottom:0.2rem;">Evening times</div>'
        f'<div>Sunset: {sunset_local.strftime("%H:%M")}</div>'
        f'<div>Civil twilight: {civil_twilight_local.strftime("%H:%M")}</div>'
        f'<div>Nautical twilight: {nautical_twilight_local.strftime("%H:%M")}</div>'
        f'<div>Astronomical twilight: {twilight_local.strftime("%H:%M")}</div>'
        f'<div style="font-size:0.8rem; opacity:0.7;">{site.timezone}</div>'
        "</div>"
    )
except (ValueError, TypeError):
    evening_times_html = (
        "<div>"
        '<div style="font-weight:600;">Evening times</div>'
        "<div>Sunset or astronomical twilight is not defined for this date.</div>"
        "</div>"
    )
twilight_placeholder.markdown(evening_times_html, unsafe_allow_html=True)

if not use_current_sky_time and sky_clock_time is None:
    st.stop()

if not st.session_state.targets:
    st.info("Add at least one target in the sidebar to create a visibility plot.")
    st.stop()

constraints = VisibilityConstraints(
    minimum_altitude=0.0,
    maximum_airmass=float(maximum_airmass),
    minimum_moon_separation=float(minimum_moon_separation),
)
try:
    with st.spinner("Calculating target visibility…"):
        results = [
            cached_visibility(
                target,
                selected_key,
                observing_date,
                float(maximum_airmass),
                float(minimum_moon_separation),
                show_daytime,
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

# The visibility plot reports its selected target through the obs-selected
# query parameter (set by the plot's JavaScript). Resolve it back to a target
# name so the sky plot can emphasize the same target.
selected_target_name = None
selected_param = st.query_params.get("obs-selected")
if selected_param:
    selection_match = re.fullmatch(r"obs-target-(\d+)", selected_param)
    if selection_match:
        selected_index = int(selection_match.group(1))
        if selected_index < len(results):
            selected_target_name = results[selected_index].target.name

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
    "selected_target": selected_target_name,
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
                    selected=context["selected_target"],
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
                selected=selected_target_name,
            )
            st.pyplot(sky_figure, width="stretch")
            plt.close(sky_figure)

st.markdown('<div class="plot-spacer"></div>', unsafe_allow_html=True)


def render_visibility_figure(figure: plt.Figure) -> None:
    """Render an interactive SVG plot beside its scrolling legend."""
    plot_axis = figure.axes[0]
    handles, labels = plot_axis.get_legend_handles_labels()
    entries = [
        (handle, label)
        for handle, label in zip(handles, labels, strict=True)
        if isinstance(handle, Line2D)
        and label
        and not label.startswith("_")
        and not label.startswith("Moon separation <")
    ]
    legend_items = []
    for handle, label in entries:
        line_style = handle.get_linestyle()
        border_style = {
            "--": "dashed",
            ":": "dotted",
            "-.": "dashed",
        }.get(line_style, "solid")
        color = html.escape(str(handle.get_color()), quote=True)
        safe_label = html.escape(label)
        gid = handle.get_gid() or ""
        target_key = gid.rsplit("-", 1)[0] if gid.startswith("obs-target-") else ""
        target_attribute = (
            f' data-target="{html.escape(target_key, quote=True)}"'
            if target_key
            else ""
        )
        legend_items.append(
            f'<div class="legend-item"{target_attribute}>'
            '<span class="legend-swatch" '
            f'style="border-top: 1px {border_style} {color}"></span>'
            f'<span class="legend-label">{safe_label}</span>'
            "</div>"
        )

    svg_buffer = io.StringIO()
    figure.savefig(svg_buffer, format="svg", bbox_inches="tight")
    svg = svg_buffer.getvalue()
    svg = svg[svg.find("<svg") :]
    storage_key = "obsplanner-visibility:" + "|".join(
        f"{handle.get_gid()}={label}"
        for handle, label in entries
        if (handle.get_gid() or "").startswith("obs-target-")
    )
    storage_key_json = json.dumps(storage_key)
    component = f"""
        <style>
            html, body {{ margin: 0; overflow: hidden; }}
            .visibility-layout {{
                display: grid;
                gap: 1rem;
                grid-template-columns: minmax(0, 5fr) minmax(9rem, 1.35fr);
                height: 470px;
            }}
            .plot-panel {{ min-width: 0; }}
            .plot-panel svg {{ display: block; height: auto; width: 100%; }}
            .legend-panel {{
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-radius: 0.5rem;
                box-sizing: border-box;
                height: 460px;
                overflow-y: auto;
                padding: 0.5rem;
            }}
            .legend-item {{
                align-items: center;
                display: flex;
                gap: 0.7rem;
                min-width: 0;
                padding: 0.35rem 0.15rem;
            }}
            .legend-item[data-target] {{ cursor: pointer; }}
            .legend-swatch {{ flex: 0 0 2.2rem; height: 0; }}
            .legend-label {{ line-height: 1.25; overflow-wrap: anywhere; }}
            .legend-item.selected .legend-swatch {{ border-top-width: 2px !important; }}
            .legend-item.selected .legend-label {{ font-weight: 700; }}
            [id^="obs-target-"] path {{ cursor: pointer; pointer-events: stroke; }}
            [id^="obs-target-"].selected path:not(.curve-hit) {{
                stroke-width: 2 !important;
            }}
            .curve-hit {{
                fill: none !important;
                pointer-events: stroke !important;
                stroke: transparent !important;
                stroke-width: 12 !important;
            }}
        </style>
        <div class="visibility-layout">
            <div class="plot-panel">{svg}</div>
            <div class="legend-panel">{"".join(legend_items)}</div>
        </div>
        <script>
            const storageKey = {storage_key_json};
            const syncSelectionParam = (target) => {{
                try {{
                    const parentLocation = window.parent.location;
                    const params = new URLSearchParams(parentLocation.search);
                    if (target) {{
                        if (params.get("obs-selected") === target) return;
                        params.set("obs-selected", target);
                    }} else {{
                        if (!params.has("obs-selected")) return;
                        params.delete("obs-selected");
                    }}
                    window.parent.history.replaceState(
                        null, "",
                        parentLocation.pathname + "?" + params.toString()
                    );
                }} catch (error) {{ /* Sky-plot sync is best-effort. */ }}
            }};
            const targetGroups = Array.from(
                document.querySelectorAll('[id^="obs-target-"]')
            );
            const originalOrders = new Map();
            targetGroups.forEach(group => {{
                if (!originalOrders.has(group.parentElement)) {{
                    originalOrders.set(
                        group.parentElement,
                        Array.from(group.parentElement.children)
                    );
                }}
            }});

            const restoreDrawingOrder = () => {{
                originalOrders.forEach((children, parent) => {{
                    children.forEach(child => parent.appendChild(child));
                }});
            }};

            const selectTarget = (target) => {{
                const selectedLegend = document.querySelector(
                    `.legend-item[data-target="${{target}}"]`
                );
                if (!selectedLegend) return;
                const turnOff = selectedLegend.classList.contains("selected");
                restoreDrawingOrder();
                document.querySelectorAll(".selected").forEach(
                    element => element.classList.remove("selected")
                );
                if (turnOff) {{
                    try {{ window.parent.sessionStorage.removeItem(storageKey); }}
                    catch (error) {{ /* Selection still works without persistence. */ }}
                    syncSelectionParam(null);
                    return;
                }}
                selectedLegend.classList.add("selected");
                document.querySelectorAll(`[id^="${{target}}-"]`).forEach(group => {{
                    group.classList.add("selected");
                    group.parentElement.appendChild(group);
                }});
                try {{ window.parent.sessionStorage.setItem(storageKey, target); }}
                catch (error) {{ /* Selection still works without persistence. */ }}
                syncSelectionParam(target);
            }};

            document.querySelectorAll(".legend-item[data-target]").forEach(item => {{
                item.addEventListener("click", () => selectTarget(item.dataset.target));
            }});
            targetGroups.forEach(group => {{
                const target = group.id.rsplit ? group.id.rsplit("-", 1)[0] :
                    group.id.replace(/-(solid|dashed)$/, "");
                group.querySelectorAll("path").forEach(path => {{
                    const hitArea = path.cloneNode(false);
                    hitArea.removeAttribute("id");
                    hitArea.setAttribute("class", "curve-hit");
                    group.insertBefore(hitArea, path);
                }});
                group.addEventListener("click", () => selectTarget(target));
            }});
            try {{
                const savedTarget = window.parent.sessionStorage.getItem(storageKey);
                if (savedTarget) selectTarget(savedTarget);
            }} catch (error) {{ /* Selection still works without persistence. */ }}
        </script>
    """
    st.iframe(component, width="stretch", height=475)


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
            show_legend=False,
        )
        render_visibility_figure(visibility_figure)
        plt.close(visibility_figure)
    else:
        for panel_index, result in enumerate(plot_results):
            visibility_figure = plot_visibility(
                result,
                plot_constraints,
                context["time_axis"],
                color=target_colors.get(
                    result.target.name, DEFAULT_COLORS[0]
                ),
                show_moon=context["show_moon"],
                current_time=current_time,
                show_legend=False,
                target_index=panel_index,
            )
            render_visibility_figure(visibility_figure)
            plt.close(visibility_figure)


@st.fragment(run_every="1s")
def sync_target_selection():
    """Rerun the app when the visibility plot selection changes.

    The visibility plot writes its selected target to the obs-selected query
    parameter from the browser. Streamlit only notices that change on a
    script run, so this lightweight periodic fragment detects it and asks
    for a full rerun, which lets the sky plot emphasize the same target.
    """
    current_selection = st.query_params.get("obs-selected")
    if current_selection != st.session_state.get("obs_selected_target"):
        if current_selection is None:
            st.session_state.pop("obs_selected_target", None)
        else:
            st.session_state.obs_selected_target = current_selection
        st.rerun(scope="app")


sync_target_selection()
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
