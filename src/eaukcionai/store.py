import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from eaukcionai.model import Auction, Item

AUCTIONS_FILE = "auctions.jsonl"
ITEMS_FILE = "items.jsonl"
_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class State:
    auctions: dict[int, Auction] = field(default_factory=dict)
    items: dict[int, tuple[Item, ...]] = field(default_factory=dict)


def encode(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime(_TIMESTAMP)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _timestamp(text: str) -> datetime:
    return datetime.strptime(text, _TIMESTAMP).replace(tzinfo=UTC)


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
    state.items = {auction_id: tuple(sorted(items, key=lambda i: i.item_no)) for auction_id, items in grouped.items()}
    return state


def write(data_dir: Path, state: State) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(data_dir / AUCTIONS_FILE, [state.auctions[k] for k in sorted(state.auctions)])
    _write_jsonl(data_dir / ITEMS_FILE, [item for k in sorted(state.items) for item in state.items[k]])
