import pytest

from eaukcionai import parse_values as v


@pytest.mark.parametrize(
    ("text", "expected"),
    [("54 670 Eur", 54670), ("1 234,56 Eur", 1234.56), ("18 908,50 Eur", 18908.5), ("0", 0), ("–", None), ("", None)],
)
def test_eur(text, expected):
    assert v.eur(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("524,67 kv. m", 524.67), ("21,84 a. (0,22 ha.)", 2184.0), ("1,5 ha", 15000.0), ("3 vnt.", None)],
)
def test_area_m2(text, expected):
    assert v.area_m2(text) == expected


def test_site_datetime():
    assert v.site_datetime("\n  2026-10-20 09:00:00 ") == "2026-10-20T09:00:00"
