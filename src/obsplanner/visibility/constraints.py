from dataclasses import dataclass


@dataclass(frozen=True)
class VisibilityConstraints:
    minimum_altitude: float = 30.0
    maximum_airmass: float = 2.0
    minimum_moon_separation: float = 30.0

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_altitude < 90:
            raise ValueError("Minimum altitude must be between 0 and 90 degrees.")
        if self.maximum_airmass < 1:
            raise ValueError("Maximum airmass must be at least 1.")
        if not 0 <= self.minimum_moon_separation <= 180:
            raise ValueError("Moon separation must be between 0 and 180 degrees.")
