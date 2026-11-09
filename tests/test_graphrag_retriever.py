"""STORY-012 GraphRAG retrieval tests. Neo4j is mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.rag.retriever import GraphRAGRetriever


def _client(rows):
    client = AsyncMock()
    client.run = AsyncMock(return_value=rows)
    return client


def test_extracts_ip_and_malware_name():
    retriever = GraphRAGRetriever(neo4j_client=None)
    assert retriever.extract_entity("Which host is 203.0.113.10?") == ("ip", "203.0.113.10")
    assert retriever.extract_entity('What does "Cobalt Strike" use?') == ("malware", "Cobalt Strike")


@pytest.mark.asyncio
async def test_known_entity_returns_provenance_and_pattern_query():
    rows = [{
        "labels": ["Malware"],
        "properties": {"name": "Cobalt Strike"},
        "provenance_claims": [{
            "claim_id": "claim-1",
            "accepted": True,
            "evidence": [{"source": "ThreatFox", "record_id": "1960611", "evidence_id": "ev-1"}],
            "principals": ["Principal-ThreatFox"],
            "conflicts": [],
            "decisions": [],
        }],
        "neighbors": [{"type": "USES_C2", "direction": "out", "labels": ["IP"], "value": "203.0.113.10"}],
    }]
    client = _client(rows)
    answer = await GraphRAGRetriever(client).retrieve("What infrastructure is associated with Cobalt Strike?")
    cypher = client.run.await_args.args[0]
    assert "OPTIONAL MATCH" not in cypher
    assert "[(c:Claim)-[:ASSERTS]->(n)" in cypher
    assert answer.entity_type == "malware"
    assert answer.entity_value == "Cobalt Strike"
    assert answer.provenance_claims[0]["claim_id"] == "claim-1"
    assert answer.evidence_subgraph["edges"][0]["type"] == "USES_C2"
    assert answer.conflicts == []
    assert "ThreatFox" in answer.answer_text


@pytest.mark.asyncio
async def test_unknown_entity_returns_empty_neighborhood():
    client = _client([])
    answer = await GraphRAGRetriever(client).retrieve("Look up 198.51.100.4")
    assert answer.entity_value == "198.51.100.4"
    assert answer.provenance_claims == []
    assert "No IP node matched" in answer.answer_text


@pytest.mark.asyncio
async def test_conflict_entity_surfaces_conflict_records():
    rows = [{
        "labels": ["IP"],
        "properties": {"value": "203.0.113.7"},
        "provenance_claims": [{
            "claim_id": "claim-a",
            "conflicts": [{"conflict_id": "cf-1", "status": "DETECTED"}],
            "decisions": [{"verdict": "accept", "reason": "FCFS"}],
            "evidence": [],
        }],
        "neighbors": [],
    }]
    answer = await GraphRAGRetriever(_client(rows)).neighborhood("ip", "203.0.113.7")
    assert answer.conflicts[0]["conflict_id"] == "cf-1"
    assert "1 recorded conflict" in answer.answer_text
