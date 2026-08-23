from dataclasses import dataclass

from astropy.coordinates import SkyCoord


@dataclass(frozen=True)
class Target:
    """A named fixed celestial target."""

    name: str
    coord: SkyCoord
    tag: str = ""
    exptime: str = ""
    note: str = ""
