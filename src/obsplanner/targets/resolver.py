from __future__ import annotations

import threading

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astroquery.simbad import Simbad
from astroquery.simbad import conf as simbad_conf

from .target import Target

#: Backup SIMBAD mirrors queried automatically when the primary server
#: (astroquery's configured server, the CDS site in Strasbourg) is
#: unreachable or too slow. Mirrors are tried in the listed order.
SIMBAD_BACKUP_SERVERS = ("simbad.cfa.harvard.edu",)

#: Seconds to wait for one SIMBAD mirror before moving on to the next
#: one. pyvo submits TAP queries without a request timeout, so a
#: hanging server would otherwise block resolution forever.
SIMBAD_QUERY_TIMEOUT = 60.0


class TargetResolutionError(ValueError):
    """Raised when a target cannot be parsed or resolved."""


def _set_simbad_server(server: str) -> bool:
    """Point the shared astroquery SIMBAD client at ``server``.

    Returns ``True`` when the client is left using ``server``. Releases
    of astroquery without mirror support keep their configured server
    and report ``False`` instead.
    """
    try:
        if Simbad.server == server:
            return True
        servers_list = getattr(simbad_conf, "servers_list", None)
        if isinstance(servers_list, list) and server not in servers_list:
            servers_list.append(server)
        Simbad.server = server
        return Simbad.server == server
    except (AttributeError, ValueError, TypeError):
        return False


def _simbad_servers() -> list[str]:
    """Mirrors to query: the current one, the configured one, then backups.

    The mirror that answered the last query comes first, so a successful
    fallback sticks for later queries. The configured primary stays in
    the list, so a recovered primary is used again once the current
    mirror fails.
    """
    candidates: list[str] = []
    try:
        current = Simbad.server
    except (AttributeError, ValueError, TypeError):
        current = None
    for server in (
        current,
        getattr(simbad_conf, "server", None),
        *SIMBAD_BACKUP_SERVERS,
    ):
        if server and server not in candidates:
            candidates.append(server)
    return candidates


def _run_with_timeout(query, timeout: float):
    """Run ``query()`` and return its result, re-raising any exception.

    Raises ``TimeoutError`` when the call takes longer than ``timeout``
    seconds. The abandoned call keeps running on a daemon thread so a
    hanging server cannot block the fallback or the application.
    """
    outcome: dict[str, object] = {}

    def _query() -> None:
        try:
            outcome["result"] = query()
        except BaseException as exc:  # re-raised on the calling thread
            outcome["error"] = exc

    worker = threading.Thread(target=_query, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"no reply within {timeout:g} seconds")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


def _query_simbad(name: str) -> Table:
    """Query SIMBAD for ``name`` with automatic mirror fallback.

    Mirrors from :func:`_simbad_servers` are queried in turn until one
    answers. An empty result is an authoritative "no such object"
    answer and is not retried on the other mirrors.
    """
    failures: list[str] = []
    last_error: Exception | None = None

    for server in _simbad_servers():
        if not _set_simbad_server(server):
            # astroquery without mirror support: the first iteration
            # queries the configured server; later ones cannot change it.
            if failures:
                break
            label = "configured server"
        else:
            label = server
        try:
            result = _run_with_timeout(
                lambda: Simbad.query_object(name), SIMBAD_QUERY_TIMEOUT
            )
        except Exception as exc:
            failures.append(f"{label} ({exc.__class__.__name__})")
            last_error = exc
            continue
        if result is None or len(result) == 0:
            raise TargetResolutionError(f"SIMBAD found no target named “{name}”.")
        return result

    raise TargetResolutionError(
        "SIMBAD could not be reached (tried "
        + ", ".join(failures)
        + "). Check your network connection or enter coordinates manually."
    ) from last_error


def resolve_target(name: str) -> Target:
    """Resolve a target name with SIMBAD.

    The primary SIMBAD server is queried first; if it is unreachable or
    too slow, the mirrors in ``SIMBAD_BACKUP_SERVERS`` (the Harvard CfA
    mirror) are tried automatically.
    """
    clean_name = name.strip()
    if not clean_name:
        raise TargetResolutionError("Enter a target name.")

    result = _query_simbad(clean_name)

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


def parse_coordinate_pair(coordinates: str, name: str = "Manual target") -> Target:
    """Parse a comma-separated RA and Dec pair, inferring the RA format."""
    parts = [part.strip() for part in coordinates.split(",")]
    if len(parts) != 2 or not all(parts):
        raise TargetResolutionError(
            "Enter coordinates as a comma-separated pair: RA, Dec."
        )
    ra, dec = parts
    normalized_ra = ra.lower()
    sexagesimal_ra = ":" in normalized_ra or any(
        marker in normalized_ra for marker in ("h", "m", "s")
    )
    return parse_manual_coordinates(
        ra,
        dec,
        name,
        decimal_degrees=not sexagesimal_ra,
    )
