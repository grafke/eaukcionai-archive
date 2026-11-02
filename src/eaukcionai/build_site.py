"""Build site/auctions.sqlite from data/*.jsonl for the static viewer.

Also writes auctions-recent.sqlite beside it. The page opens that file first.
It holds auctions whose end date falls in the default window, plus two days
of slack for a browser behind UTC. The full file follows in the background.

Usage: uv run python -m eaukcionai.build_site [DATA_DIR] [OUT]
"""

import re
import sqlite3
import sys
from dataclasses import asdict, fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from eaukcionai import store
from eaukcionai.model import Auction, Item

_MUNICIPALITY = re.compile(r"^(\S+(?: \S+)?(?: [rm]\.)? sav\.)")
_LOCALITY = re.compile(r"^((?:\S+ )*(?:mstl\.|vs\.|k\.|m\.))(?!\S)")
RECENT_DAYS = 90
# The page's default window is 90 local days. Two more days cover a browser behind UTC and a page opened the day after the build.
RECENT_SLACK_DAYS = 2


def municipality(address: str | None) -> str | None:
    """`Telšių r. sav. Telšių m. ...` -> `Telšių r. sav.`; None when the address has no municipality prefix."""
    match = _MUNICIPALITY.match(address or "")
    return match[1] if match else None


def settlement(address: str | None) -> str | None:
    """`Telšių r. sav. Telšių m. ...` -> `Telšių m.`. Cities, towns, villages, and homesteads share one list."""
    prefix = municipality(address)
    if prefix is None or address is None:
        return None
    match = _LOCALITY.match(address[len(prefix) :].lstrip())
    return match[1] if match else None


def _columns(cls) -> list[str]:
    return [f.name for f in fields(cls)]


def recent_cutoff(today: date) -> str:
    return (today - timedelta(days=RECENT_DAYS + RECENT_SLACK_DAYS)).isoformat()


def recent_output(out: Path) -> Path:
    return out.with_name(f"{out.stem}-recent{out.suffix}")


def _item_rows_sql(auction_columns: list[str], item_columns: list[str]) -> str:
    auction_only = [c for c in auction_columns if c not in item_columns]
    price_per_m2 = "CAST(a.starting_price_eur AS REAL) / NULLIF(i.area_m2, 0) AS price_per_m2"
    return (
        "CREATE VIEW item_rows AS SELECT "
        + ", ".join([*(f"i.{c}" for c in item_columns), *(f"a.{c}" for c in auction_only), price_per_m2])
        + " FROM items i JOIN auctions a USING (auction_id)"
    )


def write_recent(full: Path, recent: Path, cutoff: str) -> None:
    """Copy auctions with end_date >= cutoff into `recent`, and record that cutoff in meta."""
    with sqlite3.connect(full) as src:
        view = src.execute("SELECT sql FROM sqlite_master WHERE type = 'view' AND name = 'item_rows'").fetchone()[0]
    recent.unlink(missing_ok=True)
    with sqlite3.connect(recent) as dst:
        dst.execute("ATTACH DATABASE ? AS src", (str(full),))
        dst.execute("CREATE TABLE auctions AS SELECT * FROM src.auctions WHERE end_date >= ?", (cutoff,))
        dst.execute(
            "CREATE TABLE items AS SELECT * FROM src.items WHERE auction_id IN (SELECT auction_id FROM auctions)"
        )
        dst.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        dst.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [("scope", "recent"), ("end_from", cutoff)],
        )
        dst.execute(view)


def build(data_dir: Path, out: Path, today: date | None = None) -> None:
    state = store.load(data_dir)
    auction_columns = _columns(Auction)
    item_columns = [*_columns(Item), "municipality", "settlement"]
    out.unlink(missing_ok=True)
    with sqlite3.connect(out) as db:
        db.execute(f"CREATE TABLE auctions ({', '.join(auction_columns)}, PRIMARY KEY (auction_id))")
        db.execute(f"CREATE TABLE items ({', '.join(item_columns)}, PRIMARY KEY (auction_id, item_no))")
        db.executemany(
            f"INSERT INTO auctions VALUES ({', '.join('?' * len(auction_columns))})",
            ([store.encode(v) for v in asdict(a).values()] for a in state.auctions.values()),
        )
        db.executemany(
            f"INSERT INTO items VALUES ({', '.join('?' * len(item_columns))})",
            (
                [*asdict(item).values(), municipality(item.address), settlement(item.address)]
                for items in state.items.values()
                for item in items
            ),
        )
        db.execute(_item_rows_sql(auction_columns, item_columns))
    db.close()
    write_recent(out, recent_output(out), recent_cutoff(today or datetime.now(UTC).date()))


if __name__ == "__main__":
    args = sys.argv[1:]
    build(Path(args[0]) if args else Path("data"), Path(args[1]) if len(args) > 1 else Path("site/auctions.sqlite"))
