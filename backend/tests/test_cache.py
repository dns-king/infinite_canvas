import asyncio

from app.cache import TileCache


def test_lru_eviction() -> None:
    async def run() -> None:
        cache = TileCache(max_size=2, ttl_seconds=100)
        await cache.put((0, 0, 1, "forest", 512, None), b"a")
        await cache.put((1, 0, 1, "forest", 512, None), b"b")
        assert await cache.get((0, 0, 1, "forest", 512, None)) is not None
        await cache.put((2, 0, 1, "forest", 512, None), b"c")
        assert await cache.get((1, 0, 1, "forest", 512, None)) is None
        assert await cache.get((0, 0, 1, "forest", 512, None)) is not None

    asyncio.run(run())


def test_ttl_expiration() -> None:
    async def run() -> None:
        cache = TileCache(max_size=2, ttl_seconds=1)
        key = (0, 0, 1, "forest", 512, None)
        await cache.put(key, b"a")
        entry = await cache.get(key)
        assert entry is not None
        entry.created_at -= 5
        assert await cache.get(key) is None

    asyncio.run(run())

