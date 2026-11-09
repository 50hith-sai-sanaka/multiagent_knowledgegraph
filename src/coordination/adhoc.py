"""
Protocol 1 — Ad‑Hoc Coordinator (Baseline / Worst Case)
File: src/coordination/adhoc.py
Story: STORY-004 (Task P1-002)

Writes DIRECTLY to Neo4j WITHOUT:
  - Distributed locking (no SemanticLockManager)
  - Conflict detection (no ConflictDetector)
  - Arbitration (no ArbitrationEngine)
  - Full provenance (minimal claim tracking only)

PURPOSE: establish the benchmark control baseline.
Concurrent writes INTENTIONALLY produce LWW corruption.
GIR < 100% is the expected and desired outcome for Protocol 1.

NEVER use this for production data — benchmark only.
"""

from __future__ import annotations

import logging
import time
import uuid

from src.coordination.base import BaseCoordinator
from src.schemas.models import CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)


class AdHocCoordinator(BaseCoordinator):
    """Uncoordinated direct writer – baseline for performance tests.

    The coordinator receives a ``GraphOperation`` and issues a single MERGE
    statement to Neo4j. No lock acquisition, no conflict detection, no
    arbitration – just fire‑and‑forget.
    """

    def __init__(self, neo4j_client):
        self._client = neo4j_client

    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        start = time.monotonic()

        # Simple MERGE – we deliberately ignore any lock keys or conflict logic.
        cypher = (
            f"MERGE (n:{operation.node_label} {{{operation.node_key}: $val}}) "
            f"SET n += $props "
            f"SET n.node_schema_version = '1.0' "
            f"SET n.last_writer = $principal "
            f"SET n.last_write_ts = timestamp()"
        )
        props = dict(operation.properties)
        props[operation.node_key] = operation.node_value

        await self._client.run(
            cypher,
            {
                "val": operation.node_value,
                "props": props,
                "principal": operation.principal,
            },
        )

        latency_ms = (time.monotonic() - start) * 1000
        return CoordinationResult(
            run_id=str(uuid.uuid4()),
            protocol="AD_HOC",
            ablation_mode="NONE",
            operation_id=operation.operation_id,
            status="ACCEPTED",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            latency_ms=latency_ms,
            agent_id=operation.principal,
        )
