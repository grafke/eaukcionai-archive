from datetime import UTC, date, datetime

from eaukcionai.lifecycle import needs_fetch, reconcile
from eaukcionai.model import Auction, AuctionFields, Detail, Item, Missing

ID = 337594


def page(status: str, highest_bid: int | None = None) -> Detail:
    fields = AuctionFields(
        number=336875,
        kind="Antstolių varžytynės",
        type="Antrosios",
        status=status,
        start_date="2026-09-09T10:30:08",
        end_date="2026-10-09T10:35:59",
        starting_price_eur=13200,
        highest_bid_eur=highest_bid,
    )
    return Detail(auction_fields=fields, items=(Item(auction_id=ID, item_no=1, name="Butas"),))


def night(day: str, hour: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, minute=30, tzinfo=UTC)


def lifecycle_fields(a: Auction) -> tuple:
    return (a.status, a.first_seen, a.last_seen, a.last_fetched, a.final_status_seen_at, a.done)


def test_live_then_gone_then_final_then_one_extra_fetch_then_done():
    n1 = reconcile(ID, None, page("Vykstančios"), live=True, now=night("2026-10-01"))
    assert n1 == Auction(
        auction_id=ID,
        number=336875,
        url="https://www.eaukcionai.lt/evs/pages/auction.do?id=337594",
        kind="Antstolių varžytynės",
        type="Antrosios",
        status="Vykstančios",
        start_date="2026-09-09T10:30:08",
        end_date="2026-10-09T10:35:59",
        registration_start=None,
        registration_end=None,
        starting_price_eur=13200,
        highest_bid_eur=None,
        first_seen=date(2026, 10, 1),
        last_seen=date(2026, 10, 1),
        last_fetched=night("2026-10-01"),
        final_status_seen_at=None,
        done=False,
    )

    n2 = reconcile(ID, n1, page("Vykstančios", 13200), live=False, now=night("2026-10-02"))
    assert lifecycle_fields(n2) == (
        "Vykstančios",
        date(2026, 10, 1),
        date(2026, 10, 1),
        night("2026-10-02"),
        None,
        False,
    )
    assert n2.highest_bid_eur == 13200
    assert needs_fetch(n2, live=False) is True

    n3 = reconcile(ID, n2, page("Baigtos", 13200), live=False, now=night("2026-10-03"))
    assert lifecycle_fields(n3) == (
        "Baigtos",
        date(2026, 10, 1),
        date(2026, 10, 1),
        night("2026-10-03"),
        night("2026-10-03"),
        False,
    )
    assert needs_fetch(n3, live=False) is True

    n4 = reconcile(ID, n3, page("Baigtos", 13200), live=False, now=night("2026-10-04"))
    assert lifecycle_fields(n4) == (
        "Baigtos",
        date(2026, 10, 1),
        date(2026, 10, 1),
        night("2026-10-04"),
        night("2026-10-03"),
        True,
    )
    assert needs_fetch(n4, live=False) is False


def test_rerun_on_the_same_night_does_not_count_as_the_extra_fetch():
    gone = reconcile(ID, None, page("Vykstančios"), live=True, now=night("2026-10-01"))
    first = reconcile(ID, gone, page("Įvykusios"), live=False, now=night("2026-10-03", hour=0))
    rerun = reconcile(ID, first, page("Įvykusios"), live=False, now=night("2026-10-03", hour=5))
    assert (rerun.final_status_seen_at, rerun.done) == (night("2026-10-03", hour=0), False)
    assert reconcile(ID, rerun, page("Įvykusios"), live=False, now=night("2026-10-04")).done is True


def test_final_status_seen_while_still_listed_is_finished_on_the_first_night_off_the_listing():
    listed = reconcile(ID, None, page("Baigtos"), live=True, now=night("2026-10-09"))
    assert (listed.final_status_seen_at, listed.done) == (night("2026-10-09"), False)
    assert reconcile(ID, listed, page("Baigtos"), live=False, now=night("2026-10-10")).done is True


def test_gives_up_more_than_30_days_after_last_listed_without_a_final_status():
    listed = reconcile(ID, None, page("Vykstančios"), live=True, now=night("2026-10-01"))
    day_30 = reconcile(ID, listed, page("Vykstančios"), live=False, now=night("2026-10-31"))
    day_31 = reconcile(ID, day_30, page("Vykstančios"), live=False, now=night("2026-11-01"))
    assert (day_30.done, day_31.done) == (False, True)
    assert (day_31.last_seen, day_31.final_status_seen_at) == (date(2026, 10, 1), None)


def test_http_400_on_a_known_auction_keeps_the_record_and_finishes_one_night_later():
    listed = reconcile(ID, None, page("Vykstančios", 500), live=True, now=night("2026-10-01"))
    missing = reconcile(ID, listed, Missing(), live=False, now=night("2026-10-02"))
    assert lifecycle_fields(missing) == (
        "Vykstančios",
        date(2026, 10, 1),
        date(2026, 10, 1),
        night("2026-10-02"),
        night("2026-10-02"),
        False,
    )
    assert missing.highest_bid_eur == 500
    assert reconcile(ID, missing, Missing(), live=False, now=night("2026-10-03")).done is True


def test_http_400_for_an_unknown_auction_records_nothing():
    assert reconcile(ID, None, Missing(), live=True, now=night("2026-10-01")) is None


def test_a_relisted_auction_is_fetched_again_and_not_done():
    listed = reconcile(ID, None, page("Baigtos"), live=True, now=night("2026-10-01"))
    finished = reconcile(ID, listed, page("Baigtos"), live=False, now=night("2026-10-02"))
    assert needs_fetch(finished, live=True) is True
    relisted = reconcile(ID, finished, page("Vykstančios"), live=True, now=night("2026-10-05"))
    assert (relisted.last_seen, relisted.final_status_seen_at, relisted.done) == (date(2026, 10, 5), None, False)


def test_needs_fetch_for_unknown_ids_only_when_listed():
    assert (needs_fetch(None, live=True), needs_fetch(None, live=False)) == (True, False)
