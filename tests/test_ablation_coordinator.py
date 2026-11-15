"""Tests for MPACAblationCoordinator (STORY-010)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.coordination.ablation import MPACAblationCoordinator
from src.schemas.models import GraphOperation


def make_op(entity: str, agent: str = "Agent-A", target: str = "redline", **extra):
    base = {
        "operation_type": "create_edge",
        "operation_id": str(uuid.uuid4()),
        "lock_keys": [f"entity:ip:{entity}", f"slot:ip:{entity}:uses_c2"],
        "node_label": "IP",
        "node_key": "value",
        "node_value": entity,
        "predicate": "USES_C2",
        "target_label": "Malware",
        "target_key": "name",
        "target_value": target,
        "principal": agent,
        "confidence": 90,
        "is_functional": True,
        "valid_from": "2026-10-12T00:00:00Z",
        "properties": {},
        "claim_id": f"claim-{uuid.uuid4().hex[:6]}",
    }
    base.update(extra)
    return GraphOperation(**base)


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
    mock_lock.acquire = AsyncMock(return_value={"key": "tok"})
    mock_lock.acquire_fenced = AsyncMock(return_value=({"key": "tok"}, 42))
    mock_lock.release = AsyncMock()
    client.hydrate_existing_claims = AsyncMock(return_value=[])
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
    coord._detector.classify_pair_with_llm = AsyncMock(return_value="EXCLUSIVE_CONTRADICTION")
    op1 = make_op("same_entity", agent="A", target="redline")
    op2 = make_op("same_entity", agent="B", target="cobalt")
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
    coord._detector.classify_pair_with_llm = AsyncMock(return_value="EXCLUSIVE_CONTRADICTION")
    op1 = make_op("entity_X", operation_id="0001", valid_from="2026-10-10T00:00:00Z", target="redline")
    op2 = make_op("entity_X", operation_id="0002", valid_from="2026-10-12T00:00:00Z", target="cobalt")
    result = await coord.submit([op1, op2])
    assert result.ablation_mode == "timestamp_ordered"
    assert result.status in ("ACCEPTED", "RESOLVED")
