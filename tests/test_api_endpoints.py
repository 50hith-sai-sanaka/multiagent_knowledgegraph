"""Analyst API tests. Startup does not open Neo4j or Redis."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def api():
    with (
        patch("src.api.main.Neo4jClient.connect", new_callable=AsyncMock),
        patch("src.api.main.Neo4jClient.initialize_schema", new_callable=AsyncMock),
        patch("src.api.main.Neo4jClient.close", new_callable=AsyncMock),
        patch("src.api.main.SemanticLockManager.connect", new_callable=AsyncMock),
        patch("src.api.main.SemanticLockManager.close", new_callable=AsyncMock),
    ):
        with TestClient(app) as client:
            yield client


def _install_rows(rows):
    async def run(cypher, parameters=None):
        del cypher, parameters
        return rows

    app.state.neo4j_client.run = run


def test_query_returns_evidence_backed_answer(api):
    _install_rows([{
        "labels": ["IP"],
        "properties": {"value": "203.0.113.10"},
        "provenance_claims": [{
            "claim_id": "claim-1",
            "evidence": [{"source": "ThreatFox", "record_id": "1960611"}],
            "conflicts": [],
            "decisions": [],
        }],
        "neighbors": [],
    }])
    response = api.post("/api/v1/query", json={"query": "Investigate 203.0.113.10", "include_provenance": True})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Investigate 203.0.113.10"
    assert body["provenance_trail"][0]["claim_id"] == "claim-1"
    assert "203.0.113.10" in body["answer"]


def test_query_rejects_empty_text(api):
    response = api.post("/api/v1/query", json={"query": ""})
    assert response.status_code == 422


def test_graph_unknown_entity_is_404(api):
    _install_rows([])
    response = api.get("/api/v1/graph/ip/203.0.113.99")
    assert response.status_code == 404


def test_graph_rejects_unknown_type(api):
    response = api.get("/api/v1/graph/not-a-type/abc")
    assert response.status_code == 422


def test_conflicts_and_provenance(api):
    async def run(cypher, parameters=None):
        if "MATCH (x:Conflict)" in cypher:
            return [{
                "id": "cf-1",
                "status": "DETECTED",
                "node_label": "IP",
                "node_value": "203.0.113.7",
                "claims": [{"claim_id": "claim-1", "accepted": True}],
                "decisions": [[{"decision_id": "d-1", "verdict": "accept", "reason": "FCFS"}]],
            }]
        return [{
            "claim_id": parameters["id"],
            "accepted": True,
            "principals": ["Principal-ThreatFox"],
            "evidence": [{"source": "ThreatFox", "record_id": "1"}],
            "decisions": [],
        }]

    app.state.neo4j_client.run = run
    conflicts = api.get("/api/v1/conflicts", params={"status": "resolved", "limit": 10})
    assert conflicts.status_code == 200
    assert conflicts.json()["conflicts"][0]["id"] == "cf-1"
    missing = api.get("/api/v1/conflicts", params={"status": "nope"})
    assert missing.status_code == 422
    provenance = api.get("/api/v1/provenance/claim-1")
    assert provenance.status_code == 200
    assert provenance.json()["principals"] == ["Principal-ThreatFox"]


def test_provenance_missing_claim_is_404(api):
    _install_rows([])
    response = api.get("/api/v1/provenance/missing")
    assert response.status_code == 404


def test_benchmark_job_is_accepted_and_not_executed(api):
    started = api.post("/api/v1/benchmark/run", json={
        "workload_size": 10,
        "concurrency_workers": 2,
        "protocols": ["MPAC"],
    })
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    assert started.json()["status"] == "deferred"
    fetched = api.get(f"/api/v1/benchmark/results/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["gir"] is None
    assert api.get("/api/v1/benchmark/results/missing").status_code == 404
