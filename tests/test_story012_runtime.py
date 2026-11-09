"""Regression tests for STORY-012 runtime and coordination guarantees."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.workflow import _make_coordinator
from src.coordination.ablation import MPACAblationCoordinator
from src.coordination.mpac import MPACCoordinator
from src.schemas.models import GraphOperation


def _op(agent: str, *, op_id: str | None = None, timestamp: str = "") -> GraphOperation:
    return GraphOperation(
        operation="MERGE",
        operation_id=op_id or str(uuid.uuid4()),
        lock_keys=["ip:203.0.113.7"],
        node_label="IP",
        node_key="value",
        node_value="203.0.113.7",
        principal=agent,
        properties={"source": agent, "record_id": f"record-{agent}", "timestamp": timestamp},
    )


def _neo4j_mock():
    client = MagicMock()
    session_cm = AsyncMock()
    session = AsyncMock()
    session_cm.__aenter__.return_value = session
    tx_cm = AsyncMock()
    session.begin_transaction = AsyncMock(return_value=tx_cm)
    tx = AsyncMock()
    tx.run = AsyncMock()
    tx_cm.__aenter__.return_value = tx
    client.session.return_value = session_cm
    return client, tx


@pytest.mark.asyncio
async def test_mpac_uses_lock_manager_contract_and_does_not_write_rejected_entity():
    client, tx = _neo4j_mock()
    locks = AsyncMock()
    locks.acquire.return_value = {"ip:203.0.113.7": "token"}
    coordinator = MPACCoordinator(client, lock_manager=locks)

    result = await coordinator.submit([_op("source-a"), _op("source-b")])

    locks.acquire.assert_awaited_once_with(["ip:203.0.113.7"])
    locks.release.assert_awaited_once_with({"ip:203.0.113.7": "token"})
    entity_merges = [c for c in tx.run.await_args_list if c.args[0].startswith("MERGE (n:IP")]
    assert len(entity_merges) == 1
    assert result.operations_attempted == 2
    assert result.operations_committed == 1
    assert result.conflict_detected is True
    assert "1/2" in result.detail
    assert any("GROUNDED_IN" in c.args[0] for c in tx.run.await_args_list)
    assert any("HAS_DECISION" in c.args[0] for c in tx.run.await_args_list)
    assert any("INVOLVED_IN" in c.args[0] for c in tx.run.await_args_list)


@pytest.mark.asyncio
async def test_mpac_releases_locks_when_transaction_fails():
    client, tx = _neo4j_mock()
    tx.run.side_effect = RuntimeError("write failed")
    locks = AsyncMock()
    locks.acquire.return_value = {"ip:203.0.113.7": "token"}
    coordinator = MPACCoordinator(client, lock_manager=locks)
    with pytest.raises(RuntimeError, match="write failed"):
        await coordinator.submit(_op("source-a"))
    locks.release.assert_awaited_once_with({"ip:203.0.113.7": "token"})


@pytest.mark.asyncio
async def test_mpac_rejects_unsafe_graph_identifier_before_transaction():
    client, tx = _neo4j_mock()
    locks = AsyncMock()
    locks.acquire.return_value = {"key": "token"}
    coordinator = MPACCoordinator(client, lock_manager=locks)
    operation = _op("source-a").model_copy(update={"node_label": "IP) DETACH DELETE"})
    with pytest.raises(ValueError, match="Unapproved graph label"):
        await coordinator.submit(operation)
    tx.run.assert_not_awaited()
    locks.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_ablation_disables_semantic_lock_acquisition():
    client, _ = _neo4j_mock()
    locks = AsyncMock()
    coordinator = MPACAblationCoordinator(client, "no_semantic_locks", lock_manager=locks)
    await coordinator.submit(_op("source-a"))
    locks.acquire.assert_not_awaited()
    locks.release.assert_awaited_once_with({})


@pytest.mark.asyncio
async def test_timestamp_ablation_uses_evidence_timestamp_not_operation_id():
    client, _ = _neo4j_mock()
    coordinator = MPACAblationCoordinator(client, "timestamp_ordered", lock_manager=AsyncMock())
    first_by_time = _op("source-a", op_id="z-later-id", timestamp="2026-01-01T00:00:00Z")
    second_by_time = _op("source-b", op_id="a-earlier-id", timestamp="2025-01-01T00:00:00Z")
    conflicts = coordinator._detector.detect([first_by_time, second_by_time])
    decisions = await coordinator._arbitrate([first_by_time, second_by_time], conflicts)
    assert decisions[first_by_time.operation_id].decision == "reject"
    assert decisions[second_by_time.operation_id].decision == "accept"


@pytest.mark.asyncio
async def test_pending_tier2_label_is_audited_without_a_domain_write():
    client, tx = _neo4j_mock()
    client.validate_and_register_type = AsyncMock(return_value={
        "decision": "PENDING",
        "target_type": "CryptoWallet",
        "reason": "waiting for a second confirmation",
    })
    locks = AsyncMock()
    locks.acquire.return_value = {"wallet:abc": "token"}
    operation = _op("source-a").model_copy(update={
        "node_label": "CryptoWallet",
        "node_key": "address",
        "node_value": "abc",
        "lock_keys": ["wallet:abc"],
    })
    result = await MPACCoordinator(client, lock_manager=locks).submit(operation)
    assert result.operations_committed == 0
    assert not any(call.args[0].startswith("MERGE (n:") for call in tx.run.await_args_list)
    assert any("HAS_DECISION" in call.args[0] for call in tx.run.await_args_list)


@pytest.mark.asyncio
async def test_approved_tier2_label_writes_schema_version_two():
    client, tx = _neo4j_mock()
    client.validate_and_register_type = AsyncMock(return_value={
        "decision": "APPROVE",
        "target_type": "CryptoWallet",
        "reason": "approved by two agents",
    })
    locks = AsyncMock()
    locks.acquire.return_value = {"wallet:abc": "token"}
    operation = _op("source-a").model_copy(update={
        "node_label": "CryptoWallet",
        "node_key": "address",
        "node_value": "abc",
        "lock_keys": ["wallet:abc"],
    })
    result = await MPACCoordinator(client, lock_manager=locks).submit(operation)
    merges = [call for call in tx.run.await_args_list if call.args[0].startswith("MERGE (n:CryptoWallet")]
    assert result.operations_committed == 1
    assert merges[0].args[1]["props"]["node_schema_version"] == "2.0"


def test_workflow_selects_each_supported_protocol_and_rejects_unknown():
    client = MagicMock()
    assert type(_make_coordinator("adhoc", client)).__name__ == "AdHocCoordinator"
    assert type(_make_coordinator("mpac", client)).__name__ == "MPACCoordinator"
    assert type(_make_coordinator("ablation_no_locks", client)).__name__ == "MPACAblationCoordinator"
    with pytest.raises(ValueError, match="Unsupported coordination protocol"):
        _make_coordinator("surprise", client)
