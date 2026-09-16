import aiohttp
import pytest

from stepik_autopilot.presentation.providers import ApplicationProvider


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_http_session_uses_system_threaded_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = aiohttp.ThreadedResolver()
    resolver_created = False

    def create_resolver() -> aiohttp.ThreadedResolver:
        nonlocal resolver_created
        resolver_created = True
        return resolver

    monkeypatch.setattr(aiohttp, "ThreadedResolver", create_resolver)
    provider = ApplicationProvider()
    session_factory = provider.create_http_session()
    session = await anext(session_factory)
    try:
        assert isinstance(session.connector, aiohttp.TCPConnector)
        assert resolver_created
    finally:
        await session_factory.aclose()
