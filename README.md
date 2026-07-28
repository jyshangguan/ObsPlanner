# ObsPlanner

ObsPlanner is a small Streamlit application for planning astronomical
observations. Search for a target with SIMBAD or enter coordinates, choose an
observatory and date, and inspect the target's altitude, airmass, and useful
observing windows.

The bundled catalog includes Paranal, La Silla, Palomar, Las Campanas, and
other major observing sites around the world.

## Features

- SIMBAD target-name resolution
- Sexagesimal or decimal manual coordinates
- Persistent target list with individual entry, CSV import, and removal
- Combined multi-target plot with an individual color picker for every target
- Separate-panel mode using the full single-target presentation
- Fifteen built-in observatory locations with local time-zone support
- Adjustable maximum-airmass and Moon-separation constraints
- Five-minute sampling of the astronomical night
- Rise, transit, set, altitude, airmass, and observing-window summaries
- One visibility curve with airmass on the left and the equivalent nonlinear
  altitude scale on the right, plus civil, nautical, astronomical twilight,
  and night shading
- Moon altitude shown as a light-yellow dashed curve
- Observing date and midpoint Moon illuminated fraction in the plot title
- Observatory in the plot title and target name in the curve legend
- Sidebar toggle for showing or hiding the Moon curve
- Solid target curve where the Moon-separation constraint passes and dashed
  target curve where it fails
- Compact observing details inside the plot and line legend outside its right
  axis, keeping the chart visible without page scrolling
- Selectable local-time, UTC, or apparent local sidereal time (LST) plot axis

## Install

ObsPlanner requires Python 3.11 or newer.

The development environment is named `observations`:

```bash
conda create -n observations python=3.12 pip
conda activate observations
python -m pip install -e ".[test]"
```

Or use a standard virtual environment:

```bash
git clone <repository-url>
cd ObsPlanner
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

Alternatively, install the runtime packages with:

```bash
python -m pip install -r requirements.txt
```

## Run

From the repository root:

```bash
streamlit run app.py
```

The app opens in a browser. Try resolving `NGC 3783`, or select manual
coordinates and enter:

```text
RA:  11:39:01
Dec: -37:44:20
```

Right ascension is interpreted as hours in sexagesimal mode; declination is in
degrees. Decimal mode interprets both fields as degrees.

### CSV target catalogs

Upload a CSV containing the required `name`, `ra`, and `dec` columns:

```csv
name,ra,dec
NGC 3783,11:39:01,-37:44:20
PDS 456,262.0825,-14.9322
```

RA values containing colons or hour-angle letters are interpreted as
sexagesimal hours. Numeric RA values are interpreted as decimal degrees.
Target names must be unique.

In **Combined panel** mode, each target has its own sidebar color picker. In
**Separate panels** mode, every target is rendered with the complete
single-target chart.

## Time and constraints

The selected date denotes the observing night beginning on that local calendar
date. Astronomy calculations use UTC internally, while results are displayed
in the selected observatory's local IANA time zone and in UTC.

A time is marked observable when all of the following are true:

- the Sun is below −18 degrees;
- the target is above the horizon;
- target airmass is below the selected maximum; and
- target–Moon separation is above the selected minimum.

Window boundaries have five-minute precision. At high-latitude sites and dates
where astronomical twilight is undefined, ObsPlanner falls back to 18:00–06:00
local time and still applies the Sun-altitude constraint.

## Test

```bash
pytest
```

External SIMBAD access is not required by the tests.

## Notes

ObsPlanner is an observation-planning aid. Verify visibility, weather,
instrument limits, and facility-specific requirements with the observatory
before executing an observation.

See [PROJECT_SPEC.md](PROJECT_SPEC.md) for the intended scope and future
extensions.
