import pytest

from goranchacha.coords import format_dec, format_ra, parse_dec_degrees, parse_ra_hours


def test_parse():
    assert parse_ra_hours("05:34:32") == pytest.approx(5.575556, abs=1e-5)
    assert parse_ra_hours("5.5") == 5.5
    assert parse_ra_hours("05h34m32s") == pytest.approx(5.575556, abs=1e-5)
    assert parse_dec_degrees("-05:23:28") == pytest.approx(-5.391111, abs=1e-5)
    assert parse_dec_degrees("+22 00 52") == pytest.approx(22.014444, abs=1e-5)


@pytest.mark.parametrize("bad", ["", "25", "ab", "5:70:00", "1:2:3:4"])
def test_bad_ra(bad):
    with pytest.raises(ValueError):
        parse_ra_hours(bad)


def test_dec_range_and_format():
    with pytest.raises(ValueError):
        parse_dec_degrees("91")
    assert format_ra(5.575556) == "05:34:32.0"
    assert format_dec(-5.391111) == "-05:23:28"
