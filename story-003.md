# STORY-003: Redis Distributed Lock Manager
## Complete Step-by-Step Execution Guide

| Field | Details |
|---|---|
| **Story ID** | STORY-003 |
| **Sprint** | Sprint 1 |
| **Points** | 8 |
| **Lead** | @member1 |
| **Blocked by** | STORY-001 gate (Docker / Redis must be running) |

---

> **WHY THIS STORY EXISTS**
>
> Without locks, two agents can read the same Neo4j node simultaneously, both see no conflict, and both write incompatible data. The second write silently overwrites the first — the Last-Write-Wins (LWW) race condition. This is exactly what Protocol 1 (Ad-Hoc) intentionally demonstrates as the worst-case baseline.
>
> The Semantic Lock Manager prevents this. Before any agent writes, it acquires a Redis lock on the entity key. Other agents trying the same entity block until the first agent releases. Keys are ALWAYS acquired in sorted order to prevent deadlocks.

---

## Pre-Flight Check

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_neo4j_client.py -v
```
Must show: `5 passed`

```bash
docker exec redis-cti redis-cli ping
```
Must show: `PONG`

---

## TASK LCK-001 — Confirm Redis in docker-compose.yml

Redis was added in STORY-001. Verify it is running:

```bash
grep "redis" docker-compose.yml
docker ps | grep redis-cti
```

Both must return output. If not, run `docker compose up -d`.

---

## TASK LCK-002/003/004/005 — Create src/coordination/lock_manager.py

### WHY

The lock manager has two backends:
- **Redis** (production): uses `SETNX key token EX ttl` — sets key only if not exists. Token is a UUID. Release uses Lua script that only deletes if token matches — no agent can steal another agent's lock.
- **asyncio.Lock** (fallback): used when `USE_REDIS=false`. Allows full test coverage without a running Redis.

Deadlock prevention: if Agent A locks `["IP:1.2.3.4", "Malware:RedLine"]` and Agent B locks `["Malware:RedLine", "IP:1.2.3.4"]`, without sorted order they deadlock. Sorting makes this impossible.

### Step LCK-002 — Create src/coordination/ directory

```bash
mkdir -p src/coordination
touch src/coordination/__init__.py
```

### Step LCK-003 — Write src/coordination/lock_manager.py

Save this file as `lock_manager.py` in `src/coordination/`:

```python
"""
Redis Distributed Lock Manager
File: src/coordination/lock_manager.py
Story: STORY-003

Provides SemanticLockManager — acquires/releases Redis locks with:
  - Sorted multi-key acquisition (deadlock prevention)
  - Atomic Lua-based release (foreign token cannot steal lock)
  - asyncio.Lock fallback when USE_REDIS=false
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

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
        redis_url:  Optional[str] = None,
        ttl_ms:     int = 10_000,
        timeout_ms: int = 5_000,
        use_redis:  Optional[bool] = None,
    ):
        from dotenv import load_dotenv
        load_dotenv()

        self.redis_url  = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ttl_ms     = ttl_ms
        self.timeout_ms = timeout_ms

        if use_redis is None:
            use_redis = os.getenv("USE_REDIS", "true").lower() != "false"
        self._use_redis = use_redis

        self._redis = None
        self._local_locks: Dict[str, asyncio.Lock] = {}

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

    async def acquire(self, lock_keys: List[str]) -> Dict[str, str]:
        """
        Acquire locks for all keys in sorted order.
        Returns Dict[key -> token]. Pass to release().
        Raises LockTimeoutError if any lock cannot be acquired.
        """
        sorted_keys = sorted(lock_keys)  # Deadlock prevention
        tokens: Dict[str, str] = {}
        deadline = time.monotonic() + self.timeout_ms / 1000.0

        for key in sorted_keys:
            token = str(uuid.uuid4())
            acquired = False

            while time.monotonic() < deadline:
                if self._use_redis and self._redis:
                    ok = await self._redis.set(
                        f"lock:{key}", token,
                        px=self.ttl_ms, nx=True
                    )
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
                await self.release(tokens)
                raise LockTimeoutError(
                    f"Could not acquire lock for '{key}' within {self.timeout_ms}ms"
                )
            tokens[key] = token

        logger.debug("Acquired %d locks: %s", len(tokens), list(tokens.keys()))
        return tokens

    async def release(self, tokens: Dict[str, str]) -> None:
        """Release locks using token verification. Silent on already-released locks."""
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
    async def locked(self, lock_keys: List[str]):
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
```

**VERIFICATION CHECK LCK-003**
```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.coordination.lock_manager import SemanticLockManager, LockTimeoutError
print('Import OK')
lm = SemanticLockManager(use_redis=False)
print('Instantiation OK')
"
```
Must show: `Import OK` then `Instantiation OK`

**IF ModuleNotFoundError: redis:**
```bash
./venv/bin/pip install redis>=5.0.0
```

---

## TASK LCK-006 — Create tests/test_lock_manager.py

Save this as `tests/test_lock_manager.py`:

```python
"""
STORY-003 Gate Tests
File: tests/test_lock_manager.py
Owner: @member1

