"""
Arbitration Engine
File: src/coordination/arbitration_engine.py
Story: STORY-005 (Task AE-001)

Applies a First-Come-First-Served (FCFS) policy to a list of conflict pairs
produced by ConflictDetector.

Policy rules:
  - The FIRST operation in each conflict pair is ALWAYS accepted.
  - Any operation that appears as the SECOND (loser) in any pair is rejected.
  - Operations not involved in any conflict are accepted by default.

NOTE: GraphOperation contains a list field (lock_keys) which makes it
unhashable, so we cannot use it directly as a dict key. We use operation_id
(a str) as the key in all internal bookkeeping.

Output: a dict mapping operation_id (str) -> ArbitrationDecision.
"""

from __future__ import annotations

from src.schemas.models import ArbitrationDecision, GraphOperation


class ArbitrationEngine:
    """Applies FCFS arbitration to a list of conflict pairs."""

    def resolve(
        self,
        all_operations: list[GraphOperation],
        conflicts: list[tuple[GraphOperation, GraphOperation]],
    ) -> dict[str, ArbitrationDecision]:
        """Produce an ArbitrationDecision for every operation.

        Args:
            all_operations: The full list of GraphOperation objects (in submission order).
            conflicts:       Conflict pairs from ConflictDetector.detect().

        Returns:
            A dict mapping operation_id (str) -> ArbitrationDecision.
        """
        # Collect operation_ids of losers (second item of each conflict pair)
        loser_ids: set = {loser.operation_id for _, loser in conflicts}

        decisions: dict[str, ArbitrationDecision] = {}
        for op in all_operations:
            if op.operation_id in loser_ids:
                decisions[op.operation_id] = ArbitrationDecision(
                    decision="reject",
                    reason=(
                        f"Conflict detected on shared lock key(s); operation {op.operation_id} rejected by FCFS policy."
                    ),
                )
            else:
                decisions[op.operation_id] = ArbitrationDecision(decision="accept", reason=None)

        return decisions
