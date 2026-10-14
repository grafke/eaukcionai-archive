from dataclasses import dataclass
from datetime import date, datetime

type Eur = int | float

BASE_URL = "https://www.eaukcionai.lt/evs/pages"


def auction_url(auction_id: int) -> str:
    return f"{BASE_URL}/auction.do?id={auction_id}"


@dataclass(frozen=True, kw_only=True)
class Item:
    auction_id: int
    item_no: int
    name: str
    share_sold: str | None = None
    subtype: str | None = None
    area_m2: float | None = None
    share_area_m2: float | None = None
    address: str | None = None
    unique_nr: str | None = None


@dataclass(frozen=True, kw_only=True)
class AuctionFields:
    """What one detail page says about an auction, before lifecycle bookkeeping."""

    number: int | None
    kind: str | None
    type: str | None = None
    status: str
    start_date: str
    end_date: str
    registration_start: str | None = None
    registration_end: str | None = None
    starting_price_eur: Eur | None = None
    highest_bid_eur: Eur | None = None


@dataclass(frozen=True)
class Detail:
    auction_fields: AuctionFields
    items: tuple[Item, ...]


@dataclass(frozen=True)
class Missing:
    """The site answered HTTP 400: the auction id does not exist (any more)."""


@dataclass(frozen=True)
class Auction:
    auction_id: int
    number: int | None
    url: str
    kind: str | None
    type: str | None
    status: str
    start_date: str
    end_date: str
    registration_start: str | None
    registration_end: str | None
    starting_price_eur: Eur | None
    highest_bid_eur: Eur | None
    first_seen: date
    last_seen: date
    last_fetched: datetime
    final_status_seen_at: datetime | None
    done: bool
