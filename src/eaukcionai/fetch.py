import time
from collections.abc import Callable

import httpx

from eaukcionai.model import Missing

USER_AGENT = "eaukcionai-archive (+https://github.com/grafke/eaukcionai-archive)"


class FetchError(RuntimeError):
    pass


class Client:
    """Polite HTTP client: one request per `interval` seconds, backoff on 5xx and timeouts."""

    def __init__(
        self,
        *,
        interval: float = 1.0,
        retries: int = 4,
        backoff: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )
        self._interval, self._retries, self._backoff = interval, retries, backoff
        self._sleep, self._clock = sleep, clock
        self._next_request_at = 0.0

    def get(self, url: str) -> str | Missing:
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(self._backoff**attempt)
            wait = self._next_request_at - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._next_request_at = self._clock() + self._interval
            try:
                response = self._http.get(url)
            except httpx.TransportError as error:
                failure = f"{type(error).__name__}: {error}"
                continue
            if response.status_code == 400:
                return Missing()
            if response.status_code >= 500:
                failure = f"HTTP {response.status_code}"
                continue
            if response.status_code != 200:
                raise FetchError(f"{url}: HTTP {response.status_code}")
            return response.text
        raise FetchError(f"{url}: {failure} after {self._retries + 1} attempts")
