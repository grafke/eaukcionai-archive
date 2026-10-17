import sqlite3
from datetime import UTC, date, datetime

from eaukcionai import store
from eaukcionai.build_site import build, municipality, settlement
from eaukcionai.detail import parse_detail
from eaukcionai.lifecycle import reconcile
from eaukcionai.model import Auction, Item


def test_item_rows_join_items_to_auctions_with_municipality(tmp_path, fixture_text):
    detail = parse_detail(fixture_text("auction_337594.html"), 337594)
    auction = reconcile(337594, None, detail, live=True, now=datetime(2026, 10, 9, 0, 30, tzinfo=UTC))
    store.write(tmp_path, store.State(auctions={337594: auction}, items={337594: detail.items}))

    build(tmp_path, tmp_path / "auctions.sqlite")

    db = sqlite3.connect(tmp_path / "auctions.sqlite")
    rows = db.execute(
        "SELECT item_no, name, municipality, settlement, kind, status, starting_price_eur, end_date, url, done"
        " FROM item_rows ORDER BY item_no"
    ).fetchall()
    assert rows == [
        (
            1,
            "Sandėlis",
            "Telšių r. sav.",
            "Telšių m.",
            "Antstolių varžytynės",
            "Baigtos",
            13200,
            "2026-10-09T10:35:59",
            "https://www.eaukcionai.lt/evs/pages/auction.do?id=337594",
            0,
        ),
        (
            2,
            "Butas",
            "Telšių r. sav.",
            "Telšių m.",
            "Antstolių varžytynės",
            "Baigtos",
            13200,
            "2026-10-09T10:35:59",
            "https://www.eaukcionai.lt/evs/pages/auction.do?id=337594",
            0,
        ),
    ]
    assert db.execute("SELECT last_fetched FROM auctions").fetchone() == ("2026-10-09T00:30:00Z",)
    assert db.execute("SELECT item_no, round(price_per_m2, 2) FROM item_rows ORDER BY item_no").fetchall() == [
        (1, 904.11),
        (2, 297.57),
    ]


def test_price_per_m2_only_when_area_and_price_exist(tmp_path):
    auction = Auction(
        auction_id=1,
        number=1,
        url="https://www.eaukcionai.lt/evs/pages/auction.do?id=1",
        kind=None,
        type=None,
        status="Paskelbtas",
        start_date="2026-10-01T00:00:00",
        end_date="2026-10-02T00:00:00",
        registration_start=None,
        registration_end=None,
        starting_price_eur=1000,
        highest_bid_eur=None,
        first_seen=date(2026, 10, 1),
        last_seen=date(2026, 10, 1),
        last_fetched=datetime(2026, 10, 1, tzinfo=UTC),
        final_status_seen_at=None,
        done=False,
    )
    no_price = Auction(
        auction_id=2,
        number=2,
        url="https://www.eaukcionai.lt/evs/pages/auction.do?id=2",
        kind=None,
        type=None,
        status="Paskelbtas",
        start_date="2026-10-01T00:00:00",
        end_date="2026-10-02T00:00:00",
        registration_start=None,
        registration_end=None,
        starting_price_eur=None,
        highest_bid_eur=None,
        first_seen=date(2026, 10, 1),
        last_seen=date(2026, 10, 1),
        last_fetched=datetime(2026, 10, 1, tzinfo=UTC),
        final_status_seen_at=None,
        done=False,
    )
    store.write(
        tmp_path,
        store.State(
            auctions={1: auction, 2: no_price},
            items={
                1: (
                    Item(auction_id=1, item_no=1, name="Be ploto"),
                    Item(auction_id=1, item_no=2, name="Nulis", area_m2=0),
                    Item(auction_id=1, item_no=3, name="Sklypas", area_m2=10),
                ),
                2: (Item(auction_id=2, item_no=1, name="Be kainos", area_m2=20),),
            },
        ),
    )
    build(tmp_path, tmp_path / "auctions.sqlite")

    db = sqlite3.connect(tmp_path / "auctions.sqlite")
    assert db.execute(
        "SELECT auction_id, item_no, price_per_m2 FROM item_rows ORDER BY auction_id, item_no"
    ).fetchall() == [
        (1, 1, None),
        (1, 2, None),
        (1, 3, 100.0),
        (2, 1, None),
    ]


def test_municipality_prefixes():
    assert [
        municipality(a)
        for a in (
            "Vilniaus m. sav. Vilniaus m. Gedimino pr. 1",
            "Marijampolės sav. Želsvos k. Želsvelės g. 3-10",
            "Kazlų Rūdos sav. Kazlų Rūdos m. Atžalyno g. 2",
            "Vilnius, Gedimino pr. 1",
            None,
        )
    ] == ["Vilniaus m. sav.", "Marijampolės sav.", "Kazlų Rūdos sav.", None, None]


def test_settlement_is_the_locality_after_the_municipality():
    assert [
        settlement(a)
        for a in (
            "Vilniaus m. sav. Vilniaus m. Gedimino pr. 1",
            "Marijampolės sav. Želsvos k. Želsvelės g. 3-10",
            "Kazlų Rūdos sav. Kazlų Rūdos m. Atžalyno g. 2",
            "Pakruojo r. sav. Lygumų mstl. Juknaičių g. 12",
            "Panevėžio r. sav. Steponiškio vs.",
            "Akmenės r. sav. Naujosios Akmenės m.",
            "Vilniaus m. sav. Vilniaus m. Pylimo g. 11-16A",
            "Radviliškio r. sav. Radviliškio r. sav. teritorija",
            "Vilnius, Gedimino pr. 1",
            None,
        )
    ] == [
        "Vilniaus m.",
        "Želsvos k.",
        "Kazlų Rūdos m.",
        "Lygumų mstl.",
        "Steponiškio vs.",
        "Naujosios Akmenės m.",
        "Vilniaus m.",
        None,
        None,
        None,
    ]
