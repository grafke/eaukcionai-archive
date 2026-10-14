"""The whole auction lifecycle: which ids to fetch tonight, and how an observation updates a record.

An auction is fetched every night while it is in the live listing. After it leaves, it is
fetched until a final status shows up, then once more on a later night, then never again.
An auction that never shows a final status stops being fetched 30 days after it was last
listed. HTTP 400 for a known id counts as a final status.
"""

from dataclasses import asdict, fields
from datetime import datetime, timedelta

from eaukcionai.model import Auction, AuctionFields, Detail, Missing, auction_url

LIVE_STATUSES = frozenset({"Paskelbtas", "Paskelbtos", "Vykstančios", "Vykstantis"})
KNOWN_FINAL_STATUSES = frozenset({"Įvykusios", "Įvykęs", "Neįvykusios", "Neįvykęs", "Atšauktos", "Baigtos"})
GIVE_UP_AFTER = timedelta(days=30)
_PAGE_FIELDS = tuple(f.name for f in fields(AuctionFields))


def is_known_status(status: str) -> bool:
    return status in LIVE_STATUSES or status in KNOWN_FINAL_STATUSES


def needs_fetch(auction: Auction | None, *, live: bool) -> bool:
    return live or (auction is not None and not auction.done)


def reconcile(
    auction_id: int, prev: Auction | None, observed: Detail | Missing, *, live: bool, now: datetime
) -> Auction | None:
    """Fold one fetch result into the stored record. Returns None when there is nothing to record."""
    run_date = now.date()
    if isinstance(observed, Missing):
        if prev is None:
            return None
        page = {name: getattr(prev, name) for name in _PAGE_FIELDS}
        final = True
    else:
        page = asdict(observed.auction_fields)
        final = bool(page["status"]) and page["status"] not in LIVE_STATUSES

    last_seen = run_date if live or prev is None else prev.last_seen
    final_status_seen_at = ((prev and prev.final_status_seen_at) or now) if final else None
    extra_fetch_done = final_status_seen_at is not None and final_status_seen_at.date() < run_date
    gave_up = not final and run_date - last_seen > GIVE_UP_AFTER

    return Auction(
        auction_id=auction_id,
        url=auction_url(auction_id),
        **page,
        first_seen=prev.first_seen if prev else run_date,
        last_seen=last_seen,
        last_fetched=now,
        final_status_seen_at=final_status_seen_at,
        done=not live and (extra_fetch_done or gave_up),
    )
