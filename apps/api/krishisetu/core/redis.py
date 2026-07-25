"""Redis client and cache helpers."""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from krishisetu.core.config import settings

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Get the async Redis client (singleton)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(
            str(settings().REDIS_URL),
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            retry_on_timeout=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection (on shutdown)."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def check_redis_connection() -> bool:
    """Health check: verify Redis is reachable."""
    try:
        redis = await get_redis()
        return await redis.ping()
    except Exception:
        return False
