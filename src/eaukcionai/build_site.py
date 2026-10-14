"""Build site/auctions.sqlite from data/*.jsonl for the static viewer.

Usage: uv run python -m eaukcionai.build_site [DATA_DIR] [OUT]
"""

import re
import sqlite3
import sys
from dataclasses import asdict, fields
from pathlib import Path

from eaukcionai import store
from eaukcionai.model import Auction, Item

_MUNICIPALITY = re.compile(r"^(\S+(?: \S+)?(?: [rm]\.)? sav\.)")


def municipality(address: str | None) -> str | None:
    """`Telšių r. sav. Telšių m. ...` -> `Telšių r. sav.`; None when the address has no municipality prefix."""
    match = _MUNICIPALITY.match(address or "")
    return match[1] if match else None


def _columns(cls) -> list[str]:
    return [f.name for f in fields(cls)]


def build(data_dir: Path, out: Path) -> None:
    state = store.load(data_dir)
    auction_columns = _columns(Auction)
    item_columns = [*_columns(Item), "municipality"]
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
            ([*asdict(item).values(), municipality(item.address)] for items in state.items.values() for item in items),
        )
        auction_only = [c for c in auction_columns if c not in item_columns]
        db.execute(
            "CREATE VIEW item_rows AS SELECT "
            + ", ".join([*(f"i.{c}" for c in item_columns), *(f"a.{c}" for c in auction_only)])
            + " FROM items i JOIN auctions a USING (auction_id)"
        )
    db.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    build(Path(args[0]) if args else Path("data"), Path(args[1]) if len(args) > 1 else Path("site/auctions.sqlite"))
