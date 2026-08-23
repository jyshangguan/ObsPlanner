from __future__ import annotations

from io import BytesIO, StringIO
from typing import IO

import pandas as pd

from .resolver import TargetResolutionError, parse_manual_coordinates
from .target import Target


def _uses_sexagesimal_ra(value: str) -> bool:
    normalized = value.lower()
    return ":" in normalized or any(marker in normalized for marker in ("h", "m", "s"))


def parse_target_csv(
    source: str | bytes | IO[str] | IO[bytes],
) -> list[Target]:
    """Parse a CSV catalog with optional tag, exptime, and note columns.

    Numeric RA is interpreted as decimal degrees. RA containing a colon or
    hour-angle letters is interpreted as sexagesimal hours.
    """
    if isinstance(source, bytes):
        readable = BytesIO(source)
    elif isinstance(source, str):
        readable = StringIO(source)
    else:
        readable = source

    try:
        table = pd.read_csv(readable, dtype=str)
    except Exception as exc:
        raise TargetResolutionError("The uploaded file is not a readable CSV.") from exc

    table.columns = [str(column).strip().lower() for column in table.columns]
    required = {"name", "ra", "dec"}
    missing = required - set(table.columns)
    if missing:
        raise TargetResolutionError(
            "CSV is missing required columns: "
            + ", ".join(sorted(missing))
            + "."
        )
    if table.empty:
        raise TargetResolutionError("The uploaded CSV contains no targets.")

    targets: list[Target] = []
    seen_names: set[str] = set()
    for index, row in table.iterrows():
        row_number = int(index) + 2
        name = str(row["name"]).strip()
        ra = str(row["ra"]).strip()
        dec = str(row["dec"]).strip()
        if not name or name.lower() == "nan":
            raise TargetResolutionError(f"CSV row {row_number} has no target name.")
        if name.casefold() in seen_names:
            raise TargetResolutionError(
                f"CSV row {row_number} repeats target name “{name}”."
            )
        if not ra or not dec or ra.lower() == "nan" or dec.lower() == "nan":
            raise TargetResolutionError(
                f"CSV row {row_number} must contain both RA and Dec."
            )
        try:
            target = parse_manual_coordinates(
                ra,
                dec,
                name,
                decimal_degrees=not _uses_sexagesimal_ra(ra),
            )
        except TargetResolutionError as exc:
            raise TargetResolutionError(
                f"CSV row {row_number} ({name}): {exc}"
            ) from exc
        optional_values: dict[str, str] = {}
        for column in ("tag", "exptime", "note"):
            value = ""
            if column in table.columns:
                raw_value = str(row[column]).strip()
                if raw_value and raw_value.lower() != "nan":
                    value = raw_value
            optional_values[column] = value
        targets.append(
            Target(name=target.name, coord=target.coord, **optional_values)
        )
        seen_names.add(name.casefold())
    return targets
