import astropy.units as u
import pytest

from obsplanner.targets import TargetResolutionError, parse_target_csv


def test_parse_target_csv_with_both_coordinate_formats():
    targets = parse_target_csv(
        "name,ra,dec\n"
        "NGC 3783,11:39:01,-37:44:20\n"
        "PDS 456,262.0825,-14.9322\n"
    )
    assert [target.name for target in targets] == ["NGC 3783", "PDS 456"]
    assert targets[0].coord.ra.to_value(u.deg) == pytest.approx(174.7542, abs=0.001)
    assert targets[1].coord.ra.to_value(u.deg) == pytest.approx(262.0825)


def test_target_csv_columns_are_case_insensitive():
    targets = parse_target_csv("Name,RA,DEC\nTest,12:00:00,+10:00:00\n")
    assert targets[0].name == "Test"


def test_target_csv_imports_optional_fields_and_treats_blanks_as_empty():
    targets = parse_target_csv(
        "name,ra,dec,tag,exptime,note\n"
        'First,10,+20,program A,2 x 600s,"First visit"\n'
        "Second,11,+21,,,\n"
    )

    assert targets[0].tag == "program A"
    assert targets[0].exptime == "2 x 600s"
    assert targets[0].note == "First visit"
    assert targets[1].tag == ""
    assert targets[1].exptime == ""
    assert targets[1].note == ""


@pytest.mark.parametrize(
    "csv_text",
    [
        "name,ra\nTarget,12:00:00\n",
        "name,ra,dec\n",
        "name,ra,dec\nTarget,bad,-20\n",
        "name,ra,dec\nTarget,12:00:00,-20\nTarget,13:00:00,-21\n",
    ],
)
def test_invalid_target_csv_is_rejected(csv_text):
    with pytest.raises(TargetResolutionError):
        parse_target_csv(csv_text)
