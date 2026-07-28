from __future__ import annotations

import astropy.units as u
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad

from .target import Target


class TargetResolutionError(ValueError):
    """Raised when a target cannot be parsed or resolved."""


def resolve_target(name: str) -> Target:
    """Resolve a target name with SIMBAD."""
    clean_name = name.strip()
    if not clean_name:
        raise TargetResolutionError("Enter a target name.")

    try:
        result = Simbad.query_object(clean_name)
    except Exception as exc:
        raise TargetResolutionError(
            "SIMBAD could not be reached. Check your network connection or "
            "enter coordinates manually."
        ) from exc

    if result is None or len(result) == 0:
        raise TargetResolutionError(f"SIMBAD found no target named “{clean_name}”.")

    try:
        columns = set(result.colnames)
        if {"ra", "dec"} <= columns:
            coord = SkyCoord(
                ra=float(result["ra"][0]) * u.deg,
                dec=float(result["dec"][0]) * u.deg,
                frame="icrs",
            )
        else:
            coord = SkyCoord(
                str(result["RA"][0]),
                str(result["DEC"][0]),
                unit=(u.hourangle, u.deg),
                frame="icrs",
            )
    except Exception as exc:
        raise TargetResolutionError(
            f"SIMBAD returned coordinates that could not be read for “{clean_name}”."
        ) from exc

    return Target(name=clean_name, coord=coord)


def parse_manual_coordinates(
    ra: str,
    dec: str,
    name: str = "Manual target",
    *,
    decimal_degrees: bool = False,
) -> Target:
    """Parse manual ICRS coordinates."""
    if not ra.strip() or not dec.strip():
        raise TargetResolutionError("Enter both right ascension and declination.")

    try:
        if decimal_degrees:
            coord = SkyCoord(
                ra=float(ra) * u.deg,
                dec=float(dec) * u.deg,
                frame="icrs",
            )
        else:
            coord = SkyCoord(
                ra.strip(),
                dec.strip(),
                unit=(u.hourangle, u.deg),
                frame="icrs",
            )
    except (TypeError, ValueError) as exc:
        expected = (
            "decimal degrees" if decimal_degrees else "sexagesimal RA and Dec"
        )
        raise TargetResolutionError(
            f"Could not parse the coordinates. Expected {expected}."
        ) from exc

    clean_name = name.strip() or "Manual target"
    return Target(name=clean_name, coord=coord)
