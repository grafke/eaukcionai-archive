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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Daikto pagrindinė naudojimo paskirtis: Kita. Žemės sklypo naudojimo būdas: Gyvenamosios teritorijos.", "Kita"),
        ("Daikto pagrindinė naudojimo paskirtis: Žemės ūkio", "Žemės ūkio"),
        ("Žemės sklypo paskirtis/ naudojimo būdas: Kita/Komercinės paskirties objektų teritorijos.", "Kita"),
        ("Žemės sklypo paskirtis/naudojimo būdas(-ai): Kita / Visuomeninės paskirties teritorijos", "Kita"),
        ("8274/0001:133 Užpalių k.v., paskirtis – žemės ūkio, žemės sklypo plotas – 0,1880 ha", "Žemės ūkio"),
        ("pagrindinė žemės sklypo naudojimo paskirtis – miškų ūkio; naudojimo būdas – ūkinių miškų sklypai", "Miškų ūkio"),
        ("Pagrindinė žemės sklypo naudojimo paskirtis – vandens ūkio", "Vandens ūkio"),
        ("Daikto pagrindinė naudojimo paskirtis: Konservacinė", "Konservacinė"),
        ("žemės sklypo, Gyvenamosios teritorijos, Mažaaukščių gyvenamųjų namų statybos", None),
        ("mokėjimo paskirtis, kai mokama šio įsakymo 1.1.10 papunktyje nurodytu atveju", None),
        ("Daikto pagrindinė naudojimo paskirtis: Vienbučių", None),
        ("", None),
        (None, None),
    ],
)
def test_land_purpose(text, expected):
    assert v.land_purpose(text) == expected
