import hashlib
import json

import redis.asyncio as redis

from src.config import settings


class CacheService:
    def __init__(self):
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

    def _make_key(self, text: str) -> str:
        text_hash = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

        return f"sentiment:{text_hash}"

    async def get(self, text: str) -> dict | None:
        key = self._make_key(text)

        cached = await self.redis.get(key)

        if cached is None:
            return None

        return json.loads(cached)

    async def set(self, text: str, result: dict) -> None:
        key = self._make_key(text)

        await self.redis.set(
            key,
            json.dumps(result),
            ex=settings.cache_ttl_seconds,
        )

    async def close(self) -> None:
        await self.redis.aclose()