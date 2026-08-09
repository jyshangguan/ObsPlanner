import astropy.units as u
import pytest

from obsplanner.targets import (
    TargetResolutionError,
    parse_coordinate_pair,
    parse_manual_coordinates,
)


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
