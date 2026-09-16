import asyncio
from contextlib import asynccontextmanager, suppress
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from time import monotonic, time
from typing import TYPE_CHECKING, Any

import aiohttp

from stepik_autopilot.core.exceptions import ExternalServiceError
from stepik_autopilot.settings import Settings

HTTP_ERROR = 400
HTTP_TOO_MANY_REQUESTS = 429
if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator


def response_error_message(prefix: str, status: int, payload: object) -> str:
    details = [f"HTTP {status}"]
    with suppress(ValueError):
        details.append(HTTPStatus(status).phrase)
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error.replace("_", "").replace("-", "").isalnum():
            details.append(f"error={error}")
    return f"{prefix} ({'; '.join(details)})"


def _network_error_message(prefix: str, error: aiohttp.ClientError) -> str:
    detail = " ".join(str(error).split())
    return f"{prefix} ({type(error).__name__}: {detail})" if detail else f"{prefix} ({type(error).__name__})"


class StepikTokenProvider:
    def __init__(self, session: aiohttp.ClientSession, settings: Settings, limiter: StepikRateLimiter) -> None:
        self._session, self._settings, self._limiter = session, settings, limiter
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        if self._access_token is not None and monotonic() < self._expires_at:
            return self._access_token
        async with self._lock:
            if self._access_token is not None and monotonic() < self._expires_at:
                return self._access_token
            base_url = str(self._settings.stepik.base_url).rstrip("/")
            url = f"{base_url}/oauth2/token/"
            headers = {
                "Authorization": aiohttp.encode_basic_auth(
                    self._settings.stepik.oauth.client_id,
                    self._settings.stepik.oauth.client_secret.get_secret_value(),
                )
            }
            try:
                async with self._limiter.request_slot():
                    async with self._session.post(
                        url, data={"grant_type": "client_credentials"}, headers=headers
                    ) as response:
                        payload: object = await response.json(content_type=None)
                        if response.status >= HTTP_ERROR:
                            msg = response_error_message("Stepik OAuth token request failed", response.status, payload)
                            raise ExternalServiceError(msg)
                        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
                            msg = "Stepik OAuth token response is malformed (access_token is missing)"
                            raise ExternalServiceError(msg)
            except aiohttp.ClientError as error:
                msg = _network_error_message("Stepik OAuth token request failed", error)
                raise ExternalServiceError(msg) from error
            access_token = payload["access_token"]
            if not isinstance(access_token, str):
                msg = "Stepik OAuth token response is malformed"
                raise ExternalServiceError(msg)
            self._access_token = access_token
            expires_in = payload.get("expires_in", 3600)
            self._expires_at = monotonic() + max(0, int(expires_in) - 60)
            return access_token


class StepikRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._rate = settings.stepik.requests_per_second
        self._capacity = float(settings.stepik.request_burst)
        self._tokens = self._capacity
        self._updated_at = monotonic()
        self._lock = asyncio.Lock()
        self._in_flight = asyncio.Semaphore(settings.stepik.max_in_flight)
        self._blocked_until = 0.0

    async def acquire(self) -> None:
        """Take one token from the application-wide token bucket."""
        while True:
            async with self._lock:
                now = monotonic()
                self._tokens = min(self._capacity, self._tokens + (now - self._updated_at) * self._rate)
                self._updated_at = now
                blocked_for = self._blocked_until - now
                if blocked_for <= 0 and self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait_for = max(blocked_for, (1 - self._tokens) / self._rate)
            await asyncio.sleep(wait_for)

    @asynccontextmanager
    async def request_slot(self) -> AsyncGenerator[None]:
        async with self._in_flight:
            await self.acquire()
            yield

    async def block(self, retry_after: str | None) -> None:
        seconds = 1.0
        if retry_after:
            try:
                seconds = max(0.0, float(retry_after))
            except ValueError:
                try:
                    seconds = max(0.0, parsedate_to_datetime(retry_after).timestamp() - time())
                except TypeError, ValueError, IndexError:
                    seconds = 1.0
        async with self._lock:
            self._blocked_until = max(self._blocked_until, monotonic() + seconds)


class StepikApiClient:
    """Authenticated, rate-limited transport shared by resource repositories."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        tokens: StepikTokenProvider,
        settings: Settings,
        limiter: StepikRateLimiter,
    ) -> None:
        self._session, self._tokens, self._settings, self._limiter = session, tokens, settings, limiter

    async def request(
        self,
        method: str,
        path: str,
        params: list[tuple[str, str]] | None = None,
        json: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        token = await self._tokens.token()
        base_url = str(self._settings.stepik.base_url).rstrip("/")
        url = f"{base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with self._limiter.request_slot():
                async with self._session.request(method, url, headers=headers, params=params, json=json) as response:
                    payload: object = await response.json(content_type=None)
                    if response.status == HTTP_TOO_MANY_REQUESTS:
                        await self._limiter.block(response.headers.get("Retry-After"))
                    if response.status >= HTTP_ERROR or not isinstance(payload, dict):
                        msg = response_error_message("Stepik API request failed", response.status, payload)
                        raise ExternalServiceError(msg)
                    return payload
        except aiohttp.ClientError as error:
            msg = _network_error_message("Stepik API request failed", error)
            raise ExternalServiceError(msg) from error

    async def paged(
        self, path: str, key: str, params: list[tuple[str, str]] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        page = 1
        while True:
            request_params = [*(params or []), ("page", str(page))]
            payload = await self.request("GET", path, params=request_params)
            values = payload.get(key)
            if not isinstance(values, list):
                msg = f"Stepik response has no {key!r} list"
                raise ExternalServiceError(msg)
            for value in values:
                if isinstance(value, dict):
                    yield value
            if not bool(payload.get("meta", {}).get("has_next")):
                return
            page += 1
