from pathlib import Path

import pytest

from obsplanner.observatories import ObservatoryCatalogError, load_observatories


def test_catalog_contains_required_sites():
    sites = load_observatories()
    required = {"paranal", "la_silla", "palomar", "las_campanas"}
    assert required <= sites.keys()
    assert "alma" not in sites
    assert len(sites) >= 14


def test_catalog_sites_create_observers():
    sites = load_observatories()
    for site in sites.values():
        observer = site.to_observer()
        assert observer.name == site.name
        assert observer.location.height.value > 0


def test_invalid_catalog_is_rejected(tmp_path: Path):
    catalog = tmp_path / "invalid.yaml"
    catalog.write_text("bad_site:\n  name: Missing fields\n", encoding="utf-8")
    with pytest.raises(ObservatoryCatalogError):
        load_observatories(catalog)
