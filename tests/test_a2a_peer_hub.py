"""
Tests for Standards-Compliant A2A HTTP JSON-RPC Router & LLM Peer Verifier — STORY-013.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_peer_hub.py -v
"""

from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
import pytest

from src.a2a.peer_hub import (
    A2APeerHub,
    LLMPeerVerificationJudgment,
    a2a_router,
    close_shared_mcp_session,
)


@pytest.fixture
def app():
    api = FastAPI()
    api.include_router(a2a_router)
    return api


@pytest.fixture(autouse=True)
async def cleanup_mcp():
    yield
    await close_shared_mcp_session()


@pytest.mark.asyncio
async def test_a2a_discovery_agent_cards(app):
    hub = A2APeerHub(app=app, base_url="http://test")
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol_version"] == "A2A-G2CP-1.0"
        assert len(data["agents"]) == 4
        principals = [a["principal"] for a in data["agents"]]
        assert "threatfox" in principals
        assert "otx" in principals


@pytest.mark.asyncio
async def test_a2a_hop_budget_enforcement(app):
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "test-recursive",
            "method": "tasks/send",
            "params": {"hop_budget": 1, "subject_value": "1.1.1.1"},
        }
        resp = await client.post("/a2a/threatfox/tasks/send", json=payload)
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
        assert "hop_budget" in data["error"]["message"]


@pytest.mark.asyncio
async def test_a2a_peer_verification_abstain_on_unknown(app):
    hub = A2APeerHub(app=app, base_url="http://test")
    attestations = await hub.verify_claim_with_peers(
        requesting_principal="threatfox",
        ioc_value="0.0.0.0",
        predicate="USES_C2",
        claimed_target="Cobalt Strike",
    )
    assert len(attestations) == 3
    for att in attestations:
        assert att.stance == "ABSTAIN"
        assert att.responder_principal != "threatfox"


@pytest.mark.asyncio
async def test_a2a_peer_verification_confirm_and_contradict(app):
    hub = A2APeerHub(app=app, base_url="http://test")

    # Mock the LLM judge in peer_hub for deterministic execution
    with patch(
        "src.a2a.peer_hub._evaluate_peer_evidence_with_llm",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.return_value = LLMPeerVerificationJudgment(
            stance="CONTRADICT",
            confidence=90,
            counter_object="RedLine Stealer",
            reasoning="Telemetry shows active RedLine Stealer C2.",
        )

        attestations = await hub.verify_claim_with_peers(
            requesting_principal="otx",
            ioc_value="139.59.33.238",
            predicate="USES_C2",
            claimed_target="Cobalt Strike",
        )
        assert len(attestations) == 3
        tf_att = next(a for a in attestations if a.responder_principal == "threatfox")
        assert tf_att.stance == "CONTRADICT"
        assert tf_att.counter_object == "redline stealer"
        assert len(tf_att.signature) == 64

