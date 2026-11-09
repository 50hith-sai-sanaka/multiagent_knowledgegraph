"""
STORY‑006 – MPAC Coordinator tests
File: tests/test_mpac_coordinator.py
Owner: @member1
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.coordination.mpac import MPACCoordinator
from src.schemas.models import GraphOperation


# ---------------------------------------------------------------------
# Helper – creates a minimal, valid GraphOperation (identical to other tests)
# ---------------------------------------------------------------------
def make_op(entity: str, agent: str = "Agent-A", **extra):
    base = {
        "operation_type": "MERGE_NODE",
        "operation_id": str(uuid.uuid4()),
        "lock_keys": [f"entity:malware:{entity}"],
        "node_label": "Malware",
        "node_key": "name",
        "node_value": entity,
        "principal": agent,
        "properties": {},
        "claim_id": "test",
    }
    base.update(extra)
    return GraphOperation(**base)


@pytest.fixture
def mpac():
    # Proper async mocks for Neo4j client session and transaction
    client = MagicMock()
    # async session context manager
    async_session = AsyncMock()
    client.session.return_value = async_session
    # async_session.__aenter__ returns a mock session object
    session_obj = AsyncMock()
    async_session.__aenter__.return_value = session_obj
    # async transaction context manager
    async_tx = AsyncMock()
    # Use a regular Mock for begin_transaction to avoid it being awaited as coroutine
    session_obj.begin_transaction = MagicMock(return_value=async_tx)
    # async_tx.__aenter__ returns a mock tx object with async run
    tx_obj = AsyncMock()
    async_tx.__aenter__.return_value = tx_obj
    tx_obj.run = AsyncMock()
    # Mock lock manager to avoid real Redis calls
    mock_lock = AsyncMock()
    mock_lock.acquire = AsyncMock()
    mock_lock.release = AsyncMock()
    mpac = MPACCoordinator(client)
    mpac._lock_manager = mock_lock
    return mpac


# ---------------------------------------------------------------------
# 1️⃣ Clean write – no conflict
# ---------------------------------------------------------------------
async def test_mpac_clean_write(mpac):
    op = make_op("entity_A")
    result = await mpac.submit(op)
    assert result.status == "ACCEPTED"
    assert result.conflict_detected is False


# ---------------------------------------------------------------------
# 2️⃣ Conflict write – two ops share a lock key
# ---------------------------------------------------------------------
async def test_mpac_conflict_write(mpac):
    op1 = make_op("same_entity", agent="A")
    op2 = make_op("same_entity", agent="B")
    result = await mpac.submit([op1, op2])
    assert result.status == "RESOLVED"
    assert result.conflict_detected is True


# ---------------------------------------------------------------------
# 3️⃣ Exception recovery – force Neo4j error inside the transaction
# ---------------------------------------------------------------------
async def test_mpac_exception_releases_lock(mpac, monkeypatch):
    # Make tx.run raise an exception the first time it is called
    async def explode(*_, **__):
        raise RuntimeError("simulated Neo4j failure")

    tx = (
        mpac._client.session.return_value.__aenter__.return_value.begin_transaction.return_value.__aenter__.return_value
    )
    tx.run = AsyncMock(side_effect=explode)

    # Replace the real lock manager with a mock to verify release call
    mock_lock = AsyncMock()
    mpac._lock_manager = mock_lock

    op = make_op("entity_X")
    with pytest.raises(RuntimeError, match="simulated Neo4j failure"):
        await mpac.submit(op)
    # Ensure release was awaited even after the exception
    mock_lock.release.assert_awaited()
