import httpx
import pytest

from eaukcionai.fetch import USER_AGENT, Client, FetchError
from eaukcionai.model import Missing


class Recorder:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.now = 0.0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self.statuses.pop(0)
        if status == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(status, text=f"body {status}")

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def client(self) -> Client:
        return Client(transport=httpx.MockTransport(self.handle), sleep=self.sleep, clock=lambda: self.now)


def test_http_400_is_missing_without_retry(fixture_text):
    recorder = Recorder([int(fixture_text("auction_50000.status"))])
    assert recorder.client().get("https://example.test/auction.do?id=50000") == Missing()
    assert len(recorder.requests) == 1


def test_retries_5xx_and_timeouts_with_backoff_then_returns_body():
    recorder = Recorder([503, "timeout", 200])
    assert recorder.client().get("https://example.test/a") == "body 200"
    assert len(recorder.requests) == 3
    assert recorder.sleeps == [2.0, 4.0]
    assert recorder.requests[0].headers["User-Agent"] == USER_AGENT


def test_gives_up_after_retries():
    recorder = Recorder([500] * 5)
    with pytest.raises(FetchError, match=r"HTTP 500 after 5 attempts") as raised:
        recorder.client().get("https://example.test/a")
    assert raised.value.status_code == 500


def test_waits_one_second_between_requests():
    recorder = Recorder([200, 200])
    client = recorder.client()
    client.get("https://example.test/a")
    client.get("https://example.test/b")
    assert recorder.sleeps == [1.0]
