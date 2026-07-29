from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_data_path, user_log_path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Return the source root or PyInstaller extraction directory."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class DesktopPaths:
    """All read-only bundle and writable user paths used by the desktop app."""

    resource_root: Path
    app_script: Path
    app_logo: Path
    observatory_catalog: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path

    @classmethod
    def discover(cls) -> "DesktopPaths":
        root = resource_root()
        return cls(
            resource_root=root,
            app_script=root / "app.py",
            app_logo=root / "assets" / "obsplanner-open-app.png",
            observatory_catalog=root / "data" / "observatories.yaml",
            data_dir=Path(user_data_path("ObsPlanner", appauthor=False)),
            cache_dir=Path(user_cache_path("ObsPlanner", appauthor=False)),
            log_dir=Path(user_log_path("ObsPlanner", appauthor=False)),
        )

    def ensure_writable_directories(self) -> None:
        for directory in (self.data_dir, self.cache_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def validate_resources(self) -> None:
        missing = [
            path
            for path in (self.app_script, self.app_logo, self.observatory_catalog)
            if not path.is_file()
        ]
        if missing:
            formatted = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"Missing bundled ObsPlanner resources: {formatted}")
