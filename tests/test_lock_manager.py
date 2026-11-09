"""
STORY-003 Gate Tests
File: tests/test_lock_manager.py
Owner: @member1

ALL 7 tests must pass before STORY-006 begins.
Runs in USE_REDIS=false (asyncio fallback) — no Redis required for tests.
"""

import asyncio

import pytest

from src.coordination.lock_manager import SemanticLockManager


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


async def test_redis_mode_requires_connection():
    """Distributed mode must not silently downgrade to process-local locks."""
    manager = SemanticLockManager(use_redis=True)
    with pytest.raises(RuntimeError, match="not connected"):
        await manager.acquire(["key"])


async def test_partial_multi_key_acquisition_is_released():
    """A timeout on a later key releases every previously acquired key."""
    manager = SemanticLockManager(use_redis=False, timeout_ms=100)
    externally_held = asyncio.Lock()
    await externally_held.acquire()
    manager._local_locks["b"] = externally_held
    with pytest.raises(Exception, match="Could not acquire lock"):
        await manager.acquire(["a", "b"])
    assert not manager._local_locks["a"].locked()
    externally_held.release()
