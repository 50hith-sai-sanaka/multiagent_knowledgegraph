# tests/test_a2a_hub.py
"""Tests for G2CPPeerHub — STORY-009.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_hub.py -v
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.a2a import G2CPPeerHub
from src.mcp.base_tool import MCPResponse
from src.schemas.models import A2AResponse

# ---------------------------------------------------------------------------
# Helper — load a real IOC from a normalized data file
# ---------------------------------------------------------------------------

def _first_ioc_and_malware(json_path: str) -> tuple[str, str | None]:
    """Return (ioc_value, malware_family) for the first record in a JSON file."""
    with open(json_path, encoding="utf-8") as fh:
        records = json.load(fh)
    r = records[0]
    return r["ioc_value"], r.get("malware_family")

# ---------------------------------------------------------------------------
# Test 1 — Full consensus: 3 peers all CONFIRM
# Expected score: (3 - 0 + 3) / 6 = 1.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_consensus_all_confirm():
    """When all 3 peers find the IOC with matching malware family, score = 1.0."""
    hub = G2CPPeerHub()
    ioc, malware = _first_ioc_and_malware("data/normalized/threatfox.json")

    malware = malware or "KnownTestFamily"
    fake_record = {"source": "ANY", "ioc_value": ioc, "malware_family": malware, "confidence": 90}
    fake_response = MCPResponse(source="ANY", records=[fake_record])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=fake_response)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=fake_response)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=fake_response)),
    }):
        responses, score = await hub.query_peers(
            ioc_value=ioc,
            requesting_agent_id="Principal-ThreatFox",
            claim_malware_family=malware,
        )

    assert len(responses) == 3
    assert all(r.vote == "CONFIRM" for r in responses)
    assert score == pytest.approx(1.0)

# ---------------------------------------------------------------------------
# Test 2 — All abstain (peers have no data on this IOC)
# Expected score: (0 - 0 + 3) / 6 = 0.5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_peers_abstain():
    """When all 3 peers have no data, votes are all ABSTAIN and score = 0.5."""
    hub = G2CPPeerHub()
    empty_response = MCPResponse(source="ANY", records=[])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=empty_response)),
    }):
        responses, score = await hub.query_peers(
            ioc_value="unknown-ioc-xyz-999.example.com",
            requesting_agent_id="Principal-ThreatFox",
        )

    assert len(responses) == 3
    assert all(r.vote == "ABSTAIN" for r in responses)
    assert score == pytest.approx(0.5)

# ---------------------------------------------------------------------------
# Test 3 — Split vote: 1 CONFIRM, 1 CONTRADICT, 1 ABSTAIN
# Expected score: (1 - 1 + 3) / 6 = 0.5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_split_vote():
    """Mixed votes: CONFIRM + CONTRADICT + ABSTAIN → score = 0.5."""
    hub = G2CPPeerHub()
    ioc = "1.2.3.4"
    claim_malware = "Emotet"

    confirm_resp = MCPResponse(source="A", records=[{"source": "A", "ioc_value": ioc, "malware_family": "Emotet", "confidence": 80}])
    contradict_resp = MCPResponse(source="B", records=[{"source": "B", "ioc_value": ioc, "malware_family": "Ryuk", "confidence": 70}])
    empty_resp = MCPResponse(source="C", records=[])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=confirm_resp)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=contradict_resp)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=empty_resp)),
    }):
        responses, score = await hub.query_peers(
            ioc_value=ioc,
            requesting_agent_id="Principal-ThreatFox",
            claim_malware_family=claim_malware,
        )

    votes = {r.peer_id: r.vote for r in responses}
    assert votes["Principal-URLhaus"] == "CONFIRM"
    assert votes["Principal-MalwareBazaar"] == "CONTRADICT"
    assert votes["Principal-OTX"] == "ABSTAIN"
    assert score == pytest.approx(0.5)

# ---------------------------------------------------------------------------
# Test 4 — Timeout: slow peer returns ABSTAIN without hanging the test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_returns_abstain():
    """Peers that don't respond within 350 ms receive an ABSTAIN vote."""
    hub = G2CPPeerHub()

    async def _slow_coroutine(peer_id: str, ioc_value: str, claim_malware_family):
        await asyncio.sleep(10.0)  # far beyond timeout
        return A2AResponse(peer_id=peer_id, vote="CONFIRM")

    with patch.object(hub, "_single_peer_query", side_effect=_slow_coroutine):
        responses, score = await hub.query_peers(
            ioc_value="1.2.3.4",
            requesting_agent_id="Principal-ThreatFox",
        )

    assert len(responses) == 3
    assert all(r.vote == "ABSTAIN" for r in responses)
    assert score == pytest.approx(0.5)

# ---------------------------------------------------------------------------
# Test 5 — Requester is NOT included in the peer list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_requester_excluded_from_peers():
    """The requesting agent must NOT appear in the list of queried peers."""
    hub = G2CPPeerHub()
    empty_response = MCPResponse(source="ANY", records=[])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=empty_response)),
    }):
        responses, _ = await hub.query_peers(
            ioc_value="any-ioc",
            requesting_agent_id="Principal-ThreatFox",
        )

    peer_ids = [r.peer_id for r in responses]
    assert "Principal-ThreatFox" not in peer_ids
    assert len(peer_ids) == 3


@pytest.mark.asyncio
async def test_missing_peer_family_abstains_instead_of_confirming():
    """Finding the IOC without attribution does not confirm a family claim."""
    hub = G2CPPeerHub()
    response = MCPResponse(source="Peer", records=[{"ioc_value": "1.2.3.4", "malware_family": None}])
    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus": MagicMock(invoke=MagicMock(return_value=response)),
    }):
        vote = await hub._single_peer_query("Principal-URLhaus", "1.2.3.4", "Emotet")
    assert vote.vote == "ABSTAIN"
