"""Redis 通用缓存 + 分布式锁（SET NX EX）。"""

import asyncio
from contextlib import asynccontextmanager

import redis

from app.core.redis import get_redis


async def cache_get(key: str) -> str | None:
    return await get_redis().get(key)


async def cache_set(key: str, value: str, ttl: int | None = None) -> None:
    r = get_redis()
    if ttl:
        await r.set(key, value, ex=ttl)
    else:
        await r.set(key, value)


async def cache_delete(key: str) -> None:
    await get_redis().delete(key)


async def acquire_lock(lock_key: str, token: str, ttl: int = 10) -> bool:
    """SET NX EX：成功抢锁返回 True（token 用于安全释放）。"""
    return bool(await get_redis().set(lock_key, token, nx=True, ex=ttl))


async def release_lock(lock_key: str, token: str) -> None:
    """Lua 原子释放：仅当持有者是自己时删除，防止误删他人锁。"""
    lua = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
    try:
        await get_redis().eval(lua, 1, lock_key, token)
    except redis.ResponseError:
        # fakeredis 等不支持 eval 的环境：check-and-delete 兜底（锁 TTL 保证最终安全）
        if await get_redis().get(lock_key) == token:
            await get_redis().delete(lock_key)


@asynccontextmanager
async def locked(lock_key: str, ttl: int = 10, wait: float = 30.0):
    """分布式锁上下文管理器：等待获取，超时抛 TimeoutError。"""
    token = f"{asyncio.get_event_loop().time()}-{id(asyncio.current_task() or object())}"
    deadline = asyncio.get_event_loop().time() + wait
    while not await acquire_lock(lock_key, token, ttl):
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"lock timeout: {lock_key}")
        await asyncio.sleep(0.2)
    try:
        yield
    finally:
        await release_lock(lock_key, token)
