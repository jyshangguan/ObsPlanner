from pathlib import Path

import pytest

from obsplanner.observatories import ObservatoryCatalogError, load_observatories


def test_catalog_contains_required_sites():
    sites = load_observatories()
    required = {
        "paranal",
        "la_silla",
        "palomar",
        "las_campanas",
        "xinglong",
        "xue_shan_mu_chang",
    }
    assert required <= sites.keys()
    assert "alma" not in sites
    assert len(sites) >= 16

    assert sites["xinglong"].timezone == "Asia/Shanghai"
    assert sites["xinglong"].elevation == pytest.approx(900)
    assert sites["xue_shan_mu_chang"].latitude == pytest.approx(37.9767)
    assert sites["xue_shan_mu_chang"].longitude == pytest.approx(96.5857)
    assert sites["xue_shan_mu_chang"].elevation == pytest.approx(4813)


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
