import pytest

from eaukcionai.detail import ParseError, parse_detail
from eaukcionai.listing import parse_listing
from eaukcionai.model import AuctionFields, Detail, Item


def test_bailiff_auction_with_two_items(fixture_text):
    assert parse_detail(fixture_text("auction_337594.html"), 337594) == Detail(
        auction_fields=AuctionFields(
            number=336875,
            kind="Antstolių varžytynės",
            type="Antrosios",
            status="Baigtos",
            start_date="2026-09-09T10:30:08",
            end_date="2026-10-09T10:35:59",
            registration_start=None,
            registration_end=None,
            starting_price_eur=13200,
            highest_bid_eur=13200,
        ),
        items=(
            Item(
                auction_id=337594,
                item_no=1,
                name="Sandėlis",
                share_sold="1/1",
                subtype="Patalpos/Butai",
                area_m2=14.6,
                share_area_m2=14.6,
                address="Telšių r. sav. Telšių m. Mažoji Kalno g. 13",
                unique_nr="7892-0001-6022:0003",
            ),
            Item(
                auction_id=337594,
                item_no=2,
                name="Butas",
                share_sold="1/1",
                subtype="Patalpos/Butai",
                area_m2=44.36,
                share_area_m2=44.36,
                address="Telšių r. sav. Telšių m. Mažoji Kalno g. 13-11",
                unique_nr="7892-0001-6011:0006",
            ),
        ),
    )


def test_other_auction_has_registration_dates_and_no_bid(fixture_text):
    assert parse_detail(fixture_text("auction_339283.html"), 339283) == Detail(
        auction_fields=AuctionFields(
            number=339218,
            kind="Kiti aukcionai",
            type="Pirminis kiti aukcionai",
            status="Paskelbtas",
            start_date="2026-10-20T09:00:00",
            end_date="2026-10-21T13:59:59",
            registration_start="2026-10-12T00:00:00",
            registration_end="2026-10-14T23:59:59",
            starting_price_eur=50000,
            highest_bid_eur=None,
        ),
        items=(
            Item(
                auction_id=339283,
                item_no=1,
                name="Mechaninės dirbtuvės",
                share_sold="1/1",
                subtype="Pastatai",
                area_m2=524.67,
                share_area_m2=524.67,
                address="Šilutės r. sav. Klugonų k. Užlieknių g. 12",
                unique_nr="4400-4101-5550",
            ),
        ),
    )


def test_cancelled_auction(fixture_text):
    detail = parse_detail(fixture_text("auction_300000.html"), 300000)
    assert (detail.auction_fields.status, detail.auction_fields.end_date, detail.auction_fields.starting_price_eur) == (
        "Atšauktos",
        "2025-02-07T11:57:59",
        12000,
    )
    assert [(i.name, i.address) for i in detail.items] == [
        ("Butas Nr.10", "Marijampolės sav. Želsvos k. Želsvelės g. 3-10")
    ]


def test_land_areas_in_ares_become_square_metres(fixture_text):
    items = parse_detail(fixture_text("auction_338315.html"), 338315).items
    assert [(i.item_no, i.name, i.share_sold, i.area_m2, i.share_area_m2) for i in items[:3]] == [
        (1, "Žemės sklypas", "1092/2184", 2184.0, 1092.0),
        (2, "Gyvenamas namas", "1/2", 136.9, 68.45),
        (3, "Daržinė", "1/2", None, None),
    ]
    assert len(items) == 6


def test_rental_auction_uses_rental_labels(fixture_text):
    detail = parse_detail(fixture_text("auction_338446.html"), 338446)
    assert (detail.auction_fields.kind, detail.auction_fields.starting_price_eur) == ("Nuomos konkursai", 2)
    assert detail.items == (
        Item(
            auction_id=338446,
            item_no=1,
            name="Žemės sklypas",
            share_sold="22003/43003",
            subtype="Sklypai",
            area_m2=43003.0,
            share_area_m2=22003.0,
            address="Ignalinos r. sav. Ignalinos m.",
            unique_nr="4400-1645-5120",
        ),
    )


def test_vehicle_has_no_address(fixture_text):
    assert parse_detail(fixture_text("auction_338314.html"), 338314).items == (
        Item(
            auction_id=338314,
            item_no=1,
            name="DEUTZ-FAHR Agrokid 220DT",
            subtype="Traktoriai, savaeigės mašinos, priekabos, puspriekabės",
        ),
    )


def test_page_without_core_dates_is_a_parse_error():
    with pytest.raises(ParseError, match="auction 1: no Pradžios data"):
        parse_detail("<html><body><main><h2>Nr. 5</h2></main></body></html>", 1)


def _page(name: str, description: str, about: str = "", second: tuple[str, str] | None = None) -> str:
    blocks = f"""
    <div class="product_desc">
      <h2>Parduodamas turtas: {name}</h2>
      <ul class="list"><li><span class="left">Aprašymas:</span><span class="right">{description}</span></li></ul>
    </div>
    """
    if second is not None:
        blocks += f"""
        <div class="product_desc">
          <h2>Parduodamas turtas: {second[0]}</h2>
          <ul class="list"><li><span class="left">Aprašymas:</span><span class="right">{second[1]}</span></li></ul>
        </div>
        """
    return f"""
    <html><body>
    <div class="load_block"><ul class="list">
      <li><span class="left">Pradžios data:</span><span class="right">2026-10-20 09:00:00</span></li>
      <li><span class="left">Pabaigos data:</span><span class="right">2026-10-21 13:59:59</span></li>
      <li><span class="left">Apie objektą:</span><span class="right">{about}</span></li>
    </ul></div>
    <main><h2>Nr. 9</h2></main>
    {blocks}
    </body></html>
    """


def test_land_plot_paskirtis_comes_from_the_item_description():
    detail = parse_detail(
        _page(
            "Žemės sklypas",
            "Daikto pagrindinė naudojimo paskirtis: Kita.",
            about="pagrindinė žemės sklypo naudojimo paskirtis – miškų ūkio",
        ),
        1,
    )
    assert [item.paskirtis for item in detail.items] == ["Kita"]


def test_land_plot_paskirtis_falls_back_to_apie_objekta():
    detail = parse_detail(
        _page("Žemės sklypas", "", about="pagrindinė žemės sklypo naudojimo paskirtis – miškų ūkio"),
        1,
    )
    assert [item.paskirtis for item in detail.items] == ["Miškų ūkio"]


def test_paskirtis_stays_on_the_land_plot_when_a_building_shares_the_page():
    detail = parse_detail(
        _page(
            "Žemės sklypas",
            "Daikto pagrindinė naudojimo paskirtis: Žemės ūkio.",
            about="pagrindinė žemės sklypo naudojimo paskirtis – miškų ūkio",
            second=("Gyvenamas namas", "Daikto pagrindinė naudojimo paskirtis: Kita."),
        ),
        1,
    )
    assert [(item.name, item.paskirtis) for item in detail.items] == [
        ("Žemės sklypas", "Žemės ūkio"),
        ("Gyvenamas namas", None),
    ]


def test_rental_right_is_not_a_land_plot_purpose():
    detail = parse_detail(
        _page("Valstybinės žemės sklypo nuomos teisė", "Daikto pagrindinė naudojimo paskirtis: Kita."),
        1,
    )
    assert [item.paskirtis for item in detail.items] == [None]


def test_listing_page(fixture_text):
    page = parse_listing(fixture_text("listing_page0.html"))
    assert page.last_page == 58
    assert page.auction_ids[:3] == (338321, 338315, 338322)
    assert len(page.auction_ids) == 20
