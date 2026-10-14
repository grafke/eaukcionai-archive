"""Nightly run: crawl the live listing, fetch the auctions that need it, write data/ once."""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from eaukcionai import lifecycle, store
from eaukcionai.detail import ParseError, parse_detail
from eaukcionai.fetch import Client, FetchError
from eaukcionai.listing import LISTING_URL, ListingPage, parse_listing
from eaukcionai.model import Detail, Missing, auction_url

log = logging.getLogger("eaukcionai")


class ListingError(RuntimeError):
    pass


def _listing_page(client: Client, page: int) -> ListingPage:
    body = client.get(LISTING_URL.format(page=page))
    if isinstance(body, Missing):
        raise ListingError(f"listing page {page}: HTTP 400")
    return parse_listing(body)


def crawl_listing(client: Client, max_pages: int | None) -> set[int]:
    first = _listing_page(client, 0)
    if first.last_page is None or not first.auction_ids:
        raise ListingError("listing page 0 has no auctions or no pagination; layout changed?")
    last = first.last_page if max_pages is None else min(first.last_page, max_pages - 1)
    live = set(first.auction_ids)
    for page in range(1, last + 1):
        ids = _listing_page(client, page).auction_ids
        if page < first.last_page and len(ids) != len(first.auction_ids):
            raise ListingError(f"listing page {page} has {len(ids)} auctions, page 0 had {len(first.auction_ids)}")
        live.update(ids)
    log.info("listing: %d live auctions on %d pages", len(live), last + 1)
    return live


def main(argv: list[str] | None = None, client: Client | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eaukcionai.run")
    parser.add_argument("--max-pages", type=int, help="crawl at most N listing pages (smoke tests)")
    parser.add_argument("--max-details", type=int, help="fetch at most N detail pages (smoke tests)")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    client = client or Client()
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        live_ids = crawl_listing(client, args.max_pages)
    except (ListingError, FetchError) as error:
        log.error("aborting before touching data: %s", error)
        return 2

    state = store.load(args.data_dir)
    targets = [
        auction_id
        for auction_id in sorted(live_ids | state.auctions.keys())
        if lifecycle.needs_fetch(state.auctions.get(auction_id), live=auction_id in live_ids)
    ][: args.max_details]
    log.info("fetching %d detail pages", len(targets))

    failures = 0
    unseen_statuses: set[str] = set()
    for auction_id in targets:
        try:
            body = client.get(auction_url(auction_id))
            observed = body if isinstance(body, Missing) else parse_detail(body, auction_id)
        except (FetchError, ParseError) as error:
            failures += 1
            log.error("%s", error)
            continue
        live = auction_id in live_ids
        record = lifecycle.reconcile(auction_id, state.auctions.get(auction_id), observed, live=live, now=now)
        if record is None:
            log.warning("auction %d: listed but HTTP 400, skipped", auction_id)
            continue
        state.auctions[auction_id] = record
        if isinstance(observed, Detail):
            state.items[auction_id] = observed.items
        status = record.status
        if status and not lifecycle.is_known_status(status) and status not in unseen_statuses:
            unseen_statuses.add(status)
            log.warning("unseen status %r (auction %d), treated as final", status, auction_id)

    store.write(args.data_dir, state)
    done = sum(a.done for a in state.auctions.values())
    log.info("wrote %d auctions (%d done), %d failures", len(state.auctions), done, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
