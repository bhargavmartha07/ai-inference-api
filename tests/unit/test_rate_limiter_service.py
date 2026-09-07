from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.rate_limiter_service import RateLimiterService


@pytest.mark.asyncio
async def test_request_is_allowed():
    service = RateLimiterService()

    service.script = AsyncMock(
        return_value=[1, 0]
    )

    allowed, retry_after = await service.check_limit(
        "127.0.0.1"
    )

    assert allowed is True
    assert retry_after == 0

    service.script.assert_awaited_once()

    kwargs = service.script.await_args.kwargs

    assert kwargs["keys"] == ["rate_limit:127.0.0.1"]
    assert kwargs["args"][2] == 5
    assert kwargs["args"][3] == 60

    await service.close()


@pytest.mark.asyncio
async def test_request_is_blocked():
    service = RateLimiterService()

    service.script = AsyncMock(
        return_value=[0, 42]
    )

    allowed, retry_after = await service.check_limit(
        "127.0.0.1"
    )

    assert allowed is False
    assert retry_after == 42

    service.script.assert_awaited_once()

    await service.close()