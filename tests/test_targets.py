import time
import types

import astropy.units as u
import pytest
from astropy.table import Table

from obsplanner.targets import (
    TargetResolutionError,
    parse_coordinate_pair,
    parse_manual_coordinates,
    resolve_target,
)
from obsplanner.targets import resolver

PRIMARY_SERVER = "simbad.cds.unistra.fr"
BACKUP_SERVER = "simbad.cfa.harvard.edu"


def test_parse_sexagesimal_coordinates():
    target = parse_manual_coordinates("11:39:01", "-37:44:20", "NGC 3783")
    assert target.name == "NGC 3783"
    assert target.coord.ra.to_value(u.deg) == pytest.approx(174.7542, abs=0.001)
    assert target.coord.dec.to_value(u.deg) == pytest.approx(-37.7389, abs=0.001)


def test_parse_decimal_coordinates():
    target = parse_manual_coordinates(
        "174.7542", "-37.7389", decimal_degrees=True
    )
    assert target.coord.ra.to_value(u.deg) == pytest.approx(174.7542)


def test_invalid_coordinates_are_rejected():
    with pytest.raises(TargetResolutionError):
        parse_manual_coordinates("", "-37:44:20")


@pytest.mark.parametrize(
    ("coordinates", "expected_ra", "expected_dec"),
    [
        ("11:39:01, -37:44:20", 174.7542, -37.7389),
        ("174.7542, -37.7389", 174.7542, -37.7389),
    ],
)
def test_parse_combined_coordinate_input(coordinates, expected_ra, expected_dec):
    target = parse_coordinate_pair(coordinates, "Target")
    assert target.coord.ra.deg == pytest.approx(expected_ra, abs=0.001)
    assert target.coord.dec.deg == pytest.approx(expected_dec, abs=0.001)


def test_combined_coordinate_input_requires_a_comma():
    with pytest.raises(TargetResolutionError, match="comma-separated"):
        parse_coordinate_pair("11:39:01 -37:44:20", "Target")


def _simbad_result_table():
    return Table(
        {
            "main_id": ["NGC  3783"],
            "ra": [174.7571236746],
            "dec": [-37.73861378972],
        }
    )


class StubSimbad:
    """Offline stand-in for the shared astroquery SIMBAD client."""

    def __init__(self, failures=(), *, delay=0.0, empty=False):
        self.server = PRIMARY_SERVER
        self.failures = set(failures)
        self.delay = delay
        self.empty = empty
        self.attempts = []

    def query_object(self, name):
        self.attempts.append(self.server)
        if self.delay:
            time.sleep(self.delay)
        if self.server in self.failures:
            raise ConnectionError(f"{self.server} is unreachable")
        if self.empty:
            return Table({"main_id": [], "ra": [], "dec": []})
        return _simbad_result_table()


@pytest.fixture
def install_simbad_stub(monkeypatch):
    """Replace the astroquery SIMBAD client used by the resolver."""

    def install(**kwargs):
        stub = StubSimbad(**kwargs)
        monkeypatch.setattr(resolver, "Simbad", stub)
        monkeypatch.setattr(
            resolver,
            "simbad_conf",
            types.SimpleNamespace(
                server=PRIMARY_SERVER,
                servers_list=[PRIMARY_SERVER, "simbad.harvard.edu"],
            ),
        )
        return stub

    return install


def test_resolve_target_success_on_primary(install_simbad_stub):
    stub = install_simbad_stub()
    target = resolve_target("NGC 3783")
    assert stub.attempts == [PRIMARY_SERVER]
    assert target.name == "NGC 3783"
    assert target.coord.ra.deg == pytest.approx(174.7571236746)
    assert target.coord.dec.deg == pytest.approx(-37.73861378972)


def test_resolve_target_falls_back_to_harvard_mirror(install_simbad_stub):
    stub = install_simbad_stub(failures=[PRIMARY_SERVER])
    target = resolve_target("NGC 3783")
    assert stub.attempts == [PRIMARY_SERVER, BACKUP_SERVER]
    assert stub.server == BACKUP_SERVER
    assert target.coord.ra.deg == pytest.approx(174.7571236746)


def test_successful_fallback_sticks_to_backup_mirror(install_simbad_stub):
    stub = install_simbad_stub(failures=[PRIMARY_SERVER])
    resolve_target("NGC 3783")
    stub.failures.clear()
    resolve_target("NGC 3783")
    assert stub.attempts == [PRIMARY_SERVER, BACKUP_SERVER, BACKUP_SERVER]


def test_fallback_returns_to_primary_when_backup_fails(install_simbad_stub):
    stub = install_simbad_stub(failures=[PRIMARY_SERVER])
    resolve_target("NGC 3783")
    stub.failures = {BACKUP_SERVER}
    target = resolve_target("NGC 3783")
    assert stub.attempts == [PRIMARY_SERVER, BACKUP_SERVER, BACKUP_SERVER, PRIMARY_SERVER]
    assert target.coord.ra.deg == pytest.approx(174.7571236746)


def test_resolve_target_reports_failure_from_all_mirrors(install_simbad_stub):
    stub = install_simbad_stub(failures=[PRIMARY_SERVER, BACKUP_SERVER])
    with pytest.raises(TargetResolutionError, match="could not be reached"):
        resolve_target("NGC 3783")
    assert stub.attempts == [PRIMARY_SERVER, BACKUP_SERVER]


def test_unknown_target_is_authoritative(install_simbad_stub):
    stub = install_simbad_stub(empty=True)
    with pytest.raises(TargetResolutionError, match="found no target"):
        resolve_target("xyzzy not a real object")
    assert stub.attempts == [PRIMARY_SERVER]


def test_hanging_server_triggers_timeout_fallback(install_simbad_stub, monkeypatch):
    monkeypatch.setattr(resolver, "SIMBAD_QUERY_TIMEOUT", 0.2)
    stub = install_simbad_stub(delay=2.0)
    with pytest.raises(TargetResolutionError, match="TimeoutError"):
        resolve_target("NGC 3783")
    assert stub.attempts == [PRIMARY_SERVER, BACKUP_SERVER]


def test_simbad_client_can_switch_to_harvard_mirror():
    previous = resolver.Simbad.server
    try:
        assert resolver._set_simbad_server(BACKUP_SERVER)
        assert resolver.Simbad.server == BACKUP_SERVER
    finally:
        resolver._set_simbad_server(previous)
