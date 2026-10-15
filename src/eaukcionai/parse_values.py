import re
from datetime import datetime

from eaukcionai.model import Eur, LandPurpose

_AREA = re.compile(r"^([\d\s]+(?:,\d+)?)\s*(kv\. m|a\.|ha)")
_SQUARE_METRES_PER_UNIT = {"kv. m": 1, "a.": 100, "ha": 10_000}


def clean(text: str) -> str:
    return " ".join(text.split())


def optional(text: str) -> str | None:
    return clean(text) or None


def eur(text: str) -> Eur | None:
    """`54 670 Eur` -> 54670, `18 908,50 Eur` -> 18908.5, `–` or empty -> None."""
    digits = "".join(text.split()).removesuffix("Eur").replace(",", ".")
    if digits in ("", "–", "-"):
        return None
    value = float(digits)
    return int(value) if value.is_integer() else value


def area_m2(text: str) -> float | None:
    """`524,67 kv. m` -> 524.67, `21,84 a. (0,22 ha.)` -> 2184.0."""
    match = _AREA.match(clean(text))
    if match is None:
        return None
    number = float("".join(match[1].split()).replace(",", "."))
    return round(number * _SQUARE_METRES_PER_UNIT[match[2]], 2)


_LAND_PURPOSE = re.compile(
    r"(?<!mokėjimo\s)paskirtis\s*(?:/\s*naudojimo\s+būdas(?:\(-ai\))?\s*)?"
    r"[:\u2013\u2014-]\s*(žemės ūkio|miškų ūkio|vandens ūkio|konservacinė|kita)\b",
    re.IGNORECASE,
)
_LAND_PURPOSE_CANONICAL: dict[str, LandPurpose] = {
    "žemės ūkio": "Žemės ūkio",
    "miškų ūkio": "Miškų ūkio",
    "vandens ūkio": "Vandens ūkio",
    "konservacinė": "Konservacinė",
    "kita": "Kita",
}


def land_purpose(text: str | None) -> LandPurpose | None:
    """`Daikto pagrindinė naudojimo paskirtis: Kita` -> `Kita`. Ignores `mokėjimo paskirtis`."""
    match = _LAND_PURPOSE.search(clean(text or ""))
    return _LAND_PURPOSE_CANONICAL[match[1].lower()] if match else None


def site_datetime(text: str) -> str:
    """`2026-10-20 09:00:00` -> `2026-10-20T09:00:00` (local Vilnius time, as shown)."""
    return datetime.strptime(clean(text), "%Y-%m-%d %H:%M:%S").isoformat()
