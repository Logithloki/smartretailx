"""Per-task read-through cache (ADR-03).

Deliberately in-process, not ElastiCache. At demo scale a shared cache would
cost more per month than the entire rest of the stack, and the catalogue is
small and read-heavy. The trade-off, which the report states plainly: with N
tasks there are N caches, so a write is only guaranteed visible everywhere
after the TTL expires. That window is bounded at 30 seconds and is acceptable
for a product catalogue - it would not be for stock levels, which is exactly
why stock is served from Postgres and never cached.

Writes invalidate the local task's entry immediately, so the admin who made
the change always sees it; other tasks converge within the TTL.
"""

from __future__ import annotations

import logging
import threading

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class ProductCache:
    def __init__(self, maxsize: int = 500, ttl: int = 30):
        # Uvicorn serves requests from a thread pool, so the cache must be
        # guarded - TTLCache is not thread-safe on its own.
        self._lock = threading.Lock()
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        with self._lock:
            try:
                value = self._cache[key]
            except KeyError:
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._cache[key] = value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)
