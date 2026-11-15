"""
Tests for Backward-Compatible Workflow Adapter — STORY-015.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.workflow import _make_coordinator, run_agent
from src.coordination.ablation import MPACAblationCoordinator
from src.coordination.adhoc import AdHocCoordinator
from src.coordination.mpac import MPACCoordinator
from src.schemas.models import CoordinationResult


def test_make_coordinator_factory():
    client = MagicMock()
    lock = MagicMock()
    assert isinstance(_make_coordinator("adhoc", client), AdHocCoordinator)
    assert isinstance(_make_coordinator("mpac", client, lock), MPACCoordinator)
    assert isinstance(_make_coordinator("no_a2a", client, lock), MPACAblationCoordinator)
    assert isinstance(_make_coordinator("timestamp_ordered", client, lock), MPACAblationCoordinator)


@pytest.mark.asyncio
async def test_run_agent_empty_evidence():
    result = await run_agent(
        principal_id="Principal-ThreatFox",
        ioc_value="0.0.0.0",
        protocol="adhoc",
    )
    assert isinstance(result, dict)
    assert result["principal_id"] == "Principal-ThreatFox"
    assert result["claim_malware_family"] is None


@pytest.mark.asyncio
async def test_run_agent_with_evidence_and_mock_coordinator():
    fake_record = {
        "ioc_value": "139.59.33.238",
        "malware_family": "Jackskid",
        "confidence": 90,
    }
    fake_mcp_response = MagicMock(records=[fake_record])

    mock_coord = MagicMock()
    mock_coord.submit = AsyncMock(
        return_value=CoordinationResult(
            status="success",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            detail="Committed successfully",
        )
    )

    with patch("src.agents.workflow.MCP_TOOLS", {"Principal-ThreatFox": MagicMock(invoke=MagicMock(return_value=fake_mcp_response))}), \
         patch("src.agents.workflow._make_coordinator", return_value=mock_coord), \
         patch("src.agents.workflow.G2CPPeerHub.query_peers", new_callable=AsyncMock, return_value=([], 0.8)):

        state = await run_agent(
            principal_id="Principal-ThreatFox",
            ioc_value="139.59.33.238",
            protocol="mpac",
            neo4j_client=MagicMock(),
        )
        assert state["claim_malware_family"] == "Jackskid"
        assert state["result"].status == "success"
        mock_coord.submit.assert_awaited_once()
