# ObsPlanner

ObsPlanner is a small Streamlit application for planning astronomical
observations. Search for a target with SIMBAD or enter coordinates, choose an
observatory and date, and inspect the target's altitude, airmass, and useful
observing windows.

The bundled catalog includes Paranal, La Silla, Palomar, Las Campanas, and
other major observing sites around the world.

## Download

The current release is **ObsPlanner 0.1.2**.

[Download ObsPlanner 0.1.2 for macOS (Apple Silicon, ZIP)](https://github.com/jyshangguan/ObsPlanner/releases/download/v0.1.2/ObsPlanner-0.1.2-macOS-arm64.zip)

The macOS application is self-contained: Conda, Python, and the source
repository are not required. Extract the ZIP, move `ObsPlanner.app` to
`Applications`, and open it. This build requires an Apple Silicon Mac and
macOS 12 or newer.

The initial release is not notarized. If macOS blocks the first launch,
Control-click `ObsPlanner.app`, choose **Open**, and confirm that you want to
run it.

## Features

- SIMBAD target-name resolution
- Sexagesimal or decimal manual coordinates
- Persistent target list with individual entry, CSV import, and removal
- Combined multi-target plot with an individual color picker for every target
- Time-selectable local sky plot with color-matched markers and labels for every target
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

## macOS desktop development

ObsPlanner includes a cross-platform desktop launcher that runs Streamlit on a
private loopback port and displays it in a native pywebview window.

Install the desktop dependencies in the development environment:

```bash
conda activate observations
python -m pip install -e ".[test,desktop]"
```

Run the native development window:

```bash
obsplanner-desktop
```

For a server-lifecycle smoke test without opening a window:

```bash
obsplanner-desktop --server-only
```

The URL printed by the server-only command is bound to `127.0.0.1` and changes
on every launch. Closing the native window terminates the embedded Streamlit
server.

### Build the macOS app

On an Apple Silicon Mac:

```bash
conda activate observations
./packaging/macos/build_macos.sh
```

The application bundle is written to:

```text
dist/ObsPlanner.app
```

It can be launched from Finder or with:

```bash
open dist/ObsPlanner.app
```

To apply an ad-hoc signature for local testing:

```bash
OBSPLANNER_ADHOC_SIGN=1 ./packaging/macos/build_macos.sh
```

The v0.1.2 ZIP release uses the locally signed build and is not Apple-notarized.
A future warning-free public distribution should use a Developer ID
Application certificate, Apple notarization, and a stapled ticket. Signing
credentials must remain in the developer keychain or CI secrets and must not
be committed.

Desktop logs are written under the platform's normal user log directory. On
macOS this is:

```text
~/Library/Logs/ObsPlanner/
```

The launcher and path logic are shared across platforms. Linux and Windows will
use platform-specific packaging configurations in later releases.

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
