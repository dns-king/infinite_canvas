from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .schemas import TileStats


TileKey = tuple[int, int, int, str, int, str | None]


@dataclass
class CacheEntry:
    data: bytes
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    last_access: float = field(default_factory=time.monotonic)


class TileCache:
    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[TileKey, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: TileKey) -> CacheEntry | None:
        async with self._lock:
            self._expire_locked()
            entry = self._items.get(key)
            if entry is None:
                self._misses += 1
                return None
            entry.last_access = time.monotonic()
            self._items.move_to_end(key)
            self._hits += 1
            return entry

    async def peek(self, key: TileKey) -> CacheEntry | None:
        async with self._lock:
            self._expire_locked()
            return self._items.get(key)

    async def put(self, key: TileKey, data: bytes, metadata: dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._items[key] = CacheEntry(data=data, metadata=metadata or {})
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)

    async def stats(self) -> TileStats:
        async with self._lock:
            self._expire_locked()
            return TileStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._items),
                max_size=self.max_size,
            )

    def _expire_locked(self) -> None:
        if self.ttl_seconds <= 0:
            return
        now = time.monotonic()
        expired = [
            key for key, entry in self._items.items() if now - entry.created_at > self.ttl_seconds
        ]
        for key in expired:
            self._items.pop(key, None)

