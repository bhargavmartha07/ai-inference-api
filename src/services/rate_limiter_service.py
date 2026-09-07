import time

import redis.asyncio as redis

from src.config import settings


RATE_LIMIT_SCRIPT = """
local key = KEYS[1]

local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local window = tonumber(ARGV[4])

redis.call("ZREMRANGEBYSCORE", key, 0, window_start)

local count = redis.call("ZCARD", key)

if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")

    if #oldest > 0 then
        local oldest_timestamp = tonumber(oldest[2])
        local retry_after = math.ceil(
            oldest_timestamp + window - now
        )

        if retry_after < 1 then
            retry_after = 1
        end

        return {0, retry_after}
    end

    return {0, window}
end

redis.call("ZADD", key, now, tostring(now))
redis.call("EXPIRE", key, window)

return {1, 0}
"""


class RateLimiterService:
    def __init__(self):
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

        self.script = self.redis.register_script(
            RATE_LIMIT_SCRIPT
        )

    async def check_limit(self, client_ip: str) -> tuple[bool, int]:
        key = f"rate_limit:{client_ip}"

        now = time.time()
        window_start = now - settings.rate_limit_window_seconds

        result = await self.script(
            keys=[key],
            args=[
                now,
                window_start,
                settings.rate_limit_amount,
                settings.rate_limit_window_seconds,
            ],
        )

        allowed = bool(result[0])
        retry_after = int(result[1])

        return allowed, retry_after

    async def close(self) -> None:
        await self.redis.aclose()