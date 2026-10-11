"""Redis client for tokens / cache."""
from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

redis_client: Redis | None = None


async def init_redis() -> None:
    global redis_client
    if settings.redis_fake:
        from fakeredis.aioredis import FakeRedis

        redis_client = FakeRedis(decode_responses=True)
        await redis_client.ping()
        return
    redis_client = Redis.from_url(
        settings.redis_url, decode_responses=True, max_connections=50
    )
    await redis_client.ping()


async def close_redis() -> None:
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    return redis_client