ALL 7 tests must pass before STORY-006 begins.
Runs in USE_REDIS=false (asyncio fallback) — no Redis required for tests.
"""

import asyncio
import pytest
from src.coordination.lock_manager import SemanticLockManager, LockTimeoutError


@pytest.fixture
async def lm():
    manager = SemanticLockManager(use_redis=False)
    await manager.connect()
    yield manager
    await manager.close()


async def test_acquire_and_release(lm):
    """Basic acquire + release must succeed."""
    tokens = await lm.acquire(["entity:IP:1.2.3.4"])
    assert "entity:IP:1.2.3.4" in tokens
    await lm.release(tokens)


async def test_lock_keys_all_acquired(lm):
    """All keys passed to acquire must appear in tokens dict."""
    tokens = await lm.acquire(["zzz", "aaa", "mmm"])
    assert set(tokens.keys()) == {"zzz", "aaa", "mmm"}
    await lm.release(tokens)


async def test_context_manager(lm):
    """Context manager must acquire and release automatically."""
    async with lm.locked(["entity:Malware:RedLine"]):
        pass  # Lock held here
    # Released — acquiring again must succeed
    tokens = await lm.acquire(["entity:Malware:RedLine"])
    await lm.release(tokens)


async def test_sequential_writes_no_corruption(lm):
    """Two sequential writers on same key must succeed in order."""
    results = []

    async def writer(val):
        async with lm.locked(["shared_entity"]):
            results.append(val)

    await writer("A")
    await writer("B")
    assert results == ["A", "B"]


async def test_concurrent_writers_serialized(lm):
    """
    Concurrent writers on the same key must be serialized.
    Neither writer should see the other's value inside the critical section.
    """
    shared = []
    saw_corruption = False

    async def writer(val):
        nonlocal saw_corruption
        async with lm.locked(["shared_entity_concurrent"]):
            shared.append(val)
            await asyncio.sleep(0)
            if len(shared) > 1:
                saw_corruption = True
            shared.pop()

    await asyncio.gather(writer("A"), writer("B"))
    assert not saw_corruption, "Lock failed to serialize concurrent writers"


async def test_empty_lock_keys(lm):
    """Empty key list must return empty dict."""
    tokens = await lm.acquire([])
    assert tokens == {}
    await lm.release(tokens)


async def test_release_is_idempotent(lm):
    """Double-release must not raise an error."""
    tokens = await lm.acquire(["idempotent_key"])
    await lm.release(tokens)
    await lm.release(tokens)  # Silent — must not raise
```

**VERIFICATION CHECK LCK-006**
```bash
grep -c "^async def test_" tests/test_lock_manager.py
```
Must show: `7`

---

## GATE — Run Story-003 Tests

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_lock_manager.py -v
```

**Must show `7 passed`.**

**IF any test fails:**

| Test | Cause | Fix |
|---|---|---|
| `test_acquire_and_release` | Import error | Check `from src.coordination.lock_manager import ...` |
| `test_context_manager` | Re-acquire fails | Confirm `finally: await self.release(tokens)` in `locked()` |
| `test_concurrent_writers_serialized` | Corruption detected | asyncio.Lock not working — check `_local_locks` key logic |
| `test_release_is_idempotent` | Exception on second release | Check `if lock and lock.locked()` guard |

---

## Sprint 1 Full Gate

After STORY-003 passes, run the complete Sprint 1 gate:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```

Expected count: `5` (data_pipeline) + `5` (neo4j_client) + `13` (models) + `9` (ontology) + `7` (lock_manager) = **39 passed minimum**

## Completion Checklist

- [ ] Redis container shows `PONG` on `docker exec redis-cti redis-cli ping`
- [ ] `src/coordination/__init__.py` and `lock_manager.py` created
- [ ] `SemanticLockManager(use_redis=False)` instantiates OK
- [ ] `tests/test_lock_manager.py` has 7 async test functions
- [ ] GATE: `7 passed`
- [ ] Sprint 1 Full Gate: all tests pass

**When all 6 boxes are checked: STORY-003 is DONE. Sprint 1 is complete.**

**Next: Run Sprint 1 Full Gate → Begin Sprint 2 (STORY-004 → 005 → 006 → 007 sequentially)**
