import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from eaukcionai.model import Auction, Gap, Item

AUCTIONS_FILE = "auctions.jsonl"
ITEMS_FILE = "items.jsonl"
GAPS_FILE = "gaps.jsonl"
_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class State:
    auctions: dict[int, Auction] = field(default_factory=dict)
    items: dict[int, tuple[Item, ...]] = field(default_factory=dict)
    gaps: dict[int, Gap] = field(default_factory=dict)


class ArchiveBusy(RuntimeError):
    """Another process holds the data directory."""


def encode(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime(_TIMESTAMP)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _timestamp(text: str) -> datetime:
    return datetime.strptime(text, _TIMESTAMP).replace(tzinfo=UTC)


def _decode_gap(row: dict) -> Gap:
    return Gap(auction_id=row["auction_id"], checked_at=_timestamp(row["checked_at"]))


def _decode_auction(row: dict) -> Auction:
    return Auction(
        **row
        | {
            "first_seen": date.fromisoformat(row["first_seen"]),
            "last_seen": date.fromisoformat(row["last_seen"]),
            "last_fetched": _timestamp(row["last_fetched"]),
            "final_status_seen_at": row["final_status_seen_at"] and _timestamp(row["final_status_seen_at"]),
        }
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: list[object]) -> None:
    lines = [json.dumps({k: encode(v) for k, v in asdict(row).items()}, ensure_ascii=False) for row in rows]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    os.replace(tmp, path)


def load(data_dir: Path) -> State:
    state = State()
    for row in _read_jsonl(data_dir / AUCTIONS_FILE):
        auction = _decode_auction(row)
        state.auctions[auction.auction_id] = auction
    grouped: dict[int, list[Item]] = {}
    for row in _read_jsonl(data_dir / ITEMS_FILE):
        grouped.setdefault(row["auction_id"], []).append(Item(**row))
    state.items = {
        auction_id: tuple(sorted(items, key=lambda item: item.item_no))
        for auction_id, items in grouped.items()
        if auction_id in state.auctions
    }
    for row in _read_jsonl(data_dir / GAPS_FILE):
        gap = _decode_gap(row)
        if gap.auction_id not in state.auctions:
            state.gaps[gap.auction_id] = gap
    return state


class Archive:
    """The data directory, held exclusively by open_archive."""

    def __init__(self, data_dir: Path, state: State) -> None:
        self._data_dir = data_dir
        self.state = state

    def save(self) -> None:
        auctions = self.state.auctions
        self.state.items = {auction_id: items for auction_id, items in self.state.items.items() if auction_id in auctions}
        self.state.gaps = {auction_id: gap for auction_id, gap in self.state.gaps.items() if auction_id not in auctions}
        data_dir = self._data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        item_rows = [item for auction_id in sorted(self.state.items) for item in self.state.items[auction_id]]
        gap_rows = [self.state.gaps[auction_id] for auction_id in sorted(self.state.gaps)]
        auction_rows = [auctions[auction_id] for auction_id in sorted(auctions)]
        _write_jsonl(data_dir / ITEMS_FILE, item_rows)
        _write_jsonl(data_dir / GAPS_FILE, gap_rows)
        _write_jsonl(data_dir / AUCTIONS_FILE, auction_rows)


@contextmanager
def open_archive(data_dir: Path) -> Iterator[Archive]:
    """Lock the directory, load it, and yield a handle that can save.

    The lock is on the directory itself, so a crash cannot leave a lock file for git to commit.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(data_dir, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise ArchiveBusy(str(data_dir)) from None
    try:
        yield Archive(data_dir, load(data_dir))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def write(data_dir: Path, state: State) -> None:
    """Replace the archive. Takes the same lock as open_archive."""
    with open_archive(data_dir) as archive:
        archive.state = state
        archive.save()
