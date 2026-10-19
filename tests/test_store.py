import subprocess
import sys
from datetime import UTC, date, datetime

from eaukcionai import store
from eaukcionai.model import Auction, Gap, Item, Unreadable


def auction(auction_id: int, **changes) -> Auction:
    fields = {
        "auction_id": auction_id,
        "number": auction_id - 700,
        "url": f"https://www.eaukcionai.lt/evs/pages/auction.do?id={auction_id}",
        "kind": "Kiti aukcionai",
        "type": "Pirminis kiti aukcionai",
        "status": "Paskelbtas",
        "start_date": "2026-10-20T09:00:00",
        "end_date": "2026-10-21T13:59:59",
        "registration_start": "2026-10-12T00:00:00",
        "registration_end": None,
        "starting_price_eur": 1234.56,
        "highest_bid_eur": None,
        "first_seen": date(2026, 10, 1),
        "last_seen": date(2026, 10, 2),
        "last_fetched": datetime(2026, 10, 2, 0, 31, 5, tzinfo=UTC),
        "final_status_seen_at": None,
        "done": False,
    }
    return Auction(**fields | changes)


def test_writes_sorted_rows_with_fixed_key_order(tmp_path):
    state = store.State(
        auctions={339283: auction(339283), 300000: auction(300000, status="Atšauktos", done=True)},
        items={
            339283: (
                Item(
                    auction_id=339283, item_no=1, name="Mechaninės dirbtuvės", area_m2=524.67, address="Šilutės r. sav."
                ),
            ),
            300000: (
                Item(auction_id=300000, item_no=1, name="Butas"),
                Item(auction_id=300000, item_no=2, name="Rūsys"),
            ),
        },
    )
    store.write(tmp_path, state)

    auctions = (tmp_path / "auctions.jsonl").read_text(encoding="utf-8")
    assert auctions.splitlines()[0] == (
        '{"auction_id": 300000, "number": 299300, "url": "https://www.eaukcionai.lt/evs/pages/auction.do?id=300000", '
        '"kind": "Kiti aukcionai", "type": "Pirminis kiti aukcionai", "status": "Atšauktos", '
        '"start_date": "2026-10-20T09:00:00", "end_date": "2026-10-21T13:59:59", '
        '"registration_start": "2026-10-12T00:00:00", "registration_end": null, "starting_price_eur": 1234.56, '
        '"highest_bid_eur": null, "first_seen": "2026-10-01", "last_seen": "2026-10-02", '
        '"last_fetched": "2026-10-02T00:31:05Z", "final_status_seen_at": null, "done": true}'
    )
    assert auctions.endswith("}\n") and auctions.count("\n") == 2
    assert (tmp_path / "items.jsonl").read_text(encoding="utf-8") == (
        '{"auction_id": 300000, "item_no": 1, "name": "Butas", "share_sold": null, "subtype": null, '
        '"area_m2": null, "share_area_m2": null, "address": null, "unique_nr": null, "paskirtis": null}\n'
        '{"auction_id": 300000, "item_no": 2, "name": "Rūsys", "share_sold": null, "subtype": null, '
        '"area_m2": null, "share_area_m2": null, "address": null, "unique_nr": null, "paskirtis": null}\n'
        '{"auction_id": 339283, "item_no": 1, "name": "Mechaninės dirbtuvės", "share_sold": null, "subtype": null, '
        '"area_m2": 524.67, "share_area_m2": null, "address": "Šilutės r. sav.", "unique_nr": null, "paskirtis": null}\n'
    )


def test_round_trip_is_lossless_and_rewrite_is_byte_identical(tmp_path):
    original = store.State(
        auctions={
            1: auction(1, final_status_seen_at=datetime(2026, 10, 3, 0, 30, tzinfo=UTC), starting_price_eur=13200),
            2: auction(2),
        },
        items={1: (Item(auction_id=1, item_no=1, name="Sklypas", area_m2=2184.0),)},
    )
    store.write(tmp_path, original)
    first = [(tmp_path / name).read_bytes() for name in ("auctions.jsonl", "items.jsonl")]

    loaded = store.load(tmp_path)
    assert loaded == original
    store.write(tmp_path, loaded)
    assert [(tmp_path / name).read_bytes() for name in ("auctions.jsonl", "items.jsonl")] == first


def test_missing_files_load_as_empty(tmp_path):
    assert store.load(tmp_path / "nowhere") == store.State()


def test_gaps_round_trip_and_auction_drops_the_gap(tmp_path):
    when = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)
    store.write(tmp_path, store.State(auctions={1: auction(1)}, gaps={1: Gap(1, when), 2: Gap(2, when)}))
    loaded = store.load(tmp_path)
    assert loaded.gaps == {2: Gap(auction_id=2, checked_at=when)}
    assert list(loaded.auctions) == [1]


def test_unreadable_round_trip_and_auction_drops_the_mark(tmp_path):
    when = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
    store.write(
        tmp_path,
        store.State(auctions={1: auction(1)}, unreadable={1: Unreadable(1, when), 2: Unreadable(2, when)}),
    )
    loaded = store.load(tmp_path)
    assert loaded.unreadable == {2: Unreadable(auction_id=2, checked_at=when)}
    assert list(loaded.auctions) == [1]


def test_load_drops_items_with_no_auction(tmp_path):
    store.write(
        tmp_path,
        store.State(auctions={1: auction(1)}, items={1: (Item(auction_id=1, item_no=1, name="Butas"),)}),
    )
    orphan = (
        '{"auction_id": 9, "item_no": 1, "name": "Gone", "share_sold": null, "subtype": null, '
        '"area_m2": null, "share_area_m2": null, "address": null, "unique_nr": null, "paskirtis": null}\n'
    )
    items = tmp_path / "items.jsonl"
    items.write_text(items.read_text(encoding="utf-8") + orphan, encoding="utf-8")
    loaded = store.load(tmp_path)
    assert list(loaded.items) == [1]


def test_second_process_cannot_open_the_archive(tmp_path):
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys\nfrom pathlib import Path\nfrom eaukcionai import store\n"
            "with store.open_archive(Path(sys.argv[1])):\n"
            "    print('ready', flush=True)\n"
            "    sys.stdin.readline()\n",
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert holder.stdout is not None and holder.stdin is not None
    assert holder.stdout.readline() == b"ready\n"
    try:
        raised = False
        try:
            with store.open_archive(tmp_path):
                pass
        except store.ArchiveBusy:
            raised = True
        assert raised
    finally:
        holder.stdin.write(b"\n")
        holder.stdin.close()
        holder.wait(timeout=5)


def test_item_row_without_paskirtis_loads(tmp_path):
    store.write(tmp_path, store.State(auctions={1: auction(1)}))
    (tmp_path / "items.jsonl").write_text(
        '{"auction_id": 1, "item_no": 1, "name": "Žemės sklypas", "share_sold": null, "subtype": null, '
        '"area_m2": null, "share_area_m2": null, "address": null, "unique_nr": null}\n',
        encoding="utf-8",
    )
    assert store.load(tmp_path).items[1][0].paskirtis is None
