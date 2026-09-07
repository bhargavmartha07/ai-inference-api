import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from src.services.cache_service import CacheService


@pytest.mark.asyncio
async def test_cache_miss():
    service = CacheService()

    service.redis.get = AsyncMock(return_value=None)

    result = await service.get("hello")

    assert result is None
    service.redis.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_hit():
    service = CacheService()

    cached_result = {
        "sentiment": "POSITIVE",
        "score": 0.99,
    }

    service.redis.get = AsyncMock(
        return_value=json.dumps(cached_result)
    )

    result = await service.get("hello")

    assert result == cached_result


@pytest.mark.asyncio
async def test_cache_key_is_derived_from_text():
    text = "Great product!"

    service = CacheService()

    service.redis.get = AsyncMock(return_value=None)

    await service.get(text)

    key = service.redis.get.await_args.args[0]

    expected_key = (
        "sentiment:"
        + hashlib.sha256(text.encode("utf-8")).hexdigest()
    )

    assert key == expected_key


@pytest.mark.asyncio
async def test_cache_set_uses_ttl():
    service = CacheService()

    service.redis.set = AsyncMock()

    await service.set(
        "hello",
        {
            "sentiment": "POSITIVE",
            "score": 0.99,
        },
    )

    service.redis.set.assert_awaited_once()

    key = service.redis.set.await_args.args[0]

    kwargs = service.redis.set.await_args.kwargs

    assert kwargs["ex"] == 300

    expected_key = (
        "sentiment:"
        + hashlib.sha256(b"hello").hexdigest()
    )

    assert key == expected_key