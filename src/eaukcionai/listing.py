import re
from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser

from eaukcionai.model import BASE_URL

LISTING_URL = (
    f"{BASE_URL}/auctions.do?stateType=PASKELBTA-IR-VYKSTA&advancedSearch=true&sortBy=endDate.ASC&page={{page}}"
)

_AUCTION_ID = re.compile(r"auction\.do\?id=(\d+)")


@dataclass(frozen=True)
class ListingPage:
    auction_ids: tuple[int, ...]
    last_page: int | None


def parse_listing(html: str) -> ListingPage:
    tree = LexborHTMLParser(html)
    ids = []
    for link in tree.css("ul.bid_list > li h2.no a"):
        match = _AUCTION_ID.search(link.attributes.get("href") or "")
        if match and int(match[1]) not in ids:
            ids.append(int(match[1]))
    pages = [int(a.attributes["data-page"]) for a in tree.css("a.paginationLink[data-page]")]
    return ListingPage(auction_ids=tuple(ids), last_page=max(pages, default=None))
