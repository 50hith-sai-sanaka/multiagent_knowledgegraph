"""
Tests for Protocol 2 MPAC Coordinator Rewrite
File: tests/test_mpac_coordinator.py
Sprint: Sprint 2 (STORY-009)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.coordination.mpac import MPACCoordinator
from src.schemas.models import GraphOperation


def make_op(entity: str, agent: str = "Agent-A", target: str = "redline", **extra):
    conf = extra.pop("conf", 90)
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
        "confidence": conf,
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

    client.hydrate_existing_claims = AsyncMock(return_value=[])

    mock_lock = AsyncMock()
    mock_lock.acquire_fenced = AsyncMock(return_value=({"key": "tok"}, 42))
    mock_lock.release = AsyncMock()

    coord = MPACCoordinator(client, lock_manager=mock_lock, arbitration_mode="bayesian")
    # Mock LLM classifier so unit tests never make live LLM or network calls
    coord._detector.classify_pair_with_llm = AsyncMock(return_value="EXCLUSIVE_CONTRADICTION")
    return coord


@pytest.mark.asyncio
async def test_mpac_clean_write(mpac):
    op = make_op("185.220.101.4")
    result = await mpac.submit(op)
    assert result.status == "ACCEPTED"
    assert result.conflict_detected is False
    assert result.fencing_token == 42
    assert result.operations_committed == 1


@pytest.mark.asyncio
async def test_mpac_conflict_arbitration(mpac):
    op1 = make_op("185.220.101.4", agent="malwarebazaar", target="redline stealer", conf=95)
    op2 = make_op("185.220.101.4", agent="otx", target="cobalt strike", conf=70)

    result = await mpac.submit([op1, op2])
    assert result.status == "RESOLVED"
    assert result.conflict_detected is True
    assert result.operations_committed == 1  # Exactly 1 winner committed to domain graph


@pytest.mark.asyncio
async def test_mpac_exception_releases_lock(mpac):
    async def explode(*_, **__):
        raise RuntimeError("simulated Neo4j failure")

    session = mpac._client.session.return_value.__aenter__.return_value
    tx = session.begin_transaction.return_value.__aenter__.return_value
    tx.run = AsyncMock(side_effect=explode)

    op = make_op("185.220.101.4")
    with pytest.raises(RuntimeError, match="simulated Neo4j failure"):
        await mpac.submit(op)

    # Guaranteed lock release
    assert mpac._lock_manager.release.call_count == 1
