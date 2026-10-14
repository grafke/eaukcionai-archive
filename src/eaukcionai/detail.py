import re
from collections.abc import Callable

from selectolax.lexbor import LexborHTMLParser, LexborNode

from eaukcionai import parse_values as v
from eaukcionai.model import AuctionFields, Detail, Item


class ParseError(ValueError):
    pass


# Page label -> (field, converter). Rental auctions ("Nuomos konkursai") use their own wording.
_AUCTION_LABELS: dict[str, tuple[str, Callable[[str], object]]] = {
    "Tipas:": ("type", v.optional),
    "Pradžios data:": ("start_date", v.site_datetime),
    "Pabaigos data:": ("end_date", v.site_datetime),
    "Registracijos pradžia:": ("registration_start", v.site_datetime),
    "Registracijos pabaiga:": ("registration_end", v.site_datetime),
    "Pradinė pardavimo kaina:": ("starting_price_eur", v.eur),
    "Pradinė nuomos kaina be PVM:": ("starting_price_eur", v.eur),
}

_ITEM_LABELS: dict[str, tuple[str, Callable[[str], object]]] = {
    "Parduodama turto dalis:": ("share_sold", v.optional),
    "Nuomojama turto dalis:": ("share_sold", v.optional),
    "Turto potipis:": ("subtype", v.optional),
    "Bendras turto plotas:": ("area_m2", v.area_m2),
    "Parduodamo turto dalies plotas:": ("share_area_m2", v.area_m2),
    "Nuomojamo turto dalies plotas:": ("share_area_m2", v.area_m2),
    "Adresas:": ("address", v.optional),
    "Unikalus Nr.:": ("unique_nr", v.optional),
}

_ITEM_HEADING = re.compile(r"^(?:Parduodamas|Nuomojamas) turtas:\s*(.*)$")
_NUMBER_HEADING = re.compile(r"^Nr\.\s*(\d+)$")


def _pairs(rows: list[LexborNode]) -> dict[str, LexborNode]:
    pairs = {}
    for li in rows:
        left, right = li.css_first(".left"), li.css_first(".right")
        if left is not None and right is not None:
            pairs[v.clean(left.text())] = right
    return pairs


def _fields(pairs: dict[str, LexborNode], labels: dict[str, tuple[str, Callable[[str], object]]]) -> dict:
    return {field: convert(pairs[label].text()) for label, (field, convert) in labels.items() if label in pairs}


def _number(tree: LexborHTMLParser) -> int | None:
    for h2 in tree.css("main h2"):
        if match := _NUMBER_HEADING.match(v.clean(h2.text())):
            return int(match[1])
    return None


def _label(node: LexborNode | None, selector: str) -> str | None:
    found = node.css_first(selector) if node is not None else None
    return v.optional(found.text()) if found is not None else None


def _items(tree: LexborHTMLParser, auction_id: int) -> tuple[Item, ...]:
    items = []
    for block in tree.css("div.product_desc"):
        heading = block.css_first("h2")
        match = _ITEM_HEADING.match(v.clean(heading.text())) if heading is not None else None
        if match is None:
            continue
        fields = _fields(_pairs(block.css("ul.list > li")), _ITEM_LABELS)
        items.append(Item(auction_id=auction_id, item_no=len(items) + 1, name=match[1], **fields))
    return tuple(items)


def parse_detail(html: str, auction_id: int) -> Detail:
    try:
        return _parse_detail(LexborHTMLParser(html), auction_id)
    except ParseError:
        raise
    except ValueError as error:
        raise ParseError(f"auction {auction_id}: {error}") from error


def _parse_detail(tree: LexborHTMLParser, auction_id: int) -> Detail:
    pairs = _pairs(tree.css("div.load_block ul.list > li"))
    if "Pradžios data:" not in pairs or "Pabaigos data:" not in pairs:
        raise ParseError(f"auction {auction_id}: no Pradžios data / Pabaigos data")
    status_node = pairs.get("Būsena:")
    max_bid = tree.css_first("#maxBid")
    highest_bid = v.eur(max_bid.text()) if max_bid is not None else None
    auction = AuctionFields(
        number=_number(tree),
        kind=_label(status_node, ".label-default"),
        status=_label(status_node, ".label-primary") or "",
        highest_bid_eur=highest_bid or None,
        **_fields(pairs, _AUCTION_LABELS),
    )
    return Detail(auction_fields=auction, items=_items(tree, auction_id))
