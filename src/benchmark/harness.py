"""
5-Protocol Comparative Evaluation Benchmark Harness
File: src/benchmark/harness.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from benchmark.runner import BenchmarkRunner, ALL_PROTOCOLS, WORKLOAD_SIZE

logger = logging.getLogger(__name__)


def calculate_gir(unresolved_conflicts: int, total_edges: int) -> float:
    """Graph Integrity Rate (GIR): 1 - (unresolved_conflicts / total_edges)."""
    if total_edges <= 0:
        return 100.0
    val = (1.0 - (unresolved_conflicts / float(total_edges))) * 100.0
    return max(0.0, min(100.0, val))


def calculate_cra(correct_resolutions: int, total_conflicts: int) -> float:
    """Conflict Resolution Accuracy (CRA)."""
    if total_conflicts <= 0:
        return 100.0
    val = (correct_resolutions / float(total_conflicts)) * 100.0
    return max(0.0, min(100.0, val))


def calculate_ptc(valid_provenance_claims: int, total_claims: int) -> float:
    """Provenance Traceability Completeness (PTC)."""
    if total_claims <= 0:
        return 100.0
    val = (valid_provenance_claims / float(total_claims)) * 100.0
    return max(0.0, min(100.0, val))


async def run_standalone_benchmark(workload_size: int = 50, protocols: list[str] | None = None) -> list[dict[str, Any]]:
    """Runs benchmark across protocols and saves output."""
    runner = BenchmarkRunner(
        workload_size=workload_size,
        protocols=protocols or ALL_PROTOCOLS,
    )
    results = await runner.run()

    output_dir = Path("data/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "benchmark_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info("Saved %d benchmark results to %s", len(results), out_file)
    return results


if __name__ == "__main__":
    asyncio.run(run_standalone_benchmark(workload_size=20))

