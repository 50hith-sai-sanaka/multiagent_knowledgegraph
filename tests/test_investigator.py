"""
Tests for Autonomous Cyclic LangGraph CTI Investigator — STORY-014.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_investigator.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage
import pytest

from src.agents.investigator import AutonomousCTIInvestigator
from src.schemas.models import CoordinationResult


@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.submit = AsyncMock(
        return_value=CoordinationResult(
            status="success",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            detail="All operations accepted",
        )
    )
    return coord


@pytest.fixture
def mock_a2a_hub():
    hub = MagicMock()
    hub.verify_claim_with_peers = AsyncMock(return_value=[])
    return hub


@pytest.mark.asyncio
async def test_investigator_cyclic_tool_execution_and_commit(mock_coordinator, mock_a2a_hub):
    investigator = AutonomousCTIInvestigator(
        coordinator=mock_coordinator,
        a2a_hub=mock_a2a_hub,
        max_tool_calls=2,
    )

    # First turn: planner decides to call search_cti_indicator
    ai_call_1 = AIMessage(
        content="Searching CTI indicator",
        tool_calls=[
            {
                "name": "search_cti_indicator",
                "args": {"ioc_value": "139.59.33.238"},
                "id": "call_1",
            }
        ],
    )
    # Second turn: planner decides investigation is complete
    ai_done = AIMessage(content="Investigation complete.")

    mock_chat_llm = MagicMock()
    mock_chat_llm.ainvoke = AsyncMock(side_effect=[ai_call_1, ai_done])
    mock_chat_llm.bind_tools = MagicMock(return_value=mock_chat_llm)

    from src.agents.investigator import ExtractedQuadBatch, ExtractedSemanticQuad
    fake_batch = ExtractedQuadBatch(
        quads=[
            ExtractedSemanticQuad(
                subject_label="IP",
                subject_value="139.59.33.238",
                predicate="USES_C2",
                object_label="Malware",
                object_value="Jackskid",
                confidence=90,
                evidence_id="1961358",
                raw_evidence_hash="sha256:1234",
                upstream_origin_signature="deepfield:139.59.33.238:jackskid",
            )
        ],
        reasoning_summary="Extracted C2 relationship",
    )

    with patch("src.agents.investigator.get_chat_llm", return_value=mock_chat_llm), \
         patch("src.agents.investigator.invoke_structured_llm", new_callable=AsyncMock, return_value=fake_batch):
        result = await investigator.run_investigation(
            principal="threatfox",
            ioc_value="139.59.33.238",
        )

        assert "coordination_result" in result
        assert result["coordination_result"]["status"] == "success"
        assert result["tool_call_count"] == 1
        assert len(result["mcp_evidence_log"]) == 1
        assert "139.59.33.238" in result["mcp_evidence_log"][0]
        mock_coordinator.submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_investigator_hop_budget_prevents_infinite_loop(mock_coordinator, mock_a2a_hub):
    import uuid
    investigator = AutonomousCTIInvestigator(
        coordinator=mock_coordinator,
        a2a_hub=mock_a2a_hub,
        max_tool_calls=2,
    )

    def _make_loop_call(*args, **kwargs):
        return AIMessage(
            id=str(uuid.uuid4()),
            content="Looping call",
            tool_calls=[
                {
                    "name": "search_cti_indicator",
                    "args": {"ioc_value": "1.1.1.1"},
                    "id": str(uuid.uuid4()),
                }
            ],
        )

    mock_chat_llm = MagicMock()
    mock_chat_llm.ainvoke = AsyncMock(side_effect=_make_loop_call)
    mock_chat_llm.bind_tools = MagicMock(return_value=mock_chat_llm)

    from src.agents.investigator import ExtractedQuadBatch
    empty_batch = ExtractedQuadBatch(quads=[], reasoning_summary="No quads")

    with patch("src.agents.investigator.get_chat_llm", return_value=mock_chat_llm), \
         patch("src.agents.investigator.invoke_structured_llm", new_callable=AsyncMock, return_value=empty_batch):
        result = await investigator.run_investigation(
            principal="threatfox",
            ioc_value="1.1.1.1",
        )
        # Verify execution halted cleanly at max_tool_calls limit
        assert result["tool_call_count"] == 2
