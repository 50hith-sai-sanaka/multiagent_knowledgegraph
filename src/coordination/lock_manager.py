"""
Redis Distributed Lock Manager with Monotonic Fencing Tokens
File: src/coordination/lock_manager.py
Sprint: Sprint 1 (STORY-004)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Atomic Multi-Lock + Fencing Token Minting Script
# KEYS[1..N-1]: lock resource keys
# KEYS[N]: counter key for atomic monotonic token generation
# ARGV[1]: token uuid string
# ARGV[2]: ttl in milliseconds
_ACQUIRE_ALL_FENCED_SCRIPT = """
local token = ARGV[1]
local ttl_ms = tonumber(ARGV[2])
local num_lock_keys = #KEYS - 1
local counter_key = KEYS[#KEYS]

-- Step 1: Verify all keys are free
for i = 1, num_lock_keys do
    local current = redis.call("get", KEYS[i])
    if current and current ~= token then
        return {0, 0} -- Collision detected, abort all
    end
end

-- Step 2: Acquire all keys with TTL
for i = 1, num_lock_keys do
    redis.call("set", KEYS[i], token, "PX", ttl_ms)
end

-- Step 3: Increment and return monotonic fencing token
local fencing_token = redis.call("incr", counter_key)
return {1, fencing_token}
"""

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
    """Distributed lock manager using Redis with monotonic fencing tokens and in-memory fallback."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_ms: int = 10_000,
        timeout_ms: int = 5_000,
        use_redis: Optional[bool] = None,
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
        self._local_locks: Dict[str, asyncio.Lock] = {}
        self._local_owners: Dict[str, str] = {}
        self._local_counter = 0

    async def connect(self) -> None:
        """Open Redis connection."""
        if self._use_redis:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self._redis.ping()
            logger.info("SemanticLockManager connected to Redis at %s", self.redis_url)
        else:
            logger.info("SemanticLockManager using asyncio.Lock fallback (USE_REDIS=false)")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def acquire_fenced(
        self,
        lock_keys: List[str],
        timeout_ms: Optional[int] = None,
        ttl_ms: Optional[int] = None,
    ) -> Tuple[Dict[str, str], int]:
        """
        Atomically acquires all keys or none, returning (token_dict, fencing_token).
        All keys are sorted lexicographically to prevent deadlocks.
        """
        sorted_keys = sorted(lock_keys)
        if not sorted_keys:
            return {}, 0

        eff_timeout = timeout_ms if timeout_ms is not None else self.timeout_ms
        eff_ttl = ttl_ms if ttl_ms is not None else self.ttl_ms

        token = str(uuid.uuid4())
        deadline = time.monotonic() + eff_timeout / 1000.0

        if self._use_redis:
            if self._redis is None:
                raise RuntimeError("Redis lock manager is not connected; call await connect() before acquire()")

            # Apply hash tag so Redis Cluster maps all keys to the same slot
            redis_lock_keys = [f"lock:{{mpac_coord}}:{k}" for k in sorted_keys]
            counter_key = "lock:{mpac_coord}:fencing_counter"
            all_keys = redis_lock_keys + [counter_key]

            while time.monotonic() < deadline:
                try:
                    res = await self._redis.eval(
                        _ACQUIRE_ALL_FENCED_SCRIPT,
                        len(all_keys),
                        *all_keys,
                        token,
                        eff_ttl,
                    )
                    if res and res[0] == 1:
                        fencing_token = int(res[1])
                        tokens = {k: token for k in sorted_keys}
                        return tokens, fencing_token
                except Exception as e:
                    logger.warning("Redis Lua acquire error: %s", e)

                await asyncio.sleep(0.05)

            raise LockTimeoutError(f"Could not acquire lock for {sorted_keys} within {eff_timeout}ms")

        # In-Memory Fallback
        for k in sorted_keys:
            if k not in self._local_locks:
                self._local_locks[k] = asyncio.Lock()

        while time.monotonic() < deadline:
            acquired_local: List[str] = []
            all_ok = True
            try:
                for k in sorted_keys:
                    lock = self._local_locks[k]
                    try:
                        await asyncio.wait_for(lock.acquire(), timeout=0.02)
                        acquired_local.append(k)
                    except asyncio.TimeoutError:
                        all_ok = False
                        break

                if all_ok and len(acquired_local) == len(sorted_keys):
                    self._local_counter += 1
                    for k in sorted_keys:
                        self._local_owners[k] = token
                    return {k: token for k in sorted_keys}, self._local_counter
            finally:
                if not (all_ok and len(acquired_local) == len(sorted_keys)):
                    for k in acquired_local:
                        if self._local_locks[k].locked():
                            self._local_locks[k].release()

            await asyncio.sleep(0.05)

        raise LockTimeoutError(f"Could not acquire lock for {sorted_keys} within {eff_timeout}ms")

    async def acquire(
        self,
        lock_keys: List[str],
        timeout_ms: Optional[int] = None,
        ttl_ms: Optional[int] = None,
    ) -> Dict[str, str]:
        """Backward-compatible wrapper returning Dict[key -> token]."""
        tokens, _ = await self.acquire_fenced(lock_keys, timeout_ms=timeout_ms, ttl_ms=ttl_ms)
        return tokens

    async def release(self, tokens: Dict[str, str]) -> None:
        """Release locks atomically using token validation."""
        for key, token in tokens.items():
            if self._use_redis and self._redis:
                redis_key = f"lock:{{mpac_coord}}:{key}"
                try:
                    await self._redis.eval(_RELEASE_SCRIPT, 1, redis_key, token)
                except Exception as e:
                    logger.warning("Error releasing Redis lock %s: %s", key, e)
            else:
                # In-memory token owner verification
                lock = self._local_locks.get(key)
                if lock and lock.locked() and self._local_owners.get(key) == token:
                    self._local_owners.pop(key, None)
                    lock.release()

    @asynccontextmanager
    async def locked_fenced(
        self,
        lock_keys: List[str],
        timeout_ms: Optional[int] = None,
        ttl_ms: Optional[int] = None,
    ):
        """Context manager yielding (tokens, fencing_token)."""
        tokens, token_int = await self.acquire_fenced(lock_keys, timeout_ms=timeout_ms, ttl_ms=ttl_ms)
        try:
            yield tokens, token_int
        finally:
            await self.release(tokens)

    @asynccontextmanager
    async def locked(
        self,
        lock_keys: List[str],
        timeout_ms: Optional[int] = None,
        ttl_ms: Optional[int] = None,
    ):
        """Legacy context manager yielding tokens dict."""
        tokens, _ = await self.acquire_fenced(lock_keys, timeout_ms=timeout_ms, ttl_ms=ttl_ms)
        try:
            yield tokens
        finally:
            await self.release(tokens)
