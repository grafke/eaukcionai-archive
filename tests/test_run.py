from datetime import UTC, date, datetime

import httpx

from eaukcionai import store
from eaukcionai.fetch import Client
from eaukcionai.lifecycle import reconcile
from eaukcionai.model import AuctionFields, Detail
from eaukcionai.run import main


def client(routes: dict[str, tuple[int, str]]) -> Client:
    def handle(request: httpx.Request) -> httpx.Response:
        key = request.url.params.get("id") or f"page={request.url.params['page']}"
        status, body = routes.get(key, (400, ""))
        return httpx.Response(status, text=body)

    return Client(transport=httpx.MockTransport(handle), interval=0, sleep=lambda _: None)


def seeded_state(tmp_path) -> bytes:
    fields = AuctionFields(
        number=280444,
        kind="Antstolių varžytynės",
        status="Vykstančios",
        start_date="2025-01-08T11:57:44",
        end_date="2025-02-07T11:57:59",
    )
    old = reconcile(300000, None, Detail(fields, ()), live=True, now=datetime(2025, 2, 1, tzinfo=UTC))
    store.write(tmp_path, store.State(auctions={300000: old}))
    return (tmp_path / "auctions.jsonl").read_bytes()


def test_empty_listing_aborts_before_touching_data(tmp_path):
    before = seeded_state(tmp_path)
    exit_code = main(["--data-dir", str(tmp_path)], client({"page=0": (200, "<html></html>")}))
    assert exit_code == 2
    assert (tmp_path / "auctions.jsonl").read_bytes() == before


def test_parse_failure_keeps_record_writes_the_rest_and_exits_1(tmp_path, fixture_text):
    before = seeded_state(tmp_path)
    routes = {
        "page=0": (200, fixture_text("listing_page0.html")),
        "338315": (200, fixture_text("auction_338315.html")),
        "300000": (200, "<html><body>maintenance</body></html>"),
    }
    exit_code = main(["--data-dir", str(tmp_path), "--max-pages", "1"], client(routes))

    assert exit_code == 1
    state = store.load(tmp_path)
    assert sorted(state.auctions) == [300000, 338315]
    assert (tmp_path / "auctions.jsonl").read_bytes().startswith(before)
    fetched = state.auctions[338315]
    assert (fetched.status, fetched.first_seen, fetched.done) == ("Vykstančios", datetime.now(UTC).date(), False)
    assert [i.name for i in state.items[338315]][:2] == ["Žemės sklypas", "Gyvenamas namas"]
    assert state.auctions[300000].last_seen == date(2025, 2, 1)
