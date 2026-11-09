"""Behavioral MPAC ablations for controlled protocol comparisons."""
from __future__ import annotations

from typing import Literal

from src.coordination.mpac import MPACCoordinator
from src.schemas.models import ArbitrationDecision, GraphOperation

AblationMode = Literal["no_a2a", "no_semantic_locks", "timestamp_ordered"]


class MPACAblationCoordinator(MPACCoordinator):
    """MPAC with one explicitly named mechanism ablated."""

    def __init__(self, client, ablation_mode: AblationMode, lock_manager=None):
        if ablation_mode not in ("no_a2a", "no_semantic_locks", "timestamp_ordered"):
            raise ValueError(f"Unsupported ablation mode: {ablation_mode!r}")
        super().__init__(client, lock_manager=lock_manager)
        self.ablation_mode: AblationMode = ablation_mode

    @property
    def skip_peer_verification(self) -> bool:
        return self.ablation_mode == "no_a2a"

    async def _acquire_locks(self, ops: list[GraphOperation]) -> dict[str, str]:
        if self.ablation_mode == "no_semantic_locks":
            return {}
        return await super()._acquire_locks(ops)

    async def _arbitrate(
        self, ops: list[GraphOperation], conflicts: list[tuple[GraphOperation, GraphOperation]]
    ) -> dict[str, ArbitrationDecision]:
        if not conflicts:
            return {}
        if self.ablation_mode != "timestamp_ordered":
            return await super()._arbitrate(ops, conflicts)

        participants = {op.operation_id for pair in conflicts for op in pair}
        def order_key(op: GraphOperation):
            stamp = str(op.properties.get("timestamp", ""))
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
