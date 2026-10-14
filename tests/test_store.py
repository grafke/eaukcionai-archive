from datetime import UTC, date, datetime

from eaukcionai import store
from eaukcionai.model import Auction, Item


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
        '"area_m2": null, "share_area_m2": null, "address": null, "unique_nr": null}\n'
        '{"auction_id": 300000, "item_no": 2, "name": "Rūsys", "share_sold": null, "subtype": null, '
        '"area_m2": null, "share_area_m2": null, "address": null, "unique_nr": null}\n'
        '{"auction_id": 339283, "item_no": 1, "name": "Mechaninės dirbtuvės", "share_sold": null, "subtype": null, '
        '"area_m2": 524.67, "share_area_m2": null, "address": "Šilutės r. sav.", "unique_nr": null}\n'
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
