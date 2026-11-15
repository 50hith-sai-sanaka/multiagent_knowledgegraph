"""
Protocol 1 — Ad-Hoc Coordinator (Baseline / Uncoordinated Direct Writer)
File: src/coordination/adhoc.py
Sprint: Sprint 2 (STORY-010)
"""

from __future__ import annotations

import logging
import time
import uuid

from src.coordination.base import BaseCoordinator
from src.schemas.models import CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)


class AdHocCoordinator(BaseCoordinator):
    """Direct, uncoordinated writer establishing the experimental control baseline."""

    def __init__(self, neo4j_client):
        self._client = neo4j_client

    async def submit(self, operation: GraphOperation | list[GraphOperation]) -> CoordinationResult:
        start = time.monotonic()

        if isinstance(operation, list):
            if not operation:
                return CoordinationResult(
                    status="empty",
                    operations_attempted=0,
                    operations_committed=0,
                    conflict_detected=False,
                    latency_ms=0.0,
                )
            target_op = operation[0]
        else:
            target_op = operation

        # Direct uncoordinated write (both node and active edge)
        if target_op.predicate and target_op.target_value:
            cypher = (
                f"MERGE (s:{target_op.node_label or 'Entity'} {{{target_op.node_key or 'value'}: $s_val}}) "
                f"MERGE (t:{target_op.target_label or 'Entity'} {{{target_op.target_key or 'name'}: $t_val}}) "
                f"MERGE (s)-[r:{target_op.predicate}]->(t) "
                f"SET r.last_writer = $principal, r.last_write_ts = timestamp()"
            )
            params = {
                "s_val": target_op.node_value,
                "t_val": target_op.target_value,
                "principal": target_op.principal,
            }
        else:
            cypher = (
                f"MERGE (n:{operation.node_label or 'Entity'} {{{operation.node_key or 'value'}: $val}}) "
                f"SET n += $props, n.last_writer = $principal, n.last_write_ts = timestamp()"
            )
            params = {
                "val": operation.node_value,
                "props": dict(operation.properties),
                "principal": operation.principal,
            }

        await self._client.run(cypher, params)

        latency_ms = (time.monotonic() - start) * 1000.0
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
