"""One-time id walk. An id is settled when the archive has an auction, a gap, or an unreadable mark."""

import argparse
import logging
import sys
from collections import deque
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from eaukcionai import lifecycle, store
from eaukcionai.detail import ParseError, parse_detail
from eaukcionai.fetch import Client, FetchError
from eaukcionai.model import Detail, Gap, Missing, Unreadable, auction_url

log = logging.getLogger("eaukcionai")

CHECKPOINT_EVERY = 20
# One broken page is skipped. This many HTTP 5xx responses in a row means the site is down.
SERVER_ERROR_STREAK = 3


def main(argv: list[str] | None = None, client: Client | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eaukcionai.walk")
    parser.add_argument("start", type=int)
    parser.add_argument("end", type=int)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--max-fetches", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--checkpoint-every", type=int, default=CHECKPOINT_EVERY)
    args = parser.parse_args(argv)
    if args.end < args.start or args.start < 1:
        parser.error("end must be >= start, and start must be >= 1")
    if args.max_fetches is not None and args.max_fetches < 1:
        parser.error("--max-fetches must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.interval < 0:
        parser.error("--interval must be >= 0")
    if args.checkpoint_every < 1:
        parser.error("--checkpoint-every must be >= 1")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    client = client or Client(interval=args.interval)
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        return _walk(
            client,
            args.data_dir,
            range(args.start, args.end + 1),
            now=now,
            max_fetches=args.max_fetches,
            concurrency=args.concurrency,
            checkpoint_every=args.checkpoint_every,
        )
    except store.ArchiveBusy as error:
        log.error("aborting before touching data: %s", error)
        return 2


def _observe(client: Client, auction_id: int) -> Missing | Detail:
    body = client.get(auction_url(auction_id))
    return body if isinstance(body, Missing) else parse_detail(body, auction_id)


def _in_flight(
    client: Client, pending: list[int], concurrency: int, *, room_for_more
) -> Iterator[tuple[int, Future[Missing | Detail]]]:
    """Yield fetches in id order, with up to `concurrency` requests running."""
    inflight: deque[tuple[int, Future[Missing | Detail]]] = deque()
    upcoming = iter(pending)

    def submit() -> bool:
        if len(inflight) >= concurrency or not room_for_more(len(inflight)):
            return False
        try:
            auction_id = next(upcoming)
        except StopIteration:
            return False
        inflight.append((auction_id, pool.submit(_observe, client, auction_id)))
        return True

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        try:
            while submit():
                pass
            while inflight:
                auction_id, future = inflight.popleft()
                yield auction_id, future
                while submit():
                    pass
        finally:
            for _, future in inflight:
                future.cancel()


def _walk(
    client: Client,
    data_dir: Path,
    ids: range,
    *,
    now: datetime,
    max_fetches: int | None,
    concurrency: int = 1,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> int:
    with store.open_archive(data_dir) as archive:
        state = archive.state
        settled = state.auctions.keys() | state.gaps.keys() | state.unreadable.keys()
        pending = [auction_id for auction_id in ids if auction_id not in settled]
        log.info(
            "walk %d..%d: %d ids, %d already settled, fetching %d",
            ids.start,
            ids.stop - 1,
            len(ids),
            len(ids) - len(pending),
            len(pending),
        )
        unsaved = 0
        fetched = 0
        unseen_statuses: set[str] = set()
        streak: list[tuple[int, FetchError]] = []
        code = 0

        def checkpoint(auction_id: int) -> None:
            nonlocal unsaved, fetched
            unsaved += 1
            fetched += 1
            if unsaved >= checkpoint_every:
                archive.save()
                unsaved = 0
                log.info("checkpoint through %d, %d fetched", auction_id, fetched)

        def settle_server_errors() -> None:
            for failed_id, error in streak:
                log.error("skipping %d: %s", failed_id, error)
                state.unreadable[failed_id] = Unreadable(auction_id=failed_id, checked_at=now)
                checkpoint(failed_id)
            streak.clear()

        def room_for_more(already_running: int) -> bool:
            return max_fetches is None or fetched + already_running < max_fetches

        try:
            for auction_id, future in _in_flight(client, pending, concurrency, room_for_more=room_for_more):
                try:
                    observed = future.result()
                except FetchError as error:
                    if error.status_code is not None and error.status_code >= 500:
                        streak.append((auction_id, error))
                        if len(streak) >= SERVER_ERROR_STREAK:
                            log.error("stopping at %d: %s", streak[0][0], streak[0][1])
                            streak.clear()
                            code = 1
                            return code
                        continue
                    settle_server_errors()
                    log.error("stopping at %d: %s", auction_id, error)
                    code = 1
                    return code
                except ParseError as error:
                    settle_server_errors()
                    log.error("stopping at %d: %s", auction_id, error)
                    code = 1
                    return code
                settle_server_errors()
                if isinstance(observed, Missing):
                    state.gaps[auction_id] = Gap(auction_id=auction_id, checked_at=now)
                else:
                    record = lifecycle.discover(auction_id, observed, now=now)
                    state.auctions[auction_id] = record
                    state.items[auction_id] = observed.items
                    status = record.status
                    if status and not lifecycle.is_known_status(status) and status not in unseen_statuses:
                        unseen_statuses.add(status)
                        log.warning("unseen status %r (auction %d), treated as final", status, auction_id)
                checkpoint(auction_id)
            if max_fetches is not None and fetched >= max_fetches and fetched < len(pending):
                log.info("pausing after %d fetches", fetched)
                code = 3
                return code
            settle_server_errors()
            log.info("range settled")
            return code
        finally:
            if unsaved:
                archive.save()


if __name__ == "__main__":
    sys.exit(main())
