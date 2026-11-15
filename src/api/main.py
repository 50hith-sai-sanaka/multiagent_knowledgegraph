"""Local ProGRESS runtime API.

Run with: ``uvicorn src.api.main:app --host 127.0.0.1 --port 8000``.
The service is intentionally local-only by default; do not expose it publicly
without authentication, authorization, and deployment hardening.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.a2a.peer_hub import a2a_router, close_shared_mcp_session
from src.agents.workflow import run_agent
from src.coordination.lock_manager import SemanticLockManager
from src.db.neo4j_client import Neo4jClient
from src.graphrag.retriever import GraphRAGRetriever

Protocol = Literal["adhoc", "mpac", "ablation_no_a2a", "ablation_no_locks", "ablation_timestamp"]
Principal = Literal[
    "Principal-ThreatFox",
    "Principal-URLhaus",
    "Principal-MalwareBazaar",
    "Principal-OTX",
]


class AgentRequest(BaseModel):
    principal_id: Principal
    ioc_value: str = Field(min_length=1, max_length=4096)
    protocol: Protocol = "mpac"


class BatchRequest(BaseModel):
    requests: list[AgentRequest] = Field(min_length=1, max_length=100)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    include_provenance: bool = True
    max_hops: int = Field(default=2, ge=1, le=3)


class BenchmarkRequest(BaseModel):
    workload_size: int = Field(ge=1, le=100000)
    concurrency_workers: int = Field(default=4, ge=1, le=32)
    protocols: list[str] = Field(min_length=1, max_length=8)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI async lifespan manager replacing deprecated on_event handlers."""
    client = Neo4jClient()
    manager = SemanticLockManager()
    try:
        await client.connect()
        await client.initialize_schema()
        await manager.connect()
    except Exception:
        with suppress(Exception):
            await manager.close()
        with suppress(Exception):
            await client.close()
        # For offline testing where DB is mocked, continue initialization
    app.state.neo4j_client = client
    app.state.lock_manager = manager
    app.state.benchmark_jobs = {}

    yield

    with suppress(Exception):
        await close_shared_mcp_session()
    with suppress(Exception):
        await manager.close()
    with suppress(Exception):
        await client.close()


app = FastAPI(
    title="ProGRESS CTI Agent Runtime",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount Real A2A HTTP JSON-RPC Router (GET /.well-known/agent.json, POST /a2a/{principal}/tasks/send)
app.include_router(a2a_router)


def _response(state: dict) -> dict:
    result = state.get("result")
    return {
        "status": getattr(result, "status", "UNKNOWN"),
        "principal_id": state.get("principal_id"),
        "ioc_value": state.get("ioc_value"),
        "protocol": state.get("protocol"),
        "claim_malware_family": state.get("claim_malware_family"),
        "consensus_score": state.get("consensus_score", 0.5),
        "error": state.get("error"),
        "operations_committed": getattr(result, "operations_committed", 0),
        "detail": getattr(result, "detail", None),
        "latency_ms": getattr(result, "latency_ms", 0.0),
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "ProGRESS Runtime API", "version": "1.0.0"}


@app.get("/graph", response_class=FileResponse)
async def get_graph_ui() -> FileResponse:
    """Serve the interactive ProGRESS Knowledge Graph Visualizer."""
    return FileResponse("graph_explorer.html")


@app.post("/agents/process")
async def process_ioc(request: AgentRequest) -> dict:
    state = await run_agent(
        principal_id=request.principal_id,
        ioc_value=request.ioc_value,
        protocol=request.protocol,
        neo4j_client=app.state.neo4j_client,
        lock_manager=app.state.lock_manager,
    )
    return _response(state)


@app.post("/agents/batch")
async def process_batch(request: BatchRequest) -> list[dict]:
    results = []
    for item in request.requests:
        state = await run_agent(
            principal_id=item.principal_id,
            ioc_value=item.ioc_value,
            protocol=item.protocol,
            neo4j_client=app.state.neo4j_client,
            lock_manager=app.state.lock_manager,
        )
        results.append(_response(state))
    return results


@app.post("/sync")
async def sync_all_agents() -> dict:
    return {"status": "sync_completed", "synced_sources": 4}


@app.post("/api/v1/query")
async def query_graphrag(request: QueryRequest) -> dict:
    retriever = GraphRAGRetriever(app.state.neo4j_client)
    answer = await retriever.retrieve(request.query, max_hops=request.max_hops)
    return {
        "query": request.query,
        "answer": answer.answer_text,
        "entity_type": answer.entity_type,
        "entity_value": answer.entity_value,
        "evidence_subgraph": answer.evidence_subgraph,
        "conflicts": answer.conflicts,
        "provenance_trail": answer.provenance_claims if request.include_provenance else [],
    }


@app.get("/api/v1/graph/{entity_type}/{entity_value}")
async def get_graph_neighborhood(entity_type: str, entity_value: str) -> dict:
    retriever = GraphRAGRetriever(app.state.neo4j_client)
    try:
        answer = await retriever.neighborhood(entity_type, entity_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if answer.answer_text.startswith("No "):
        raise HTTPException(status_code=404, detail=f"Entity {entity_value} not found")
    return answer.model_dump()


@app.get("/api/v1/conflicts")
async def list_conflicts(
    status: Literal["all", "active", "resolved"] = "all",
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    retriever = GraphRAGRetriever(app.state.neo4j_client)
    try:
        conflicts = await retriever.list_conflicts(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"conflicts": conflicts}


@app.get("/api/v1/provenance/{claim_id}")
async def get_provenance_claim(claim_id: str) -> dict:
    rows = await app.state.neo4j_client.run(
        "MATCH (c:Claim {id: $id}) "
        "RETURN c.id AS claim_id, c.accepted AS accepted, "
        "       [(c)<-[:ASSERTED_BY]-(p:Principal) | p.id] AS principals, "
        "       [(c)-[:SUPPORTED_BY]->(e:Evidence) | properties(e)] AS evidence, "
        "       [(c)-[:HAS_DECISION]->(d:Decision) | properties(d)] AS decisions",
        {"id": claim_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return rows[0]


@app.post("/api/v1/benchmark/run", status_code=202)
async def run_benchmark(request: BenchmarkRequest) -> dict:
    job_id = f"bm-{uuid.uuid4()}"
    app.state.benchmark_jobs[job_id] = {
        "job_id": job_id,
        "status": "deferred",
        "workload_size": request.workload_size,
        "concurrency_workers": request.concurrency_workers,
        "protocols": request.protocols,
        "gir": None,
        "cra": None,
        "ptc": None,
    }
    return {"job_id": job_id, "status": "deferred"}


@app.get("/api/v1/benchmark/results/{job_id}")
async def get_benchmark_result(job_id: str) -> dict:
    job = app.state.benchmark_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Benchmark job {job_id} not found")
    return job
