# ObsPlanner

ObsPlanner is a personal astronomical observation-planning application for
checking when celestial targets are visible from major observatories around
the world.

The first release should be a minimal, usable Streamlit application backed by
Astroplan and Astropy. The design should remain general-purpose and must not be
tied to a particular instrument, telescope, or observing program.

## Goals

Users should be able to:

1. Resolve an astronomical target by name.
2. Enter target coordinates manually.
3. Build and edit a list of targets one by one.
4. Import targets from a CSV containing names and coordinates.
5. Select an observatory.
6. Select an observing date.
7. Adjust basic observing constraints.
8. Plot all targets together with individually selected colors.
9. Plot each target separately using the full single-target format.

## Scope of the minimal release

The first implementation should include:

- A Streamlit graphical interface.
- Target-name resolution through SIMBAD.
- Manual right ascension and declination input.
- A persistent target list with add, remove, and clear actions.
- CSV import using required `name`, `ra`, and `dec` columns.
- Combined-panel and separate-panel multi-target presentation modes.
- Per-target color controls in combined-panel mode.
- An observatory catalog stored outside the application code.
- A configurable observing date.
- Adjustable maximum airmass and minimum Moon separation.
- A five-minute time grid covering sunset, all twilight stages, astronomical
  night, and sunrise.
- Altitude, azimuth, airmass, and Moon-separation calculations.
- Rise, set, and meridian-transit information where those events exist.
- A combined altitude/airmass plot with daylight, twilight, and night context.
- A calculated observing window satisfying all selected constraints.
- Clear messages for invalid input, failed name resolution, polar targets,
  targets that never rise, and nights without astronomical twilight.

The initial release does not need:

- Multi-target scheduling or optimization.
- User accounts or persistent storage.
- Telescope- or instrument-specific constraints.
- Automatic calibrator selection.
- A separate web API.
- Deployment infrastructure.

## Technology

- Python 3.11 or newer
- Streamlit
- Astroplan
- Astropy
- Astroquery
- Matplotlib
- NumPy
- Pandas
- PyYAML

Dependencies should be declared in `pyproject.toml`. A `requirements.txt` may
also be supplied if it makes local Streamlit deployment easier.

## Proposed project structure

```text
ObsPlanner/
├── app.py
├── PROJECT_SPEC.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── data/
│   └── observatories.yaml
├── src/
│   └── obsplanner/
│       ├── __init__.py
│       ├── targets/
│       │   ├── __init__.py
│       │   ├── resolver.py
│       │   └── target.py
│       ├── observatories/
│       │   ├── __init__.py
│       │   └── sites.py
│       ├── visibility/
│       │   ├── __init__.py
│       │   ├── calculator.py
│       │   └── constraints.py
│       └── plotting/
│           ├── __init__.py
│           └── plots.py
└── tests/
    ├── test_observatories.py
    ├── test_targets.py
    └── test_visibility.py
```

Keep the modules small and focused. Astronomy calculations, external name
resolution, plotting, and Streamlit presentation should not be mixed together.

## Target input

The sidebar maintains a target list. Target names are unique within that list.
Users can remove individual entries or clear the list.

The sidebar should offer two input modes.

### Resolve by name

The user enters a catalog or common name such as `NGC 3783`. Resolve it through
SIMBAD using `astroquery.simbad`, then convert the result to an Astropy
`SkyCoord`.

Name resolution requires network access. Failures should produce a helpful
message and should not crash the application.

### Manual coordinates

The user enters:

- Right ascension
- Declination
- An optional display name

At minimum, support sexagesimal input such as:

```text
RA:  11:39:01
Dec: -37:44:20
```

Clearly label RA as hours and Dec as degrees. If practical, also accept decimal
degrees through an explicit coordinate-format selector. Validate all values
before calculating visibility.

Internally, both input modes should produce the same target model containing a
name and `SkyCoord`.

### CSV coordinates

CSV files require case-insensitive `name`, `ra`, and `dec` columns.
Sexagesimal RA values containing colons or hour-angle letters are interpreted
as hours. Numeric RA values are interpreted as decimal degrees. Invalid rows
must identify their CSV row number in the error message.

## Observatory catalog

Observatory definitions must be stored in `data/observatories.yaml`, not
hard-coded in Python. Each entry should contain:

- Display name
- Latitude in decimal degrees
- Longitude in decimal degrees, positive east
- Elevation in metres
- IANA time-zone name
- Optional aliases or short description

The catalog must include at least:

- Paranal Observatory
- La Silla Observatory
- Palomar Observatory
- Las Campanas Observatory
- Mauna Kea Observatories
- W. M. Keck Observatory
- Gemini North
- Gemini South
- Cerro Tololo Inter-American Observatory
- Atacama Large Millimeter/submillimeter Array (ALMA)
- Kitt Peak National Observatory
- Apache Point Observatory
- Lick Observatory
- Siding Spring Observatory
- South African Astronomical Observatory (Sutherland)

Coordinates and elevations should be verified against authoritative sources
when the catalog is implemented. Multiple facilities at one site may share a
location, but should have clear labels.

Loading a catalog entry should construct an Astropy `EarthLocation` and an
Astroplan `Observer`, including the site's time zone.

## Date and time behavior

The user selects a calendar date interpreted as the start of the observing
night at the observatory. Default to the current date.

The calculation should:

1. Determine evening and morning astronomical twilight for the selected site.
2. Sample the night at five-minute intervals by default.
3. Fall back to a clearly documented time range if astronomical twilight is
   absent or cannot be calculated.
4. Perform astronomy calculations with Astropy `Time` in UTC.
5. Display local observatory time prominently, with UTC available for clarity.

