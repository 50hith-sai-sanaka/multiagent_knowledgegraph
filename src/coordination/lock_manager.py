"""
Redis Distributed Lock Manager
File: src/coordination/lock_manager.py
Story: STORY-003

Provides SemanticLockManager — acquires/releases Redis locks with:
  - Sorted multi-key acquisition (deadlock prevention)
  - Atomic Lua-based release (foreign token cannot steal lock)
  - asyncio.Lock fallback when USE_REDIS=false
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class LockTimeoutError(Exception):
    """Raised when a lock cannot be acquired within timeout_ms."""


class SemanticLockManager:
    """
    Distributed lock manager using Redis SETNX + TTL.

    All lock_keys are always acquired in sorted lexicographical order
    to prevent deadlocks across concurrent agents.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_ms: int = 10_000,
        timeout_ms: int = 5_000,
        use_redis: bool | None = None,
    ):
        from dotenv import load_dotenv

        load_dotenv()

        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ttl_ms = ttl_ms
        self.timeout_ms = timeout_ms

        if use_redis is None:
            use_redis = os.getenv("USE_REDIS", "true").lower() != "false"
        self._use_redis = use_redis

        self._redis = None
        self._local_locks: dict[str, asyncio.Lock] = {}

    async def connect(self) -> None:
        """Open Redis connection. Call once at startup."""
        if self._use_redis:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("SemanticLockManager connected to Redis at %s", self.redis_url)
        else:
            logger.info("SemanticLockManager using asyncio.Lock fallback (USE_REDIS=false)")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def acquire(self, lock_keys: list[str]) -> dict[str, str]:
        """
        Acquire locks for all keys in sorted order.
        Returns Dict[key -> token]. Pass to release().
        Raises LockTimeoutError if any lock cannot be acquired.
        """
        sorted_keys = sorted(lock_keys)  # Deadlock prevention
        tokens: dict[str, str] = {}
        if self._use_redis and self._redis is None:
            raise RuntimeError("Redis lock manager is not connected; call await connect() before acquire()")
        deadline = time.monotonic() + self.timeout_ms / 1000.0
        try:
            for key in sorted_keys:
                token = str(uuid.uuid4())
                acquired = False

                while time.monotonic() < deadline:
                    if self._use_redis:
                        ok = await self._redis.set(f"lock:{key}", token, px=self.ttl_ms, nx=True)
                        if ok:
                            acquired = True
                            break
                    else:
                        if key not in self._local_locks:
                            self._local_locks[key] = asyncio.Lock()
                        lock = self._local_locks[key]
                        try:
                            await asyncio.wait_for(lock.acquire(), timeout=0.05)
                            acquired = True
                            break
                        except asyncio.TimeoutError:
                            pass

                    await asyncio.sleep(0.05)

                if not acquired:
                    raise LockTimeoutError(f"Could not acquire lock for '{key}' within {self.timeout_ms}ms")
                tokens[key] = token
        except BaseException:
            try:
                await asyncio.shield(self.release(tokens))
            except Exception:
                logger.exception("Failed to release partial semantic locks")
            raise

        logger.debug("Acquired %d locks: %s", len(tokens), list(tokens.keys()))
        return tokens

    async def release(self, tokens: dict[str, str]) -> None:
        """Release locks using token verification. Silent on already‑released locks."""
        for key, token in tokens.items():
            if self._use_redis and self._redis:
                result = await self._redis.eval(_RELEASE_SCRIPT, 1, f"lock:{key}", token)
                if result == 0:
                    logger.warning("Lock for '%s' was already released or stolen", key)
            else:
                lock = self._local_locks.get(key)
                if lock and lock.locked():
                    lock.release()

        logger.debug("Released %d locks", len(tokens))

    @asynccontextmanager
    async def locked(self, lock_keys: list[str]):
        """
        Async context manager: acquire → yield → release (always).

        Usage:
          async with lock_manager.locked(["key1", "key2"]):
              # safe work here
        """
        tokens = await self.acquire(lock_keys)
        try:
            yield tokens
        finally:
            await self.release(tokens)
