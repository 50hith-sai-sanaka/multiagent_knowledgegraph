"""
STORY-005 Gate Tests
File: tests/test_arbiter_coordinator.py
Owner: @member2

Tests for ConflictDetector, ArbitrationEngine, and ArbiterCoordinator.

Gate requirement: ALL 6 tests must pass before Story-005 is considered done.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.coordination.arbiter import ArbiterCoordinator
from src.coordination.arbitration_engine import ArbitrationEngine
from src.coordination.conflict_detector import ConflictDetector
from src.schemas.models import CoordinationResult, GraphOperation

# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────


def make_mock_client():
    client = MagicMock()
    client.run = AsyncMock(return_value=[])
    return client


def make_op(entity: str, agent: str = "Agent-A", **kwargs):
    """Build a minimal but valid GraphOperation."""
    defaults = {
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
    defaults.update(kwargs)
    return GraphOperation(**defaults)


@pytest.fixture
def arbiter():
    return ArbiterCoordinator(make_mock_client())


# ─────────────────────────────────────────
# ConflictDetector tests
# ─────────────────────────────────────────


def test_detector_no_conflict():
    """Two ops with DIFFERENT lock keys → zero conflicts."""
    detector = ConflictDetector()
    op1 = make_op("entity_A")
    op2 = make_op("entity_B")
    conflicts = detector.detect([op1, op2])
    assert conflicts == [], f"Expected no conflicts, got {conflicts}"


def test_detector_finds_conflict():
    """Two ops with the SAME lock key → one conflict pair returned."""
    detector = ConflictDetector()
    op1 = make_op("same_entity", agent="Agent-A")
    op2 = make_op("same_entity", agent="Agent-B")
    conflicts = detector.detect([op1, op2])
    assert len(conflicts) == 1
    winner, loser = conflicts[0]
    assert winner is op1  # first submitted wins
    assert loser is op2  # second submitted loses


# ─────────────────────────────────────────
# ArbitrationEngine tests
# ─────────────────────────────────────────


def test_engine_accept_all_when_no_conflicts():
    """No conflicts → all ops get decision='accept'."""
    engine = ArbitrationEngine()
    op1 = make_op("entity_A")
    op2 = make_op("entity_B")
    decisions = engine.resolve([op1, op2], conflicts=[])
    assert decisions[op1.operation_id].decision == "accept"
    assert decisions[op2.operation_id].decision == "accept"


def test_engine_rejects_loser():
    """With one conflict pair, the loser gets decision='reject'."""
    engine = ArbitrationEngine()
    op1 = make_op("same_entity", agent="Agent-A")
    op2 = make_op("same_entity", agent="Agent-B")
    conflicts = [(op1, op2)]  # op1 is winner, op2 is loser
    decisions = engine.resolve([op1, op2], conflicts=conflicts)
    assert decisions[op1.operation_id].decision == "accept"
    assert decisions[op2.operation_id].decision == "reject"
    assert "FCFS" in decisions[op2.operation_id].reason


# ─────────────────────────────────────────
# ArbiterCoordinator integration tests
# ─────────────────────────────────────────


async def test_arbiter_all_accepted(arbiter):
    """Two non-conflicting ops → status='success', both committed."""
    op1 = make_op("entity_A")
    op2 = make_op("entity_B")
    result = await arbiter.submit([op1, op2])
    assert isinstance(result, CoordinationResult)
    assert result.status == "success"
    assert result.operations_attempted == 2
    assert result.operations_committed == 2
    assert result.conflict_detected is False


async def test_arbiter_first_wins(arbiter):
    """Two conflicting ops → status='partial', first committed, second rejected."""
    op1 = make_op("same_entity", agent="Agent-A")
    op2 = make_op("same_entity", agent="Agent-B")
    result = await arbiter.submit([op1, op2])
    assert isinstance(result, CoordinationResult)
    assert result.status == "partial"
    assert result.operations_attempted == 2
    assert result.operations_committed == 1
    assert result.conflict_detected is True
    assert result.protocol == "ARBITRATION"
