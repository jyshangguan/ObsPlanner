from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import astropy.units as u
import yaml
from astroplan import Observer
from astropy.coordinates import EarthLocation


class ObservatoryCatalogError(ValueError):
    """Raised for an invalid observatory catalog."""


@dataclass(frozen=True)
class Observatory:
    key: str
    name: str
    latitude: float
    longitude: float
    elevation: float
    timezone: str
    description: str = ""

    def to_observer(self) -> Observer:
        location = EarthLocation.from_geodetic(
            lon=self.longitude * u.deg,
            lat=self.latitude * u.deg,
            height=self.elevation * u.m,
        )
        return Observer(
            location=location,
            name=self.name,
            timezone=ZoneInfo(self.timezone),
        )


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "observatories.yaml"


def load_observatories(
    path: str | Path | None = None,
) -> dict[str, Observatory]:
    """Load and validate observatories from YAML."""
    catalog_path = Path(path) if path else default_catalog_path()
    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ObservatoryCatalogError(
            f"Could not load observatory catalog: {catalog_path}"
        ) from exc

    if not isinstance(raw, dict) or not raw:
        raise ObservatoryCatalogError("The observatory catalog is empty or invalid.")

    required = {"name", "latitude", "longitude", "elevation", "timezone"}
    observatories: dict[str, Observatory] = {}
    for key, values in raw.items():
        if not isinstance(values, dict):
            raise ObservatoryCatalogError(f"Invalid entry for {key}.")
        missing = required - values.keys()
        if missing:
            raise ObservatoryCatalogError(
                f"{key} is missing: {', '.join(sorted(missing))}."
            )
        try:
            latitude = float(values["latitude"])
            longitude = float(values["longitude"])
            elevation = float(values["elevation"])
            ZoneInfo(str(values["timezone"]))
        except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise ObservatoryCatalogError(f"Invalid values for {key}.") from exc

        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ObservatoryCatalogError(f"Invalid coordinates for {key}.")

        observatories[key] = Observatory(
            key=key,
            name=str(values["name"]),
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            timezone=str(values["timezone"]),
            description=str(values.get("description", "")),
        )
    return observatories
