# tests/test_llm_enrich.py
"""Unit tests for the LLM enrichment node — Story 011.

Tests cover:
  1. Full enrichment: LLM response is parsed and merged into the GraphOperation.
  2. Label correction: LLM suggests a new_label → GraphOperation + state updated.
  3. Graceful fallback: LLM_API_KEY missing → node returns empty enrichment.
  4. LLM HTTP error: pipeline continues with empty enrichment.
  5. Full workflow: enrich_with_llm integrates inside the 6-node LangGraph graph.
  6. LLMEnrichmentTool raises RuntimeError when API key is missing.
  7. LLMEnrichmentTool raises ValueError for unknown provider.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_llm_enrich.py -v
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.state import AgentState
from src.agents.workflow import (
    build_agent_graph,
    enrich_with_llm,
    extract_claim,
    fetch_evidence,
    run_agent,
)
from src.mcp.base_tool import MCPResponse
from src.schemas.models import CoordinationResult, GraphOperation

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

FAKE_IOC = "https://malware.example.com/payload"
FAKE_PRINCIPAL = "Principal-ThreatFox"
FAKE_MALWARE = "Emotet"

FAKE_RECORD = {
    "ioc_value": FAKE_IOC,
    "ioc_type": "url",
    "malware_family": FAKE_MALWARE,
    "confidence": 90,
    "threat_type": "payload_delivery",
    "source": "ThreatFox",
}

FAKE_CLAIM = GraphOperation(
    operation_type="MERGE",
    lock_keys=[FAKE_IOC],
    node_label="URL",
    node_key="ioc_value",
    node_value=FAKE_IOC,
    properties={
        "malware_family": FAKE_MALWARE,
        "confidence": 90,
        "source": "ThreatFox",
    },
    principal=FAKE_PRINCIPAL,
)

LLM_GOOD_RESPONSE = json.dumps({
    "summary": "Emotet uses this URL to distribute its payload. High confidence based on multiple source confirmations.",
    "extra_props": {"tactics": ["delivery"], "severity": "high"},
    "new_label": None,
})

LLM_LABEL_CORRECTION_RESPONSE = json.dumps({
    "summary": "This IOC is a URL used in phishing campaigns.",
    "extra_props": {"severity": "medium"},
    "new_label": "Domain",
})


def _make_base_state(**overrides) -> AgentState:
    """Return a minimal AgentState ready to enter enrich_with_llm."""
    state: AgentState = {
        "principal_id": FAKE_PRINCIPAL,
        "ioc_value": FAKE_IOC,
        "protocol": "mpac",
        "neo4j_client": None,
        "evidence": [FAKE_RECORD],
        "claim_malware_family": FAKE_MALWARE,
        "node_label": "URL",
        "claim": FAKE_CLAIM,
        "peer_votes": [],
        "consensus_score": 0.5,
        "result": None,
        "error": None,
        "llm_summary": None,
        "llm_extra_props": None,
    }
    state.update(overrides)
    return state


def _make_neo4j_client() -> MagicMock:
    """Return a minimal mock Neo4j client compatible with AdHocCoordinator."""
    client = MagicMock()
    client.run = AsyncMock(return_value=None)
    # For MPACCoordinator
    tx = AsyncMock()
    tx.run = AsyncMock(return_value=None)
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    session = AsyncMock()
    session.begin_transaction = MagicMock(return_value=tx)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock(return_value=session)
    return client


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — Full enrichment (good LLM response)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_merges_extra_props():
    """LLM extra_props are merged into the GraphOperation.properties."""
    state = _make_base_state()

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key", "LLM_PROVIDER": "gemini"}):
        with patch("src.agents.workflow.LLMEnrichmentTool") as MockTool:
            mock_instance = AsyncMock()
            mock_instance.enrich = AsyncMock(return_value={
                "summary": "Emotet URL.", "extra_props": {"tactics": ["delivery"], "severity": "high"}, "new_label": None
            })
            MockTool.return_value = mock_instance

            result = await enrich_with_llm(state)

    assert result["llm_summary"] == "Emotet URL."
    assert result["llm_extra_props"] == {"tactics": ["delivery"], "severity": "high"}
    # Updated claim must have the merged properties
    updated_claim: GraphOperation = result["claim"]
    assert updated_claim.properties["severity"] == "high"
    assert updated_claim.properties["tactics"] == ["delivery"]
    # Original properties must still be there
    assert updated_claim.properties["malware_family"] == FAKE_MALWARE


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — Label correction
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_label_suggestion_does_not_bypass_ontology():
    """LLM label suggestions cannot directly change the evidence-derived graph label."""
    state = _make_base_state()

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key", "LLM_PROVIDER": "gemini"}):
        with patch("src.agents.workflow.LLMEnrichmentTool") as MockTool:
            mock_instance = AsyncMock()
            mock_instance.enrich = AsyncMock(return_value={
                "summary": "Phishing campaign.",
                "extra_props": {"severity": "medium"},
                "new_label": "Domain",
            })
            MockTool.return_value = mock_instance

            result = await enrich_with_llm(state)

    assert result.get("node_label") is None
    updated_claim: GraphOperation = result["claim"]
    assert updated_claim.node_label == "URL"
    assert updated_claim.properties["severity"] == "medium"


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — Graceful fallback when LLM_API_KEY is missing
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_missing_api_key():
    """When LLM_API_KEY is not set, enrich_with_llm returns empty enrichment."""
    state = _make_base_state()

    # Remove LLM_API_KEY from environment
    env_without_key = {k: v for k, v in os.environ.items() if k != "LLM_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        result = await enrich_with_llm(state)

    assert result.get("llm_summary") == ""
    assert result.get("llm_extra_props") == {}
    # claim should NOT be in the result (no update needed)
    assert "claim" not in result


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — LLM HTTP error → graceful fallback
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_http_error_returns_empty():
    """When the LLM API returns an error, enrichment falls back to empty dict."""
    state = _make_base_state()

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key", "LLM_PROVIDER": "gemini"}):
        with patch("src.agents.workflow.LLMEnrichmentTool") as MockTool:
            mock_instance = AsyncMock()
            # LLMEnrichmentTool.enrich already handles exceptions internally
            # and returns safe defaults
            mock_instance.enrich = AsyncMock(return_value={
                "summary": "", "extra_props": {}, "new_label": None
            })
            MockTool.return_value = mock_instance

            result = await enrich_with_llm(state)

    assert result.get("llm_summary") == ""
    assert result.get("llm_extra_props") == {}


# ──────────────────────────────────────────────────────────────────────────────
# Test 5 — Enrich node is skipped when claim is None
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_skipped_when_no_claim():
    """If claim is None (no evidence), enrich_with_llm returns empty dict."""
    state = _make_base_state(claim=None, evidence=[])

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key"}):
        result = await enrich_with_llm(state)

    # No updates expected — claim is None, LLM should not be called
    assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# Test 6 — Enrich node is skipped when a prior error exists
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_skipped_on_prior_error():
    """If state contains an error from a previous node, enrichment is skipped."""
    state = _make_base_state(error="fetch_evidence failed: file not found")

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key"}):
        result = await enrich_with_llm(state)

    assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# Test 7 — Full workflow integration with mocked LLM
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_workflow_with_llm_enrichment():
    """End-to-end: run_agent calls enrich_with_llm and final result has LLM fields."""
    import json as _json
    from src.agents.a2a import G2CPPeerHub
    from src.mcp.base_tool import MCPResponse
    from src.schemas.models import A2AResponse

    neo4j_client = _make_neo4j_client()
    fake_response = MCPResponse(source="ThreatFox", records=[FAKE_RECORD])
    peer_response = A2AResponse(peer_id="Principal-URLhaus", vote="CONFIRM")

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key", "LLM_PROVIDER": "gemini"}):
        with patch("src.agents.workflow.MCP_TOOLS", {FAKE_PRINCIPAL: MagicMock(invoke=MagicMock(return_value=fake_response))}):
            with patch("src.agents.a2a.MCP_TOOLS", {
                "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=MCPResponse(source="A", records=[]))),
                "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=MCPResponse(source="B", records=[]))),
                "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=MCPResponse(source="C", records=[]))),
            }):
                with patch("src.agents.workflow.LLMEnrichmentTool") as MockTool:
                    mock_instance = AsyncMock()
                    mock_instance.enrich = AsyncMock(return_value={
                        "summary": "Emotet distributes via this URL.",
                        "extra_props": {"severity": "high"},
                        "new_label": None,
                    })
                    MockTool.return_value = mock_instance

                    final_state = await run_agent(
                        principal_id=FAKE_PRINCIPAL,
                        ioc_value=FAKE_IOC,
                        protocol="adhoc",
                        neo4j_client=neo4j_client,
                    )

    assert final_state.get("llm_summary") == "Emotet distributes via this URL."
    assert final_state.get("llm_extra_props") == {"severity": "high"}
    assert final_state.get("result") is not None
    result: CoordinationResult = final_state["result"]
    assert result.status in ("ACCEPTED", "RESOLVED", "success")


# ──────────────────────────────────────────────────────────────────────────────
# Test 8 — LLMEnrichmentTool raises when key is missing
# ──────────────────────────────────────────────────────────────────────────────

def test_llm_tool_raises_without_api_key():
    """LLMEnrichmentTool must raise RuntimeError when LLM_API_KEY is absent."""
    from src.llm.llm_tool import LLMEnrichmentTool

    env_without_key = {k: v for k, v in os.environ.items() if k != "LLM_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            LLMEnrichmentTool()


# ──────────────────────────────────────────────────────────────────────────────
# Test 9 — LLMEnrichmentTool raises for unknown provider
# ──────────────────────────────────────────────────────────────────────────────

def test_llm_tool_raises_for_unknown_provider():
    """LLMEnrichmentTool raises ValueError for an unrecognised provider name."""
    from src.llm.llm_tool import LLMEnrichmentTool

    with patch.dict(os.environ, {"LLM_API_KEY": "test-key", "LLM_PROVIDER": "unknown_llm"}):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMEnrichmentTool()
