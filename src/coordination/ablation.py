"""
MPAC Ablation Coordinator for Controlled Benchmark Comparisons
File: src/coordination/ablation.py
Sprint: Sprint 2 (STORY-010)
"""

from __future__ import annotations

from typing import Dict, List, Literal, Tuple

from src.coordination.mpac import MPACCoordinator
from src.schemas.models import ArbitrationDecision, GraphOperation

AblationMode = Literal["no_a2a", "no_semantic_locks", "timestamp_ordered", "fcfs_arb"]


class MPACAblationCoordinator(MPACCoordinator):
    """MPAC Coordinator with one explicitly isolated mechanism ablated."""

    def __init__(
        self,
        client=None,
        ablation_mode: AblationMode = "no_a2a",
        lock_manager=None,
        neo4j_client=None,
    ):
        actual_client = client if client is not None else neo4j_client
        if ablation_mode not in ("no_a2a", "no_semantic_locks", "timestamp_ordered", "fcfs_arb"):
            raise ValueError(f"Unsupported ablation mode: {ablation_mode!r}")
        super().__init__(actual_client, lock_manager=lock_manager)
        self.ablation_mode: AblationMode = ablation_mode

    async def _acquire_locks(self, ops: List[GraphOperation]) -> Tuple[Dict[str, str], int]:
        # Ablation B: NO_SEMANTIC_LOCKS skips lock acquisition
        if self.ablation_mode == "no_semantic_locks":
            return {}, 1
        return await super()._acquire_locks(ops)

    def _strip_peer_attestations(self, ops: List[GraphOperation]) -> List[GraphOperation]:
        """Ablation A: NO_A2A neutralizes peer verification."""
        return [op.model_copy(update={"peer_attestations": []}) for op in ops]

    async def _arbitrate(
        self, ops: List[GraphOperation], conflicts: List[Tuple[GraphOperation, GraphOperation]]
    ) -> Dict[str, ArbitrationDecision]:
        if not conflicts:
            return {}
        if self.ablation_mode != "timestamp_ordered":
            return await super()._arbitrate(ops, conflicts)

        participants = {op.operation_id for pair in conflicts for op in pair}

        def order_key(op: GraphOperation):
            stamp = str(op.properties.get("timestamp", "")) or str(op.valid_from or "")
            return (stamp, op.operation_id)

        candidates = [op for op in ops if op.operation_id in participants]
        winner = min(candidates, key=order_key)
        return {
            op.operation_id: ArbitrationDecision(
                decision="accept" if op.operation_id == winner.operation_id else "reject",
                reason="earliest-timestamp" if op.operation_id == winner.operation_id else "later-timestamp",
            )
            for op in candidates
        }

    async def submit(self, operation):
        ops = [operation] if isinstance(operation, GraphOperation) else list(operation)
        if self.ablation_mode == "no_a2a":
            ops = self._strip_peer_attestations(ops)

        if self.ablation_mode == "timestamp_ordered":
            ops = sorted(ops, key=lambda o: (str(o.properties.get("timestamp", "")) or str(o.valid_from or "")))
            self.arbitration_mode = "fcfs"
        elif self.ablation_mode == "fcfs_arb":
            self.arbitration_mode = "fcfs"
        else:
            self.arbitration_mode = "bayesian"

        return await super().submit(ops)
