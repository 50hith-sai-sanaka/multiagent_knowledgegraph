"""
Arbiter Coordinator — Protocol 2 (Conflict-Aware)
File: src/coordination/arbiter.py
Story: STORY-005 (Task ARB-001)

Wraps ConflictDetector + ArbitrationEngine + Neo4j writes.

submit() accepts a LIST of GraphOperation objects (batch submission).
  1. Detect conflicts.
  2. Arbitrate (FCFS — first op wins).
  3. Execute only ACCEPTED ops against Neo4j.
  4. Return a CoordinationResult summarising the round.

Status mapping:
  "success"  -> all ops accepted
  "partial"  -> some ops rejected
  "failure"  -> no ops accepted (or an error occurred)
"""

from __future__ import annotations

import logging
import time
import uuid

from src.coordination.arbitration_engine import ArbitrationEngine
from src.coordination.base import BaseCoordinator
from src.coordination.conflict_detector import ConflictDetector
from src.schemas.models import CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)


class ArbiterCoordinator(BaseCoordinator):
    """Conflict-aware coordinator implementing FCFS arbitration.

    Usage:
        coordinator = ArbiterCoordinator(neo4j_client)
        result = await coordinator.submit([op1, op2, op3])
    """

    def __init__(self, neo4j_client):
        self._client = neo4j_client
        self._detector = ConflictDetector()
        self._engine = ArbitrationEngine()

    async def submit(
        self,
        operation: GraphOperation | list[GraphOperation],
    ) -> CoordinationResult:
        """Process one or more GraphOperation objects with conflict arbitration.

        Args:
            operation: A single GraphOperation or a list of them.

        Returns:
            CoordinationResult describing the outcome.
        """
        start = time.monotonic()

        # Normalise: always work with a list
        ops: list[GraphOperation] = [operation] if isinstance(operation, GraphOperation) else list(operation)

        # Step 1 — Detect conflicts
        conflicts = self._detector.detect(ops)

        # Step 2 — Arbitrate
        decisions = self._engine.resolve(ops, conflicts)

        # Step 3 — Execute accepted ops
        committed = 0
        for op in ops:
            decision = decisions[op.operation_id]
            if decision.decision == "accept":
                cypher = (
                    f"MERGE (n:{op.node_label} {{{op.node_key}: $val}}) "
                    f"SET n += $props "
                    f"SET n.node_schema_version = '1.0' "
                    f"SET n.last_writer = $principal "
                    f"SET n.last_write_ts = timestamp()"
                )
                props = dict(op.properties)
                props[op.node_key] = op.node_value
                await self._client.run(
                    cypher,
                    {
                        "val": op.node_value,
                        "props": props,
                        "principal": op.principal,
                    },
                )
                committed += 1
                logger.debug("Committed op %s", op.operation_id)
            else:
                logger.info(
                    "Rejected op %s — reason: %s",
                    op.operation_id,
                    decision.reason,
                )

        latency_ms = (time.monotonic() - start) * 1000

        # Step 4 — Build result
        attempted = len(ops)
        rejected = attempted - committed

        if committed == attempted:
            status = "success"
        elif committed > 0:
            status = "partial"
        else:
            status = "failure"

        detail = f"{committed}/{attempted} operations committed; {rejected} rejected by FCFS arbitration."

        return CoordinationResult(
            run_id=str(uuid.uuid4()),
            protocol="ARBITRATION",
            ablation_mode="NONE",
            operation_id=ops[0].operation_id if ops else "",
            status=status,
            detail=detail,
            operations_attempted=attempted,
            operations_committed=committed,
            conflict_detected=len(conflicts) > 0,
            latency_ms=latency_ms,
            agent_id=ops[0].principal if ops else "",
        )
