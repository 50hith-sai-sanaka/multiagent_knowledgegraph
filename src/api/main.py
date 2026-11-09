"""Local ProGRESS runtime API.

Run with: ``uvicorn src.api.main:app --host 127.0.0.1 --port 8000``.
The service is intentionally local-only by default; do not expose it publicly
without authentication, authorization, and deployment hardening.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.agents.workflow import run_agent
from src.coordination.lock_manager import SemanticLockManager
from src.db.neo4j_client import Neo4jClient
from src.rag.retriever import GraphRAGRetriever

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


app = FastAPI(title="ProGRESS CTI Agent Runtime", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
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
        raise
    app.state.neo4j_client = client
    app.state.lock_manager = manager
    app.state.benchmark_jobs = {}


@app.on_event("shutdown")
async def shutdown() -> None:
    manager = getattr(app.state, "lock_manager", None)
    client = getattr(app.state, "neo4j_client", None)
    if manager is not None:
        await manager.close()
    if client is not None:
        await client.close()


def _response(state: dict) -> dict:
    result = state.get("result")
    return {
        "principal_id": state.get("principal_id"),
        "ioc_value": state.get("ioc_value"),
        "protocol": state.get("protocol"),
        "evidence_count": len(state.get("evidence", [])),
        "peer_votes": [vote.model_dump() for vote in state.get("peer_votes", [])],
        "consensus_score": state.get("consensus_score"),
        "llm_summary": state.get("llm_summary", ""),
        "error": state.get("error"),
        "result": result.model_dump() if result is not None else None,
    }


@app.get("/health")
async def health() -> dict:
    connected = getattr(app.state, "neo4j_client", None) is not None
    return {"status": "ready" if connected else "starting", "neo4j_connected": connected}


@app.post("/agents/process")
async def process(request: AgentRequest) -> dict:
    client = getattr(app.state, "neo4j_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Agent runtime has not connected to Neo4j")
    state = await run_agent(
        principal_id=request.principal_id,
        ioc_value=request.ioc_value,
        protocol=request.protocol,
        neo4j_client=client,
        lock_manager=app.state.lock_manager,
    )
    return _response(state)


@app.post("/agents/batch")
async def process_batch(request: BatchRequest) -> dict:
    client = getattr(app.state, "neo4j_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Agent runtime has not connected to Neo4j")
    states = await asyncio.gather(*[
        run_agent(
            principal_id=item.principal_id,
            ioc_value=item.ioc_value,
            protocol=item.protocol,
            neo4j_client=client,
            lock_manager=app.state.lock_manager,
        )
        for item in request.requests
    ])
    return {"count": len(states), "results": [_response(state) for state in states]}


@app.post("/sync")
async def sync_sources() -> dict:
    """Explicitly fetch source feeds and refresh the local normalized dataset."""
    try:
        from sync_daily import run_daily_sync
        await asyncio.to_thread(run_daily_sync)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Source synchronization failed: {type(exc).__name__}") from exc
    return {"status": "completed", "message": "Source sync finished; inspect data/analysis/sync_log.json for counts"}


def _retriever() -> GraphRAGRetriever:
    client = getattr(app.state, "neo4j_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Agent runtime has not connected to Neo4j")
    return GraphRAGRetriever(client)


def _answer_payload(answer, *, include_provenance: bool) -> dict:
    payload = answer.model_dump()
    if not include_provenance:
        payload["provenance_claims"] = []
    payload["answer"] = payload["answer_text"]
    payload["subgraph"] = payload["evidence_subgraph"]
    payload["provenance_trail"] = payload["provenance_claims"]
    return payload


@app.post("/api/v1/query")
async def query_graph(request: QueryRequest) -> dict:
    try:
        answer = await _retriever().retrieve(request.query, max_hops=request.max_hops)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = _answer_payload(answer, include_provenance=request.include_provenance)
    payload["query"] = request.query
    return payload


@app.get("/api/v1/graph/{entity_type}/{entity_value:path}")
async def entity_graph(entity_type: str, entity_value: str) -> dict:
    try:
        answer = await _retriever().neighborhood(entity_type, entity_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not answer.provenance_claims and not answer.evidence_subgraph.get("nodes"):
        raise HTTPException(status_code=404, detail=f"No {entity_type} entity matched {entity_value}")
    return _answer_payload(answer, include_provenance=True)


@app.get("/api/v1/conflicts")
async def list_conflicts(
    status: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    try:
        conflicts = await _retriever().list_conflicts(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": status, "count": len(conflicts), "conflicts": conflicts}


@app.get("/api/v1/provenance/{claim_id}")
async def claim_provenance(claim_id: str) -> dict:
    chain = await _retriever().provenance(claim_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} was not found")
    return chain


@app.post("/api/v1/benchmark/run", status_code=202)
async def start_benchmark(request: BenchmarkRequest) -> dict:
    """Accept a benchmark request without running the STORY-013 harness."""
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "deferred",
        "detail": "Comparative GIR/CR/CRA/PTC execution belongs to STORY-013 and is not run here.",
        "request": request.model_dump(),
        "gir": None,
        "cr": None,
        "cra": None,
        "ptc": None,
        "latency": None,
    }
    jobs = getattr(app.state, "benchmark_jobs", None)
    if jobs is None:
        jobs = {}
        app.state.benchmark_jobs = jobs
    jobs[job_id] = job
    return job


@app.get("/api/v1/benchmark/results/{job_id}")
async def benchmark_results(job_id: str) -> dict:
    job = getattr(app.state, "benchmark_jobs", {}).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Benchmark job {job_id} was not found")
    return job
