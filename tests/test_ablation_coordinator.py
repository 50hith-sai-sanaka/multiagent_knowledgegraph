"""Tests for MPACAblationCoordinator (Story‑007)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.coordination.ablation import MPACAblationCoordinator
from src.schemas.models import GraphOperation


# ---------------------------------------------------------------------
# Helper – same as Story‑006 tests
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


# ---------------------------------------------------------------------
# Fixture – async Neo4j client mock (re‑uses the Story‑006 fixture logic)
# ---------------------------------------------------------------------
@pytest.fixture
def mpac():
    client = MagicMock()
    async_session = AsyncMock()
    client.session.return_value = async_session
    session_obj = AsyncMock()
    async_session.__aenter__.return_value = session_obj
    async_tx = AsyncMock()

    session_obj.begin_transaction = MagicMock(return_value=async_tx)
    tx_obj = AsyncMock()
    async_tx.__aenter__.return_value = tx_obj
    tx_obj.run = AsyncMock()
    mock_lock = AsyncMock()
    mock_lock.acquire = AsyncMock()
    mock_lock.release = AsyncMock()
    return client, mock_lock


# ---------------------------------------------------------------------
# 1️⃣ NO_A2A – γ=0.0 (arbitration neutralised)
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_a2a_mode(mpac):
    client, mock_lock = mpac
    coord = MPACAblationCoordinator(client, ablation_mode="no_a2a")
    coord._lock_manager = mock_lock
    op = make_op("entity_A")
    result = await coord.submit(op)
    assert result.ablation_mode == "no_a2a"
    assert result.status == "ACCEPTED"


# ---------------------------------------------------------------------
# 2️⃣ NO_SEMANTIC_LOCKS – lock step omitted
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_semantic_locks_mode(mpac):
    client, mock_lock = mpac
    coord = MPACAblationCoordinator(client, ablation_mode="no_semantic_locks")
    coord._lock_manager = mock_lock
    op1 = make_op("same_entity", agent="A")
    op2 = make_op("same_entity", agent="B")
    result = await coord.submit([op1, op2])
    assert result.ablation_mode == "no_semantic_locks"
    assert result.conflict_detected is True
    assert result.status == "RESOLVED"


# ---------------------------------------------------------------------
# 3️⃣ TIMESTAMP_ORDERED – earliest‑timestamp‑wins
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_timestamp_ordered_mode(mpac):
    client, mock_lock = mpac
    coord = MPACAblationCoordinator(client, ablation_mode="timestamp_ordered")
    coord._lock_manager = mock_lock
    op1 = make_op("entity_X", operation_id="0001")
    op2 = make_op("entity_X", operation_id="0002")
    result = await coord.submit([op1, op2])
    assert result.ablation_mode == "timestamp_ordered"
    assert result.status in ("ACCEPTED", "RESOLVED")
