# tests/test_adhoc_coordinator.py
"""
STORY-004 Gate Tests
File: tests/test_adhoc_coordinator.py
Owner: @member1
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.coordination.adhoc import AdHocCoordinator
from src.schemas.models import CoordinationResult, GraphOperation


def make_mock_client():
    client = MagicMock()
    client.run = AsyncMock(return_value=[])
    return client


def make_op(**kwargs):
    defaults = {
        "operation_id": str(uuid.uuid4()),
        "operation_type": "MERGE_NODE",
        "node_label": "Malware",
        "node_key": "name",
        "node_value": "__test_adhoc__",
        "claim_id": "test",
        "principal": "Agent-Test",
        "properties": {},
        "lock_keys": ["entity:malware:__test_adhoc__"],
    }
    defaults.update(kwargs)
    return GraphOperation(**defaults)


@pytest.fixture
async def lm():
    manager = AdHocCoordinator(make_mock_client())
    # AdHocCoordinator has no async connect/close; guard just in case
    if hasattr(manager, "connect"):
        await manager.connect()
    yield manager
    if hasattr(manager, "close"):
        await manager.close()


async def test_adhoc_returns_accepted(lm):
    """Ad‑Hoc coordinator must return status=ACCEPTED."""
    result = await lm.submit(make_op())
    assert isinstance(result, CoordinationResult)
    assert result.status == "ACCEPTED"
    assert getattr(result, "protocol", None) == "AD_HOC"


async def test_adhoc_latency_is_positive(lm):
    """Latency must be >= 0."""
    result = await lm.submit(make_op())
    assert result.latency_ms >= 0


async def test_adhoc_returns_coordination_result(lm):
    """Result must be a CoordinationResult with a run_id and correct agent."""
    result = await lm.submit(make_op())
    assert result.run_id
    assert result.agent_id == "Agent-Test"
