import threading
import time
from collections.abc import Callable

import httpx

from eaukcionai.model import Missing

USER_AGENT = "eaukcionai-archive (+https://github.com/grafke/eaukcionai-archive)"


class FetchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        self._schedule = threading.Lock()

    def get(self, url: str) -> str | Missing:
        failure = "no response"
        status_code: int | None = None
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(self._backoff**attempt)
            with self._schedule:
                wait = self._next_request_at - self._clock()
                self._next_request_at = max(self._next_request_at, self._clock()) + self._interval
            if wait > 0:
                self._sleep(wait)
            try:
                response = self._http.get(url)
            except httpx.TransportError as error:
                failure = f"{type(error).__name__}: {error}"
                status_code = None
                continue
            if response.status_code == 400:
                return Missing()
            if response.status_code >= 500:
                failure = f"HTTP {response.status_code}"
                status_code = response.status_code
                continue
            if response.status_code != 200:
                raise FetchError(f"{url}: HTTP {response.status_code}", status_code=response.status_code)
            return response.text
        raise FetchError(f"{url}: {failure} after {self._retries + 1} attempts", status_code=status_code)
