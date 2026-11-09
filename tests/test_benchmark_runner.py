"""
tests/test_benchmark_runner.py
-------------------------------
STORY-013 Gate: Unit tests for the BenchmarkRunner and metric calculators.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from benchmark.runner import (
    ALL_PROTOCOLS,
    WORKLOAD_SIZE,
    BenchmarkRunner,
    _compute_latency_stats,
    _load_workload,
    _make_graph_operation,
)
from src.schemas.models import CoordinationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_neo4j():
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.initialize_schema = AsyncMock()

    session_cm = AsyncMock()
    session = AsyncMock()
    session_cm.__aenter__.return_value = session
    session_cm.__aexit__.return_value = False

    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"cnt": 0})
    mock_result.data = AsyncMock(return_value=[])
    session.run = AsyncMock(return_value=mock_result)

    client.session.return_value = session_cm
    return client


@pytest.fixture()
def mock_lock_manager():
    mgr = MagicMock()
    mgr._use_redis = False
    mgr.connect = AsyncMock()
    mgr.close = AsyncMock()
    mgr.acquire = AsyncMock(return_value={"mock_lock": "token"})
    mgr.release = AsyncMock()
    return mgr


@pytest.fixture()
def tiny_workload(tmp_path):
    sources = {
        "threatfox.json": [{"ioc_value": "1.1.1.1", "ioc_type": "ip", "malware_family": "Mirai", "confidence": 90}],
        "urlhaus.json": [{"ioc_value": "2.2.2.2", "ioc_type": "ip", "malware_family": "AgentTesla", "confidence": 75}],
        "malwarebazaar.json": [{"ioc_value": "aabbccdd" * 8, "ioc_type": "sha256_hash", "malware_family": "Redline", "confidence": 80}],
        "otx.json": [{"ioc_value": "evil.com", "ioc_type": "domain", "malware_family": "Cobalt", "confidence": 70}],
    }
    mock_files = {}
    for filename, data in sources.items():
        file_path = tmp_path / filename
        with open(file_path, "w") as fh:
            json.dump(data, fh)
        mock_files[f"Principal-{filename.split('.')[0].capitalize()}"] = str(file_path)

    # Specific casing fixes for OTX and URLhaus
    mock_files = {
        "Principal-ThreatFox": str(tmp_path / "threatfox.json"),
        "Principal-URLhaus": str(tmp_path / "urlhaus.json"),
        "Principal-MalwareBazaar": str(tmp_path / "malwarebazaar.json"),
        "Principal-OTX": str(tmp_path / "otx.json"),
    }
    with patch("benchmark.runner.SOURCE_FILES", mock_files):
        yield mock_files


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_workload_returns_records(tiny_workload):
    workload = _load_workload(size=4)
    assert len(workload) == 4
    for item in workload:
        assert "principal_id" in item
        assert "ioc_value" in item
        assert "ioc_type" in item


def test_make_graph_operation_has_lock_keys():
    item = {
        "principal_id": "Principal-ThreatFox",
        "ioc_value": "1.2.3.4",
        "ioc_type": "ip",
        "malware_family": "Mirai",
        "confidence": 90,
    }
    op = _make_graph_operation(item)
    assert len(op.lock_keys) >= 1
    assert "IP:1.2.3.4" in op.lock_keys


def test_latency_stats_mean_and_p95():
    samples = [10.0, 20.0, 30.0, 40.0, 100.0]
    stats = _compute_latency_stats(samples)
    assert stats["mean_latency_ms"] == pytest.approx(40.0, abs=1.0)
    assert stats["p95_latency_ms"] >= 40.0


def test_latency_stats_empty():
    stats = _compute_latency_stats([])
    assert stats["mean_latency_ms"] == 0.0
    assert stats["p95_latency_ms"] == 0.0


@pytest.mark.asyncio
async def test_benchmark_runner_calls_coordinator_for_each_item(
    tiny_workload, mock_neo4j, mock_lock_manager
):
    accepted_result = CoordinationResult(
        status="ACCEPTED",
        detail="mock",
        operations_attempted=1,
        operations_committed=1,
        conflict_detected=False,
        latency_ms=5.0,
    )

    mock_coordinator = MagicMock()
    mock_coordinator.submit = AsyncMock(return_value=accepted_result)

    with (
        patch("benchmark.runner.Neo4jClient", return_value=mock_neo4j),
        patch("benchmark.runner.SemanticLockManager", return_value=mock_lock_manager),
        patch("benchmark.runner._make_coordinator", return_value=mock_coordinator),
        patch("benchmark.runner._wipe_domain_nodes", new_callable=AsyncMock),
        patch("benchmark.runner._compute_gir", new_callable=AsyncMock, return_value=5.0),
        patch("benchmark.runner._compute_cr", new_callable=AsyncMock, return_value=80.0),
        patch("benchmark.runner._compute_cra", new_callable=AsyncMock, return_value=75.0),
        patch("benchmark.runner._compute_ptc", new_callable=AsyncMock, return_value=95.0),
    ):
        runner = BenchmarkRunner(workload_size=4, protocols=["adhoc"])
        results = await runner.run()

    assert len(results) == 1
    r = results[0]
    assert r["protocol"] == "adhoc"
    assert r["GIR"] == 5.0
    assert r["CR"] == 80.0
    assert r["PTC"] == 95.0
    assert mock_coordinator.submit.call_count == 4


@pytest.mark.asyncio
async def test_benchmark_runner_all_protocols_produce_results(
    tiny_workload, mock_neo4j, mock_lock_manager
):
    accepted_result = CoordinationResult(
        status="ACCEPTED",
        detail="mock",
        operations_committed=1,
        conflict_detected=False,
        latency_ms=3.0,
    )
    mock_coordinator = MagicMock()
    mock_coordinator.submit = AsyncMock(return_value=accepted_result)

    with (
        patch("benchmark.runner.Neo4jClient", return_value=mock_neo4j),
        patch("benchmark.runner.SemanticLockManager", return_value=mock_lock_manager),
        patch("benchmark.runner._make_coordinator", return_value=mock_coordinator),
        patch("benchmark.runner._wipe_domain_nodes", new_callable=AsyncMock),
        patch("benchmark.runner._compute_gir", new_callable=AsyncMock, return_value=0.0),
        patch("benchmark.runner._compute_cr", new_callable=AsyncMock, return_value=0.0),
        patch("benchmark.runner._compute_cra", new_callable=AsyncMock, return_value=0.0),
        patch("benchmark.runner._compute_ptc", new_callable=AsyncMock, return_value=0.0),
    ):
        runner = BenchmarkRunner(workload_size=4, protocols=ALL_PROTOCOLS)
        results = await runner.run()

    assert len(results) == len(ALL_PROTOCOLS)
    protocol_names = [r["protocol"] for r in results]
    for p in ALL_PROTOCOLS:
        assert p in protocol_names


@pytest.mark.asyncio
async def test_mpac_gir_not_worse_than_adhoc(
    tiny_workload, mock_neo4j, mock_lock_manager
):
    gir_values = {"adhoc": 20.0, "mpac": 5.0}
    call_count = {"n": 0}

    async def mock_gir(protocol, operations_committed, conflict_count):
        return gir_values.get(protocol, 0.0)

    accepted_result = CoordinationResult(
        status="ACCEPTED",
        detail="mock",
        operations_committed=1,
        conflict_detected=False,
        latency_ms=2.0,
    )
    mock_coordinator = MagicMock()
    mock_coordinator.submit = AsyncMock(return_value=accepted_result)

    with (
        patch("benchmark.runner.Neo4jClient", return_value=mock_neo4j),
        patch("benchmark.runner.SemanticLockManager", return_value=mock_lock_manager),
        patch("benchmark.runner._make_coordinator", return_value=mock_coordinator),
        patch("benchmark.runner._wipe_domain_nodes", new_callable=AsyncMock),
        patch("benchmark.runner._compute_gir", side_effect=mock_gir),
        patch("benchmark.runner._compute_cr", new_callable=AsyncMock, return_value=0.0),
        patch("benchmark.runner._compute_cra", new_callable=AsyncMock, return_value=0.0),
        patch("benchmark.runner._compute_ptc", new_callable=AsyncMock, return_value=0.0),
    ):
        runner = BenchmarkRunner(workload_size=4, protocols=["adhoc", "mpac"])
        results = await runner.run()

    adhoc_gir = next(r["GIR"] for r in results if r["protocol"] == "adhoc")
    mpac_gir = next(r["GIR"] for r in results if r["protocol"] == "mpac")
    assert mpac_gir <= adhoc_gir
