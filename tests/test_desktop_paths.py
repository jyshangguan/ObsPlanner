from pathlib import Path

import pytest

from obsplanner.desktop.paths import DesktopPaths, resource_root


def test_source_resource_root_contains_application():
    root = resource_root()
    assert (root / "app.py").is_file()
    assert (root / "assets" / "obsplanner-open-app.png").is_file()
    assert (root / "data" / "observatories.yaml").is_file()


def test_desktop_paths_create_writable_directories(tmp_path: Path):
    paths = DesktopPaths(
        resource_root=tmp_path,
        app_script=tmp_path / "app.py",
        app_logo=tmp_path / "ObsPlanner.png",
        observatory_catalog=tmp_path / "observatories.yaml",
        data_dir=tmp_path / "data-dir",
        cache_dir=tmp_path / "cache-dir",
        log_dir=tmp_path / "log-dir",
    )
    paths.ensure_writable_directories()
    assert paths.data_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.log_dir.is_dir()


def test_desktop_paths_report_missing_resources(tmp_path: Path):
    paths = DesktopPaths(
        resource_root=tmp_path,
        app_script=tmp_path / "missing-app.py",
        app_logo=tmp_path / "missing-logo.png",
        observatory_catalog=tmp_path / "missing-sites.yaml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    with pytest.raises(FileNotFoundError, match="Missing bundled"):
        paths.validate_resources()
