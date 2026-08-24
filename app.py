from __future__ import annotations

import base64
import html
import io
import json
import re
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

import matplotlib.pyplot as plt
import pandas as pd
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
    observing_date_for_local_time,
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
        .target-name {
            cursor: help;
            overflow: visible;
            padding: 0.35rem 0;
            position: relative;
        }
        .target-name .target-tag-tooltip {
            background: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.35);
            border-radius: 0.35rem;
            box-shadow: 0 0.2rem 0.6rem rgba(0, 0, 0, 0.15);
            display: none;
            font-size: 0.8rem;
            left: 0;
            padding: 0.2rem 0.45rem;
            position: absolute;
            top: 90%;
            line-height: 1.35;
            max-width: 18rem;
            min-width: 9rem;
            white-space: normal;
            z-index: 10;
        }
        .target-tag-tooltip div + div {
            margin-top: 0.15rem;
        }
        .observer-clock {
            margin: 0;
        }
        .current-times-title {
            color: var(--text-color);
            font-weight: 600;
            margin-bottom: 0.3rem;
        }
        .st-key-current_times_panel {
            background: rgba(255, 75, 75, 0.10);
            border: 1px solid rgba(49, 51, 63, 0.24);
            border-radius: 0.65rem;
            box-sizing: border-box;
            padding: 0.65rem 0.8rem 0.75rem;
        }
        .st-key-observatory_info_panel {
            border: 1px solid #000000;
            border-radius: 0.65rem;
            box-sizing: border-box;
            padding: 0.65rem 0.8rem 0.75rem;
        }
        .observer-clock-time {
            font-size: 1rem;
            font-variant-numeric: tabular-nums;
            line-height: 1.5rem;
            text-align: left;
            white-space: nowrap;
        }
        .observer-clock-name {
            line-height: 1.5rem;
            white-space: nowrap;
        }
        .st-key-current_times_panel [data-testid="stHorizontalBlock"] {
            align-items: center;
            flex-wrap: nowrap;
            gap: 0.3rem;
            min-height: 1.8rem;
        }
        .st-key-current_times_panel [data-testid="stColumn"] {
            min-width: 0;
        }
        .st-key-current_times_panel [data-testid="stButton"] button {
            justify-content: flex-start;
            min-height: 1.8rem;
            padding-bottom: 0;
            padding-top: 0;
        }
        .st-key-current_times_panel
        [class*="st-key-edit_remote_clock_"] button p {
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            transform: translateY(0.45rem);
            white-space: nowrap;
        }
        .st-key-add_remote_clock_control
        [data-testid="stButton"] button[kind="tertiary"] {
            opacity: 0;
            transition: opacity 0.15s ease-in-out;
        }
        .st-key-current_times_panel:hover
        .st-key-add_remote_clock_control
        [data-testid="stButton"] button[kind="tertiary"] {
            opacity: 1;
        }
        .target-name:hover .target-tag-tooltip {
            display: block;
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

REMOTE_TIMEZONES = tuple(
    sorted(
        timezone_name
        for timezone_name in available_timezones()
        if timezone_name == "UTC"
        or timezone_name.startswith(
            (
                "Africa/",
                "America/",
                "Antarctica/",
                "Asia/",
                "Atlantic/",
                "Australia/",
                "Europe/",
                "Indian/",
                "Pacific/",
            )
        )
    )
)


@st.fragment(run_every="1s")
def render_observer_clock(timezone_name: str) -> None:
    """Render a live HH:MM:SS clock without rerunning visibility work."""
    current_time = datetime.now(ZoneInfo(timezone_name)).strftime("%H:%M:%S")
    st.markdown(
        '<div class="observer-clock">'
        f'<div class="observer-clock-time">{current_time}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def add_remote_clock_slot() -> None:
    """Reveal the next remote-observer time-zone selector."""
    new_index = len(st.session_state.remote_clock_timezones)
    if new_index < 3:
        st.session_state.remote_clock_timezones.append(None)
        st.session_state.remote_clock_editing.add(new_index)


def edit_remote_clock_slot(index: int) -> None:
    """Replace a remote clock's compact label with its search field."""
    st.session_state.remote_clock_editing.add(index)


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


@st.cache_data(show_spinner=False)
def cached_empty_plot_reference(
    observatory_key: str,
    observing_date,
    maximum_airmass: float,
    minimum_moon_separation: float,
    show_daytime: bool,
):
    """Calculate the shared night ephemeris used when no targets are shown."""
    reference_target = parse_coordinate_pair("0, 0", "Sky reference")
    return cached_visibility(
        reference_target,
        observatory_key,
        observing_date,
        maximum_airmass,
        minimum_moon_separation,
        show_daytime,
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
        matching_color = next(
            (
                st.session_state.target_colors.get(existing_target.name)
                for existing_target in st.session_state.targets[:-1]
                if target.tag
                and st.session_state.target_tags.get(
                    existing_target.name, existing_target.tag
                ).strip()
                == target.tag.strip()
            ),
            None,
        )
        st.session_state.target_colors.setdefault(
            target.name,
            matching_color or DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
        )
        st.session_state.target_tags.setdefault(target.name, target.tag)
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
if "target_tags" not in st.session_state:
    st.session_state.target_tags = {}
if "content_page" not in st.session_state:
    st.session_state.content_page = "planner"
if "remote_clock_timezones" not in st.session_state:
    previous_slot_count = st.session_state.get("remote_clock_slots", 0)
    st.session_state.remote_clock_timezones = [
        st.session_state.get(f"remote_observer_timezone_{index}")
        for index in range(previous_slot_count)
    ]
if "remote_clock_editing" not in st.session_state:
    st.session_state.remote_clock_editing = {
        index
        for index, timezone_name in enumerate(
            st.session_state.remote_clock_timezones
        )
        if not timezone_name
    }
if "hidden_tags" not in st.session_state:
    st.session_state.hidden_tags = set()
if "tag_color_groups_initialized" not in st.session_state:
    initial_tag_colors: dict[str, str] = {}
    for target in st.session_state.targets:
        initial_tag = st.session_state.target_tags.get(target.name, target.tag).strip()
        if initial_tag:
            st.session_state.target_colors[target.name] = initial_tag_colors.setdefault(
                initial_tag,
                st.session_state.target_colors.get(target.name, DEFAULT_COLORS[0]),
            )
    st.session_state.tag_color_groups_initialized = True


def apply_color_to_tag(target_name: str) -> None:
    """Apply a changed color to every target sharing a non-empty tag."""
    color = st.session_state[f"target_color_{target_name}"]
    st.session_state.target_colors[target_name] = color
    tag = st.session_state.target_tags.get(target_name, "").strip()
    if not tag:
        return
    for target in st.session_state.targets:
        if st.session_state.target_tags.get(target.name, "").strip() == tag:
            st.session_state.target_colors[target.name] = color
            st.session_state[f"target_color_{target.name}"] = color


def show_target_table() -> None:
    """Switch the main content area to the target-information table."""
    st.session_state.pop("target_information_editor", None)
    st.session_state.content_page = "targets"


def show_planner() -> None:
    """Return the main content area to the visibility planner."""
    st.session_state.content_page = "planner"


def render_target_table_page() -> None:
    """Render and apply the full-page target-information editor."""
    title_column, back_column = st.columns([5, 1], vertical_alignment="center")
    title_column.title("Current targets")
    with back_column:
        st.button("Back to planner", width="stretch", on_click=show_planner)

    st.caption("Edit target information, then apply the changes.")
    target_rows = [
        {
            "name": target.name,
            "ra": target.coord.icrs.ra.deg,
            "dec": target.coord.icrs.dec.deg,
            "tag": st.session_state.target_tags.get(target.name, target.tag),
            "exptime": target.exptime,
            "note": target.note,
        }
        for target in st.session_state.targets
    ]
    edited_targets = st.data_editor(
        pd.DataFrame(
            target_rows,
            columns=("name", "ra", "dec", "tag", "exptime", "note"),
        ),
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        key="target_information_editor",
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "ra": st.column_config.NumberColumn(
                "RA (deg)", required=True, format="%.6f"
            ),
            "dec": st.column_config.NumberColumn(
                "Dec (deg)", required=True, format="%.6f"
            ),
            "tag": st.column_config.TextColumn("Tag"),
            "exptime": st.column_config.TextColumn("Exptime"),
            "note": st.column_config.TextColumn("Note", width="large"),
        },
    )

    st.subheader("Display")
    available_tags = list(
        dict.fromkeys(
            st.session_state.target_tags.get(target.name, target.tag).strip()
            for target in st.session_state.targets
            if st.session_state.target_tags.get(target.name, target.tag).strip()
        )
    )
    if available_tags:
        st.caption("Choose which tagged groups are included in the plots.")
        display_columns = st.columns(min(4, len(available_tags)))
        hidden_tags = set(st.session_state.hidden_tags)
        for tag_index, tag in enumerate(available_tags):
            with display_columns[tag_index % len(display_columns)]:
                show_tag = st.toggle(
                    f"Show {tag}",
                    value=tag not in hidden_tags,
                    key=f"display_tag_{tag_index}_{tag}",
                )
            if show_tag:
                hidden_tags.discard(tag)
            else:
                hidden_tags.add(tag)
        st.session_state.hidden_tags = hidden_tags
    else:
        st.caption("Add tags to targets to control groups here.")

    st.subheader("Colors")
    st.caption("One color is used for each tag; untagged targets are independent.")
    color_groups: dict[tuple[str, str], Target] = {}
    for target in st.session_state.targets:
        tag = st.session_state.target_tags.get(target.name, target.tag).strip()
        group_key = ("tag", tag) if tag else ("target", target.name)
        color_groups.setdefault(group_key, target)
    color_columns = st.columns(min(4, max(1, len(color_groups))))
    for group_index, ((group_type, group_name), target) in enumerate(
        color_groups.items()
    ):
        label = f"Tag: {group_name}" if group_type == "tag" else target.name
        with color_columns[group_index % len(color_columns)]:
            st.color_picker(
                label,
                value=st.session_state.target_colors.get(
                    target.name,
                    DEFAULT_COLORS[group_index % len(DEFAULT_COLORS)],
                ),
                key=f"target_color_{target.name}",
                on_change=apply_color_to_tag,
                args=(target.name,),
            )
    if st.button(
        "Apply target changes",
        type="primary",
        disabled=not st.session_state.targets,
    ):
        try:
            revised_targets: list[Target] = []
            revised_names: set[str] = set()
            revised_colors: dict[str, str] = {}
            revised_tags: dict[str, str] = {}
            for index, row in edited_targets.iterrows():
                old_target = st.session_state.targets[int(index)]
                revised_name = str(row["name"]).strip()
                if not revised_name:
                    raise TargetResolutionError(
                        f"Target row {int(index) + 1} has no name."
                    )
                if revised_name.casefold() in revised_names:
                    raise TargetResolutionError(
                        f"Target name “{revised_name}” is repeated."
                    )
                revised = parse_manual_coordinates(
                    str(row["ra"]),
                    str(row["dec"]),
                    revised_name,
                    decimal_degrees=True,
                )
                revised_tag = (
                    "" if pd.isna(row["tag"]) else str(row["tag"]).strip()
                )
                revised_exptime = (
                    ""
                    if pd.isna(row["exptime"])
                    else str(row["exptime"]).strip()
                )
                revised_note = (
                    "" if pd.isna(row["note"]) else str(row["note"]).strip()
                )
                revised_targets.append(
                    Target(
                        revised.name,
                        revised.coord,
                        revised_tag,
                        revised_exptime,
                        revised_note,
                    )
                )
                revised_names.add(revised_name.casefold())
                revised_colors[revised_name] = st.session_state.target_colors.get(
                    old_target.name, DEFAULT_COLORS[int(index) % len(DEFAULT_COLORS)]
                )
                revised_tags[revised_name] = revised_tag

            colors_by_tag: dict[str, str] = {}
            for revised_target in revised_targets:
                revised_tag = revised_tags[revised_target.name]
                if revised_tag:
                    revised_colors[revised_target.name] = colors_by_tag.setdefault(
                        revised_tag, revised_colors[revised_target.name]
                    )

            old_names = [target.name for target in st.session_state.targets]
            st.session_state.targets = revised_targets
            st.session_state.target_colors = revised_colors
            st.session_state.target_tags = revised_tags
            st.session_state.hidden_tags = set(st.session_state.hidden_tags) & set(
                revised_tags.values()
            )
            for old_name in old_names:
                st.session_state.pop(f"target_color_{old_name}", None)
            st.session_state.pop("target_information_editor", None)
            st.rerun()
        except (TargetResolutionError, TypeError, ValueError) as exc:
            st.error(str(exc))

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
                "Required columns: name, ra, dec. Optional columns: tag, "
                "exptime, note. "
                "Sexagesimal RA uses hours; numeric RA uses decimal degrees."
            ),
        )
        st.caption(
            "Required: `name`, `ra`, `dec` · Optional: `tag`, `exptime`, `note`"
        )
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

    target_heading, edit_targets_column = st.columns(
        [4, 1], vertical_alignment="center"
    )
    target_heading.header(f"Current targets ({len(st.session_state.targets)})")
    with edit_targets_column:
        st.button(
            "☰",
            help="Edit names, coordinates, and tags in the main panel",
            width="stretch",
            on_click=show_target_table,
        )

    target_list = st.container(height=300, border=False)
    with target_list:
        for index, listed_target in enumerate(list(st.session_state.targets)):
            name_column, remove_column = st.columns([4, 1])
            tag = st.session_state.target_tags.setdefault(
                listed_target.name, listed_target.tag
            )
            target_color = st.session_state.target_colors.setdefault(
                listed_target.name, DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
            )
            name_column.markdown(
                '<div class="target-name" '
                f'style="color: {html.escape(target_color, quote=True)}">'
                f"{html.escape(listed_target.name)}"
                '<span class="target-tag-tooltip">'
                f"<div><strong>Tag:</strong> {html.escape(tag or 'None')}</div>"
                "<div><strong>Exptime:</strong> "
                f"{html.escape(listed_target.exptime or 'None')}</div>"
                "<div><strong>Note:</strong> "
                f"{html.escape(listed_target.note or 'None')}</div>"
                "</span></div>",
                unsafe_allow_html=True,
            )
            if remove_column.button(
                "✕",
                key=f"remove_target_{index}_{listed_target.name}",
                help=f"Remove {listed_target.name}",
            ):
                st.session_state.targets.pop(index)
                st.session_state.target_colors.pop(listed_target.name, None)
                st.session_state.target_tags.pop(listed_target.name, None)
                st.rerun()
    if st.session_state.targets and st.button(
        "Clear target list", width="stretch"
    ):
        st.session_state.targets = []
        st.session_state.target_colors = {}
        st.session_state.target_tags = {}
        st.session_state.hidden_tags = set()
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
            "Show the Moon & Sun",
            value=True,
            help=(
                "Show or hide the Moon in the sky plot and the Moon and Sun "
                "altitude curves in the observability plot."
            ),
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