Time-zone and daylight-saving handling should use the observatory's IANA
time-zone identifier rather than a fixed UTC offset.

## Constraints

Expose these controls in the sidebar:

- Maximum airmass, default 2.0.
- Minimum Moon separation, default 30 degrees.

A time sample is observable only when all enabled constraints pass and the Sun
is below astronomical twilight. The implementation should make it easy to add
more constraints later.

Maximum airmass is the sole geometric visibility limit. The equivalent
altitude remains readable from the linked plot axis.

## Visibility calculations

For every time sample, calculate:

- Altitude
- Azimuth
- Secant-zenith airmass
- Angular separation from the Moon
- Whether each configured constraint passes
- Whether all constraints pass

Also calculate, where defined:

- Target rise time
- Target set time
- Meridian transit time
- Maximum altitude during the sampled night
- Minimum finite airmass during the sampled night

Airmass values at or below the horizon should be treated as unavailable, not
shown as meaningful numerical values.

### Observing windows

Find contiguous runs of samples that satisfy all constraints. Present the
longest useful window in the summary and, if simple to implement, list all
valid windows. Window boundaries may initially use the sample cadence; the UI
should make this precision clear.

If no samples satisfy the constraints, state that the target is not observable
under the selected conditions.

## Streamlit interface

### Sidebar

Include:

- Target-input mode selector
- Target name or manual-coordinate fields
- One-by-one versus CSV-import selector
- Current target list with removal controls
- One color picker per target in combined mode
- Observing-date picker
- Maximum-airmass control
- Minimum-Moon-separation control
- Plot time-axis selector for local time, UTC, or apparent LST
- Toggle for showing or hiding the Moon-altitude curve

### Main page

Show:

1. Observatory and combined/separate plot-layout selectors in a compact top row.
2. One combined altitude and airmass plot as the dominant initial view.
3. A compact in-plot annotation containing only the selected Moon separation.
4. A line legend outside the right altitude axis.
5. A background-color explanation below the plot.
6. Any warnings or exceptional conditions below the plot.

The application should be usable on a normal laptop display. Prefer a clear
layout and informative defaults over extensive customization.

## Plots

Use Matplotlib for the minimal release.

### Combined visibility plot

- Selectable horizontal axis: local civil time, UTC, or apparent local
  sidereal time (LST).
- Left vertical axis: airmass, with lower airmass visually higher.
- Right vertical axis: the equivalent altitude derived from
  `airmass = sec(z) = 1 / sin(altitude)`.
- Plot one target-visibility curve that can be read against either scale.
- Plot Moon altitude as a light-yellow dashed curve against the altitude scale.
- Show the observing date and the Moon illuminated fraction at the midpoint of
  the observing night together with the observatory name in the plot title.
- Use the target name as the solid target-curve legend label.
- Draw the target curve solid where the selected Moon-separation constraint
  passes and dashed where it fails; do not use observability point markers.
- Show the selected Moon-separation limit in the information box, not as a
  separate dashed-curve legend entry.
- Plot finite, above-horizon values without allowing extreme near-horizon
  airmass to dominate the scale.
- Show the maximum-airmass threshold.
- Distinguish daylight, civil twilight, nautical twilight, astronomical
  twilight, and astronomical night using background shading.
- Highlight samples satisfying all constraints.
- Do not show a twilight-color legend inside the plot; explain the background
  colors immediately below it.

Plots should return Matplotlib figure objects and should not directly call
Streamlit, which keeps plotting independently testable.

## Error handling

The app should handle these cases without an unhandled exception:

- Empty or malformed coordinates.
- Unknown target name.
- SIMBAD or network failure.
- Invalid observatory data.
- Target never rises or is circumpolar.
- No astronomical night at the selected location and date.
- No observing window under the selected constraints.
- Missing or stale Astropy site data.

Avoid downloading Astropy's observatory registry at runtime; ObsPlanner's YAML
catalog is the source of truth for supported sites.

## Testing

Add focused unit tests for:

- Loading and validating all observatory entries.
- Parsing manual sexagesimal coordinates.
- Converting a catalog entry to `Observer`.
- Producing correctly shaped visibility arrays.
- Applying altitude, airmass, Moon-separation, and night constraints.
- Detecting contiguous observing windows.
- A known target/site/date sanity check.

Mock external SIMBAD queries so the automated test suite does not require
network access.

## Documentation

The README should contain:

- What ObsPlanner does.
- A screenshot or interface description.
- Installation instructions.
- The command to run the app:

  ```bash
  streamlit run app.py
  ```

- Examples for name resolution and manual coordinates.
- An explanation of time zones and constraints.
- A note that predictions are planning aids and should be checked against the
  requirements of the relevant facility.

## Acceptance criteria

The minimal release is complete when a user can:

1. Install the declared dependencies in a clean Python environment.
2. Start ObsPlanner with `streamlit run app.py`.
3. Select Paranal, La Silla, Palomar, or Las Campanas.
4. Resolve `NGC 3783` by name when network access is available, or enter its
   coordinates manually.
5. Select a date and adjust the three constraints.
6. See a correct altitude curve, usable airmass curve, and night context.
7. See whether and when the target satisfies all constraints.
8. Receive a helpful UI message instead of a crash for invalid input or an
   unavailable name-resolution service.

## Future extensions

The architecture should leave room for:

- Result export.
- Multi-target comparison and ranking.
- Batch visibility calculations.
- Nightly scheduling and optimization.
- Additional solar, lunar, weather, and sky-brightness constraints.
- Telescope- and instrument-specific constraints.
- Interactive plots.
- Saved custom observatories.
- Calibrator searches.
- Command-line and API interfaces sharing the same calculation engine.

These are future directions and should not complicate the first usable
implementation.
