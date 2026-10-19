import httpx

from eaukcionai import store
from eaukcionai.fetch import Client
from eaukcionai.run import main as run_main
from eaukcionai.walk import CHECKPOINT_EVERY, main


def client(routes: dict[str, tuple[int, str]], requested: list[str] | None = None) -> Client:
    def handle(request: httpx.Request) -> httpx.Response:
        if requested is not None:
            requested.append(request.url.params["id"])
        status, body = routes.get(request.url.params["id"], (400, ""))
        return httpx.Response(status, text=body)

    return Client(transport=httpx.MockTransport(handle), interval=0, sleep=lambda _: None)


def page(status: str) -> str:
    return (
        '<div class="load_block"><ul class="list">'
        '<li><span class="left">Pradžios data:</span><span class="right">2020-06-01 09:00:00</span></li>'
        '<li><span class="left">Pabaigos data:</span><span class="right">2020-07-01 13:59:59</span></li>'
        f'<li><span class="left">Būsena:</span><span class="right"><span class="label-primary">{status}</span>'
        '<span class="label-default">Antstolių varžytynės</span></span></li>'
        "</ul></div>"
    )


def test_walk_settles_final_live_and_gap(tmp_path):
    routes = {"10": (200, page("Įvykęs")), "11": (400, ""), "12": (200, page("Paskelbtas"))}
    assert main(["10", "12", "--data-dir", str(tmp_path)], client(routes)) == 0
    state = store.load(tmp_path)
    assert state.auctions[10].done is True
    assert state.auctions[12].done is False
    assert list(state.gaps) == [11]
    assert 11 not in state.auctions


def test_second_run_requests_nothing(tmp_path):
    routes = {"10": (200, page("Įvykęs")), "11": (400, "")}
    assert main(["10", "11", "--data-dir", str(tmp_path)], client(routes)) == 0
    requested: list[str] = []
    assert main(["10", "11", "--data-dir", str(tmp_path)], client(routes, requested)) == 0
    assert requested == []


def test_isolated_server_errors_are_skipped_and_not_retried(tmp_path):
    routes = {
        "10": (200, page("Įvykęs")),
        "11": (500, ""),
        "12": (500, ""),
        "13": (200, page("Įvykęs")),
    }
    assert main(["10", "13", "--data-dir", str(tmp_path)], client(routes)) == 0
    state = store.load(tmp_path)
    assert list(state.auctions) == [10, 13]
    assert list(state.unreadable) == [11, 12]
    requested: list[str] = []
    assert main(["10", "13", "--data-dir", str(tmp_path)], client(routes, requested)) == 0
    assert requested == []


def test_a_run_of_server_errors_stops_and_retries_that_id(tmp_path):
    failing = client({"10": (200, page("Įvykęs")), "11": (500, ""), "12": (500, ""), "13": (500, "")})
    assert main(["10", "13", "--data-dir", str(tmp_path)], failing) == 1
    state = store.load(tmp_path)
    assert list(state.auctions) == [10]
    assert state.unreadable == {}
    requested: list[str] = []
    routes = {str(auction_id): (200, page("Įvykęs")) for auction_id in range(11, 14)}
    assert main(["10", "13", "--data-dir", str(tmp_path)], client(routes, requested)) == 0
    assert requested == ["11", "12", "13"]


def test_fetch_error_keeps_progress_and_resumes_at_that_id(tmp_path):
    first = client({"10": (200, page("Įvykęs")), "11": (429, "")})
    assert main(["10", "12", "--data-dir", str(tmp_path)], first) == 1
    assert list(store.load(tmp_path).auctions) == [10]
    requested: list[str] = []
    second = client({"11": (200, page("Įvykęs")), "12": (400, "")}, requested)
    assert main(["10", "12", "--data-dir", str(tmp_path)], second) == 0
    assert requested == ["11", "12"]


def test_unparseable_page_is_not_settled(tmp_path):
    routes = {"10": (200, page("Įvykęs")), "11": (200, "<html>maintenance</html>")}
    assert main(["10", "11", "--data-dir", str(tmp_path)], client(routes)) == 1
    state = store.load(tmp_path)
    assert 11 not in state.auctions
    assert 11 not in state.gaps
    assert 11 not in state.unreadable


def test_checkpoint_is_on_disk_before_the_next_batch(tmp_path):
    start = 100
    last = start + CHECKPOINT_EVERY
    seen: dict[str, int] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        auction_id = int(request.url.params["id"])
        if auction_id == last:
            seen["saved"] = len(store.load(tmp_path).auctions)
        return httpx.Response(200, text=page("Įvykęs"))

    http = Client(transport=httpx.MockTransport(handle), interval=0, sleep=lambda _: None)
    assert main([str(start), str(last), "--data-dir", str(tmp_path)], http) == 0
    assert seen["saved"] == CHECKPOINT_EVERY


def test_max_fetches_pauses_and_resume_continues(tmp_path):
    routes = {str(auction_id): (200, page("Įvykęs")) for auction_id in range(10, 15)}
    assert main(["10", "14", "--data-dir", str(tmp_path), "--max-fetches", "2"], client(routes)) == 3
    assert list(store.load(tmp_path).auctions) == [10, 11]
    requested: list[str] = []
    assert main(["10", "14", "--data-dir", str(tmp_path)], client(routes, requested)) == 0
    assert requested == ["12", "13", "14"]


def test_nightly_keeps_gaps_and_skips_walked_auctions(tmp_path):
    assert main(["10", "11", "--data-dir", str(tmp_path)], client({"10": (200, page("Įvykęs"))})) == 0
    gaps = (tmp_path / "gaps.jsonl").read_bytes()
    listing = (
        '<ul class="bid_list"><li><h2 class="no"><a href="auction.do?id=50">50</a></h2></li></ul>'
        '<a class="paginationLink" data-page="0">1</a>'
    )
    requested: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("id"):
            requested.append(request.url.params["id"])
            return httpx.Response(200, text=page("Paskelbtas"))
        return httpx.Response(200, text=listing)

    nightly = Client(transport=httpx.MockTransport(handle), interval=0, sleep=lambda _: None)
    assert run_main(["--data-dir", str(tmp_path)], nightly) == 0
    assert "10" not in requested and "11" not in requested
    assert (tmp_path / "gaps.jsonl").read_bytes() == gaps