if st.session_state.content_page == "targets":
    render_target_table_page()
    st.stop()

display_targets = [
    target
    for target in st.session_state.targets
    if not st.session_state.target_tags.get(target.name, target.tag).strip()
    or st.session_state.target_tags.get(target.name, target.tag).strip()
    not in st.session_state.hidden_tags
]

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
    observatory_area, clock_column = st.columns(
        [2.35, 1.35], vertical_alignment="top"
    )
    with observatory_area:
        with st.container(key="observatory_info_panel"):
            site_column, twilight_column = st.columns(
                [1.15, 1.2], vertical_alignment="top"
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
            with twilight_column:
                twilight_placeholder = st.empty()

        lower_site_column, _ = st.columns([1.15, 1.2])
        with lower_site_column:
            st.session_state.setdefault("use_current_time", True)
            use_current_sky_time = bool(st.session_state.use_current_time)
            date_column, fixed_time_column = st.columns([1.7, 1])
            with date_column:
                observatory_now = datetime.now(ZoneInfo(site.timezone))
                current_observing_date = observing_date_for_local_time(
                    observatory_now
                )
                observing_date = st.date_input(
                    "Observing date",
                    value=current_observing_date,
                    key=(
                        f"current_observing_date_{selected_key}_"
                        f"{current_observing_date}"
                        if use_current_sky_time
                        else f"observing_date_{selected_key}"
                    ),
                    disabled=use_current_sky_time,
                    help=(
                        f"Evening date of the observing night at {site.name} "
                        f"({site.timezone})."
                    ),
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
                    "Use the current time and lock the observing date to the "
                    "current date at the selected observatory."
                ),
            )
    with clock_column.container(key="current_times_panel"):
        st.markdown(
            '<div class="current-times-title">Current times</div>',
            unsafe_allow_html=True,
        )
        palomar_label, palomar_time = st.columns([1.45, 1])
        palomar_label.markdown(
            '<div class="observer-clock-name">Palomar</div>',
            unsafe_allow_html=True,
        )
        with palomar_time:
            render_observer_clock(catalog["palomar"].timezone)

        utc_label, utc_time = st.columns([1.45, 1])
        utc_label.markdown(
            '<div class="observer-clock-name">UTC</div>',
            unsafe_allow_html=True,
        )
        with utc_time:
            render_observer_clock("UTC")

        for remote_index, saved_timezone in enumerate(
            st.session_state.remote_clock_timezones
        ):
            remote_label, remote_time = st.columns([1.45, 1])
            with remote_label:
                if remote_index in st.session_state.remote_clock_editing:
                    searched_timezone = st.selectbox(
                        f"Remote observer {remote_index + 1} time zone",
                        REMOTE_TIMEZONES,
                        index=None,
                        placeholder=(
                            saved_timezone.replace("_", " ")
                            if saved_timezone
                            else "Search time zone"
                        ),
                        format_func=lambda timezone_name: timezone_name.replace(
                            "_", " "
                        ),
                        label_visibility="collapsed",
                        key=f"remote_timezone_search_{remote_index}",
                    )
                    if searched_timezone:
                        st.session_state.remote_clock_timezones[
                            remote_index
                        ] = searched_timezone
                        st.session_state.remote_clock_editing.discard(remote_index)
                        st.rerun()
                elif saved_timezone:
                    st.button(
                        saved_timezone.replace("_", " "),
                        key=f"edit_remote_clock_{remote_index}",
                        help="Change this remote observer time zone",
                        type="tertiary",
                        on_click=edit_remote_clock_slot,
                        args=(remote_index,),
                    )
            if saved_timezone:
                with remote_time:
                    render_observer_clock(saved_timezone)

        can_add_remote = (
            not st.session_state.remote_clock_timezones
            or bool(st.session_state.remote_clock_timezones[-1])
        )
        if len(st.session_state.remote_clock_timezones) < 3 and can_add_remote:
            with st.container(key="add_remote_clock_control"):
                st.button(
                    "＋",
                    key=(
                        "add_remote_clock_"
                        f"{len(st.session_state.remote_clock_timezones)}"
                    ),
                    help="Add a remote observer time",
                    type="tertiary",
                    on_click=add_remote_clock_slot,
                )

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
        f'<div>Naut. twilight: {nautical_twilight_local.strftime("%H:%M")}</div>'
        f'<div>Astro. twilight: {twilight_local.strftime("%H:%M")}</div>'
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
            for target in display_targets
        ]
        reference_result = (
            results[0]
            if results
            else cached_empty_plot_reference(
                selected_key,
                observing_date,
                float(maximum_airmass),
                float(minimum_moon_separation),
                show_daytime,
            )
        )
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
    "reference_result": reference_result,
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
                display_targets,
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
    handles = []
    labels = []
    for axis in figure.axes:
        axis_handles, axis_labels = axis.get_legend_handles_labels()
        handles.extend(axis_handles)
        labels.extend(axis_labels)
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
        selectable_gid = gid.startswith(("obs-target-", "obs-body-"))
        target_key = gid.rsplit("-", 1)[0] if selectable_gid else ""
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
        if (handle.get_gid() or "").startswith(("obs-target-", "obs-body-"))
    )
    storage_key_json = json.dumps(storage_key)
    component = f"""
        <style>
            html, body {{ margin: 0; overflow: hidden; }}
            .visibility-layout {{
                align-items: stretch;
                display: grid;
                gap: 1rem;
                grid-template-columns: minmax(0, 5fr) minmax(9rem, 1.35fr);
            }}
            .plot-panel {{ min-width: 0; }}
            .plot-panel svg {{ display: block; height: auto; width: 100%; }}
            .legend-slot {{ min-height: 0; position: relative; }}
            .legend-panel {{
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-radius: 0.5rem;
                box-sizing: border-box;
                inset: 0;
                overflow-y: auto;
                padding: 0.5rem;
                position: absolute;
            }}
            .legend-search-row {{
                background: white;
                padding: 0 0 0.5rem;
                position: sticky;
                top: 0;
                z-index: 2;
            }}
            .legend-search {{
                border: 1px solid rgba(49, 51, 63, 0.25);
                border-radius: 0.35rem;
                box-sizing: border-box;
                color: inherit;
                font: inherit;
                padding: 0.38rem 0.5rem;
                width: 100%;
            }}
            .legend-search:focus {{
                border-color: #ff4b4b;
                outline: 1px solid #ff4b4b;
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
            .legend-item.selected .legend-swatch {{
                border-top-color: #ffea00 !important;
                border-top-width: 4px !important;
                filter: drop-shadow(0 0 1px #333);
            }}
            .legend-item.selected .legend-label {{ font-weight: 700; }}
            [id^="obs-target-"] path,
            [id^="obs-body-"] path {{ cursor: pointer; pointer-events: stroke; }}
            [id^="obs-target-"].selected path:not(.curve-hit),
            [id^="obs-body-"].selected path:not(.curve-hit) {{
                filter: drop-shadow(0 0 1px #333);
                stroke: #ffea00 !important;
                stroke-width: 4 !important;
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
            <div class="legend-slot">
                <div class="legend-panel">
                    <div class="legend-search-row">
                        <input class="legend-search" type="search"
                            placeholder="Search target, press Enter…"
                            aria-label="Search target">
                    </div>
                    {"".join(legend_items)}
                </div>
            </div>
        </div>
        <script>
            const storageKey = {storage_key_json};
            const scrollStorageKey = storageKey + ":legend-scroll";
            const legendPanel = document.querySelector(".legend-panel");
            const searchInput = document.querySelector(".legend-search");
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
            const selectableGroups = Array.from(
                document.querySelectorAll('[id^="obs-target-"], [id^="obs-body-"]')
            );
            const originalOrders = new Map();
            selectableGroups.forEach(group => {{
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

            const selectTarget = (target, forceSelect = false) => {{
                const selectedLegend = document.querySelector(
                    `.legend-item[data-target="${{target}}"]`
                );
                if (!selectedLegend) return;
                const turnOff = selectedLegend.classList.contains("selected")
                    && !forceSelect;
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

            const saveLegendScroll = () => {{
                try {{
                    window.parent.sessionStorage.setItem(
                        scrollStorageKey, String(legendPanel.scrollTop)
                    );
                }} catch (error) {{ /* Scrolling still works without persistence. */ }}
            }};
            legendPanel.addEventListener("scroll", saveLegendScroll, {{ passive: true }});
            window.addEventListener("beforeunload", saveLegendScroll);
            try {{
                const savedScroll = window.parent.sessionStorage.getItem(scrollStorageKey);
                if (savedScroll !== null) legendPanel.scrollTop = Number(savedScroll);
            }} catch (error) {{ /* Scrolling still works without persistence. */ }}

            const searchTargets = () => {{
                const query = searchInput.value.trim().toLocaleLowerCase();
                if (!query) return;
                const targetItems = Array.from(document.querySelectorAll(
                    '.legend-item[data-target^="obs-target-"]'
                ));
                const exactMatch = targetItems.find(item =>
                    item.querySelector(".legend-label").textContent.trim()
                        .toLocaleLowerCase() === query
                );
                const match = exactMatch || targetItems.find(item =>
                    item.querySelector(".legend-label").textContent
                        .toLocaleLowerCase().includes(query)
                );
                if (!match) {{
                    searchInput.setCustomValidity("No matching target");
                    searchInput.reportValidity();
                    return;
                }}
                searchInput.setCustomValidity("");
                selectTarget(match.dataset.target, true);
                legendPanel.scrollTop = Math.max(
                    0,
                    match.offsetTop - (legendPanel.clientHeight - match.offsetHeight) / 2
                );
                saveLegendScroll();
            }};
            searchInput.addEventListener("input", () => searchInput.setCustomValidity(""));
            searchInput.addEventListener("keydown", event => {{
                if (event.key === "Enter") {{
                    event.preventDefault();
                    searchTargets();
                }}
            }});

            document.querySelectorAll(".legend-item[data-target]").forEach(item => {{
                item.addEventListener("click", () => selectTarget(item.dataset.target));
            }});
            selectableGroups.forEach(group => {{
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
    st.iframe(component, width="stretch", height="content")


@st.fragment(run_every=refresh_interval)
def render_visibility_plots():
    context = st.session_state.active_plot_context
    plot_results = context["results"]
    plot_constraints = context["constraints"]
    target_colors = context["target_colors"]
    current_time = Time.now()
    if context["plot_mode"] == "Combined panel" or not plot_results:
        visibility_figure = plot_combined_visibility(
            plot_results or [context["reference_result"]],
            plot_constraints,
            context["time_axis"],
            colors=target_colors,
            show_moon=context["show_moon"],
            current_time=current_time,
            show_legend=False,
            include_targets=bool(plot_results),
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
