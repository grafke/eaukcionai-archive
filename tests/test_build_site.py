import sqlite3
from datetime import UTC, datetime

from eaukcionai import store
from eaukcionai.build_site import build, municipality
from eaukcionai.detail import parse_detail
from eaukcionai.lifecycle import reconcile


def test_item_rows_join_items_to_auctions_with_municipality(tmp_path, fixture_text):
    detail = parse_detail(fixture_text("auction_337594.html"), 337594)
    auction = reconcile(337594, None, detail, live=True, now=datetime(2026, 10, 9, 0, 30, tzinfo=UTC))
    store.write(tmp_path, store.State(auctions={337594: auction}, items={337594: detail.items}))

    build(tmp_path, tmp_path / "auctions.sqlite")

    db = sqlite3.connect(tmp_path / "auctions.sqlite")
    rows = db.execute(
        "SELECT item_no, name, municipality, kind, status, starting_price_eur, end_date, url, done"
        " FROM item_rows ORDER BY item_no"
    ).fetchall()
    assert rows == [
        (
            1,
            "Sandėlis",
            "Telšių r. sav.",
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
            "Antstolių varžytynės",
            "Baigtos",
            13200,
            "2026-10-09T10:35:59",
            "https://www.eaukcionai.lt/evs/pages/auction.do?id=337594",
            0,
        ),
    ]
    assert db.execute("SELECT last_fetched FROM auctions").fetchone() == ("2026-10-09T00:30:00Z",)


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
