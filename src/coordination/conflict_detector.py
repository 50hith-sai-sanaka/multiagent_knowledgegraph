"""
Neuro-Symbolic 3-Class Conflict Detector (Rule Fast-Path + LLM Semantic Judge)
File: src/coordination/conflict_detector.py
Sprint: Sprint 2 (STORY-007)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.agents.llm_factory import invoke_structured_llm
from src.schemas.models import GraphOperation

logger = logging.getLogger(__name__)


class LLMConflictClassification(BaseModel):
    """Structured judgment returned by the Semantic Conflict Judge."""

    conflict_class: str = Field(
        description="Strictly one of: 'AGREEMENT_OVERLAP', 'CO_TENANT_COMPATIBLE', 'TEMPORAL_SUPERSESSION', 'EXCLUSIVE_CONTRADICTION'"
    )
    explanation: str = Field(description="1-sentence CTI domain explanation for why these two claims relate this way")


class ConflictDetector:
    """Combines deterministic rule fast-paths with LLM Semantic Conflict Judgment."""

    def detect(self, operations: List[GraphOperation]) -> List[Tuple[GraphOperation, GraphOperation]]:
        """Legacy synchronous lock-key detector kept for backward compatibility."""
        conflicts: List[Tuple[GraphOperation, GraphOperation]] = []
        key_owner: Dict[str, GraphOperation] = {}
        for op in operations:
            for key in op.lock_keys:
                if key in key_owner:
                    conflicts.append((key_owner[key], op))
                else:
                    key_owner[key] = op
        return conflicts

    async def classify_pair_with_llm(self, op_a: GraphOperation, op_b: GraphOperation) -> str:
        """
        Classifies relationship between two operations using deterministic rules and LLM fallback.

        Rule 1: Different subjects or predicates -> UNRELATED
        Rule 2: Non-functional predicate -> CO_TENANT_COMPATIBLE
        Rule 3: Identical canonical target -> AGREEMENT_OVERLAP
        Rule 4: Time gap > 30 days on functional slot -> TEMPORAL_SUPERSESSION
        Fallback: Structured LLM Semantic Judge -> EXCLUSIVE_CONTRADICTION / CO_TENANT_COMPATIBLE
        """
        # Rule 1: Subject / predicate divergence
        if op_a.node_value.strip().lower() != op_b.node_value.strip().lower():
            return "UNRELATED"

        pred_a = (op_a.predicate or "").strip().upper()
        pred_b = (op_b.predicate or "").strip().upper()
        if pred_a != pred_b:
            return "UNRELATED"

        # Pure node operations on same subject by different principals
        if not pred_a and not pred_b and not op_a.target_value and not op_b.target_value:
            if op_a.principal != op_b.principal:
                return "EXCLUSIVE_CONTRADICTION"
            return "AGREEMENT_OVERLAP"

        # Rule 2: Multi-tenancy on non-functional predicate
        if not op_a.is_functional or not op_b.is_functional:
            return "CO_TENANT_COMPATIBLE"

        # Rule 3: Target agreement (corroboration)
        if op_a.target_value.strip().lower() == op_b.target_value.strip().lower():
            return "AGREEMENT_OVERLAP"

        # Rule 4: Temporal Supersession (> 30 days gap)
        gap_days = self._compute_date_gap_days(op_a.valid_from, op_b.valid_from)
        if gap_days > 30:
            return "TEMPORAL_SUPERSESSION"

        # Ambiguous case: Invoke LLM Semantic Conflict Judge
        date_a = (op_a.valid_from or "")[:10]
        date_b = (op_b.valid_from or "")[:10]
        prompt = (
            f"Evaluate two Cyber Threat Intelligence claims on indicator ({op_a.node_label}: {op_a.node_value}):\n"
            f"- Claim A (by {op_a.principal}): predicate={op_a.predicate}, target={op_a.target_value}, "
            f"confidence={op_a.confidence}, date={date_a}\n"
            f"- Claim B (by {op_b.principal}): predicate={op_b.predicate}, target={op_b.target_value}, "
            f"confidence={op_b.confidence}, date={date_b}\n"
            f"Time gap between claims: {gap_days} days.\n"
            f"Classify strictly into one category:\n"
            f"1. AGREEMENT_OVERLAP: Both refer to the same threat family or alias.\n"
            f"2. TEMPORAL_SUPERSESSION: Infrastructure was legitimately reassigned over time.\n"
            f"3. CO_TENANT_COMPATIBLE: Both payloads legitimately co-exist.\n"
            f"4. EXCLUSIVE_CONTRADICTION: Incompatible contradictory attributions for the same infrastructure in the same window."
        )
        try:
            judgment = await invoke_structured_llm(prompt, LLMConflictClassification)
            return judgment.conflict_class
        except Exception as e:
            logger.warning("LLM Conflict Judge unavailable: %s. Defaulting to EXCLUSIVE_CONTRADICTION.", e)
            return "EXCLUSIVE_CONTRADICTION"

    async def detect_semantic(
        self,
        operations: List[GraphOperation],
        existing_claims: Optional[List[GraphOperation]] = None,
    ) -> Tuple[List[Tuple[GraphOperation, GraphOperation]], Dict[str, str]]:
        """
        Classifies incoming operations against each other and against Neo4j-hydrated prior claims.

        Returns:
            contradictions: List of (op_a, op_b) pairs that must be arbitrated.
            classifications: Dict[operation_id -> classification_class].
        """
        # Place existing claims first so FCFS preserves already-committed claims
        all_ops = (existing_claims or []) + list(operations)
        contradictions: List[Tuple[GraphOperation, GraphOperation]] = []
        classifications: Dict[str, str] = {op.operation_id: "CLEAN" for op in all_ops}
        seen_by_slot: Dict[Tuple[str, str], List[GraphOperation]] = {}

        for op in all_ops:
            slot = (op.node_value.strip().lower(), (op.predicate or "").strip().upper())
            for prior_op in seen_by_slot.get(slot, []):
                relation = await self.classify_pair_with_llm(prior_op, op)
                if relation == "EXCLUSIVE_CONTRADICTION":
                    contradictions.append((prior_op, op))
                    classifications[prior_op.operation_id] = "EXCLUSIVE_CONTRADICTION"
                    classifications[op.operation_id] = "EXCLUSIVE_CONTRADICTION"
                elif classifications[op.operation_id] == "CLEAN":
                    classifications[op.operation_id] = relation

            seen_by_slot.setdefault(slot, []).append(op)

        return contradictions, classifications

    @staticmethod
    def _compute_date_gap_days(ts_a: str, ts_b: str) -> int:
        """Parse ISO timestamps and return absolute day difference, normalizing naive/aware datetimes."""
        try:
            clean_a = ts_a.replace("Z", "+00:00")
            clean_b = ts_b.replace("Z", "+00:00")
            t1 = datetime.fromisoformat(clean_a)
            t2 = datetime.fromisoformat(clean_b)
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=timezone.utc)
            else:
                t1 = t1.astimezone(timezone.utc)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=timezone.utc)
            else:
                t2 = t2.astimezone(timezone.utc)
            return abs((t2 - t1).days)
        except Exception:
            return 0
