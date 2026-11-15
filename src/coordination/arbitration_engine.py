"""
Arbitration Engine with Laplace-Smoothed Bayesian Log-Odds and FCFS Fallback
File: src/coordination/arbitration_engine.py
Sprint: Sprint 2 (STORY-008)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from src.schemas.models import ArbitrationDecision, GraphOperation, PeerAttestation

logger = logging.getLogger(__name__)

# Empirical source authority priors
PRINCIPAL_PRIORS: Dict[str, float] = {
    "malwarebazaar": 0.833,
    "threatfox": 0.783,
    "urlhaus": 0.739,
    "otx": 0.636,
}
DEFAULT_PRIOR = 0.50

# Temporal half-life decay rates per day (lambda)
TEMPORAL_DECAY_RATES: Dict[str, float] = {
    "filehash": 0.0,
    "domain": 0.015,
    "url": 0.03,
    "ip": 0.05,
}


class ArbitrationEngine:
    """Arbitrates conflicting operations using Bayesian Log-Odds or FCFS fallback."""

    def resolve(
        self,
        operations: List[GraphOperation],
        conflicts: List[Tuple[GraphOperation, GraphOperation]],
        mode: str = "fcfs",
    ) -> Dict[str, ArbitrationDecision]:
        """
        Resolve conflicts across operations.

        Args:
            operations: All candidate operations in the round.
            conflicts: List of (op_a, op_b) conflicting pairs.
            mode: "bayesian" for Bayesian log-odds, "fcfs" for first-come-first-served.

        Returns:
            Dict[operation_id -> ArbitrationDecision]
        """
        if not conflicts:
            return {
                op.operation_id: ArbitrationDecision(decision="accept", reason="no conflict")
                for op in operations
            }

        if mode.lower() == "bayesian":
            return self._resolve_bayesian(operations, conflicts)
        return self._resolve_fcfs(operations, conflicts)

    def _resolve_fcfs(
        self,
        operations: List[GraphOperation],
        conflicts: List[Tuple[GraphOperation, GraphOperation]],
    ) -> Dict[str, ArbitrationDecision]:
        """Legacy FCFS arbitration: First operation in pair wins."""
        losers: Set[str] = {loser.operation_id for _, loser in conflicts}
        decisions: Dict[str, ArbitrationDecision] = {}
        for op in operations:
            if op.operation_id in losers:
                decisions[op.operation_id] = ArbitrationDecision(
                    decision="reject",
                    reason=f"Rejected under FCFS: superseded by earlier operation",
                )
            else:
                decisions[op.operation_id] = ArbitrationDecision(
                    decision="accept",
                    reason="Accepted under FCFS policy",
                )
        return decisions

    def _resolve_bayesian(
        self,
        operations: List[GraphOperation],
        conflicts: List[Tuple[GraphOperation, GraphOperation]],
    ) -> Dict[str, ArbitrationDecision]:
        """Laplace-Smoothed Bayesian Log-Odds arbitration."""
        # Find all operations participating in conflicts
        conflict_op_ids: Set[str] = {op.operation_id for pair in conflicts for op in pair}
        decisions: Dict[str, ArbitrationDecision] = {}

        # Non-conflicting operations accept cleanly
        for op in operations:
            if op.operation_id not in conflict_op_ids:
                decisions[op.operation_id] = ArbitrationDecision(
                    decision="accept",
                    reason="clean write without conflict",
                    posterior_prob=1.0,
                )

        # Group conflicting operations by slot
        slots: Dict[Tuple[str, str], List[GraphOperation]] = {}
        for op in operations:
            if op.operation_id in conflict_op_ids:
                slot = (op.node_value.strip().lower(), op.predicate.strip().upper())
                slots.setdefault(slot, []).append(op)

        for slot, slot_ops in slots.items():
            posteriors: Dict[str, float] = {}
            for op in slot_ops:
                op_target = op.target_value.strip().lower()
                opponents = [
                    other
                    for other in slot_ops
                    if other.operation_id != op.operation_id
                    and (not op_target or other.target_value.strip().lower() != op_target)
                ]
                corroborators = [
                    other
                    for other in slot_ops
                    if other.operation_id != op.operation_id
                    and op_target
                    and other.target_value.strip().lower() == op_target
                ]
                posteriors[op.operation_id] = self.compute_posterior(op, opponents, corroborators)

            # Winner is operation with highest posterior probability
            winner = max(slot_ops, key=lambda o: (posteriors[o.operation_id], o.operation_id))
            winner_target = (winner.target_value or "").strip().lower()
            for op in slot_ops:
                prob = posteriors[op.operation_id]
                # Accept winner and all corroborators sharing the winning non-empty target hypothesis
                if winner_target and (op.target_value or "").strip().lower() == winner_target:
                    decisions[op.operation_id] = ArbitrationDecision(
                        decision="accept",
                        reason=f"Bayesian posterior winner/corroborator for '{winner.target_value}' (P={prob:.3f})",
                        winning_operation_id=winner.operation_id,
                        posterior_prob=prob,
                    )
                elif op.operation_id == winner.operation_id:
                    decisions[op.operation_id] = ArbitrationDecision(
                        decision="accept",
                        reason=f"Bayesian posterior winner (P={prob:.3f})",
                        winning_operation_id=winner.operation_id,
                        posterior_prob=prob,
                    )
                else:
                    decisions[op.operation_id] = ArbitrationDecision(
                        decision="reject",
                        reason=f"Bayesian posterior inferior (P={prob:.3f} vs P_win={posteriors[winner.operation_id]:.3f})",
                        winning_operation_id=winner.operation_id,
                        posterior_prob=prob,
                    )

        return decisions

    def compute_posterior(
        self,
        target_op: GraphOperation,
        opponents: List[GraphOperation],
        corroborators: Optional[List[GraphOperation]] = None,
    ) -> float:
        """
        Computes Bayesian posterior probability P(h) with lineage deduplication.
        """
        # Deduplication tracking for upstream signatures
        seen_lineages: Set[str] = set()
        support_weights: List[float] = []
        contradict_weights: List[float] = []

        # 1. Target operation evidence
        w_target = self._calculate_evidence_weight(
            principal=target_op.principal,
            node_label=target_op.node_label,
            confidence=target_op.confidence,
            valid_from=target_op.valid_from,
        )
        if target_op.upstream_origin_signature:
            seen_lineages.add(target_op.upstream_origin_signature)
        support_weights.append(w_target)

        # 2. Corroborating operations on the same target hypothesis
        for corr in (corroborators or []):
            if corr.upstream_origin_signature and corr.upstream_origin_signature in seen_lineages:
                pass
            else:
                if corr.upstream_origin_signature:
                    seen_lineages.add(corr.upstream_origin_signature)
                w_corr = self._calculate_evidence_weight(
                    principal=corr.principal,
                    node_label=corr.node_label,
                    confidence=corr.confidence,
                    valid_from=corr.valid_from,
                )
                support_weights.append(w_corr)

            for att in corr.peer_attestations:
                if att.upstream_origin_signature and att.upstream_origin_signature in seen_lineages:
                    continue
                if att.upstream_origin_signature:
                    seen_lineages.add(att.upstream_origin_signature)

                w_corr_att = self._calculate_evidence_weight(
                    principal=att.responder_principal,
                    node_label=corr.node_label,
                    confidence=att.confidence,
                    valid_from=corr.valid_from,
                )
                if att.stance == "CONFIRM":
                    support_weights.append(w_corr_att)
                elif att.stance == "CONTRADICT":
                    contradict_weights.append(w_corr_att)

        # 3. Peer Attestations attached to target operation
        for att in target_op.peer_attestations:
            if att.upstream_origin_signature and att.upstream_origin_signature in seen_lineages:
                continue
            if att.upstream_origin_signature:
                seen_lineages.add(att.upstream_origin_signature)

            w_att = self._calculate_evidence_weight(
                principal=att.responder_principal,
                node_label=target_op.node_label,
                confidence=att.confidence,
                valid_from=target_op.valid_from,
            )
            if att.stance == "CONFIRM":
                support_weights.append(w_att)
            elif att.stance == "CONTRADICT":
                contradict_weights.append(w_att)

        # 4. Opponent operations and their supporting peer attestations
        for opp in opponents:
            if opp.upstream_origin_signature and opp.upstream_origin_signature in seen_lineages:
                pass
            else:
                if opp.upstream_origin_signature:
                    seen_lineages.add(opp.upstream_origin_signature)
                w_opp = self._calculate_evidence_weight(
                    principal=opp.principal,
                    node_label=opp.node_label,
                    confidence=opp.confidence,
                    valid_from=opp.valid_from,
                )
                contradict_weights.append(w_opp)

            for att in opp.peer_attestations:
                if att.upstream_origin_signature and att.upstream_origin_signature in seen_lineages:
                    continue
                if att.upstream_origin_signature:
                    seen_lineages.add(att.upstream_origin_signature)

                w_opp_att = self._calculate_evidence_weight(
                    principal=att.responder_principal,
                    node_label=opp.node_label,
                    confidence=att.confidence,
                    valid_from=opp.valid_from,
                )
                if att.stance == "CONFIRM":
                    contradict_weights.append(w_opp_att)
                elif att.stance == "CONTRADICT":
                    support_weights.append(w_opp_att)

        # Net Log-Odds calculation
        log_odds = 0.0
        for w in support_weights:
            clamped = max(0.05, min(0.95, w))
            log_odds += math.log((1.0 + clamped) / (1.0 - clamped))

        for w in contradict_weights:
            clamped = max(0.05, min(0.95, w))
            log_odds -= math.log((1.0 + clamped) / (1.0 - clamped))

        # Posterior probability: P = 1 / (1 + exp(-log_odds))
        try:
            return 1.0 / (1.0 + math.exp(-log_odds))
        except OverflowError:
            return 1.0 if log_odds > 0 else 0.0

    def _calculate_evidence_weight(
        self,
        principal: str,
        node_label: str,
        confidence: int,
        valid_from: str,
    ) -> float:
        """Calculates decay-adjusted evidence weight clamped to [0.05, 0.95]."""
        p_prior = PRINCIPAL_PRIORS.get(principal.strip().lower(), DEFAULT_PRIOR)
        lambda_rate = TEMPORAL_DECAY_RATES.get(node_label.strip().lower(), 0.02)

        # Compute age in days with naive/aware normalization
        try:
            clean_ts = valid_from.replace("Z", "+00:00")
            ts = datetime.fromisoformat(clean_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            now = datetime.now(timezone.utc)
            delta_days = max(0, (now - ts).days)
        except Exception:
            delta_days = 0

        decay = min(0.50, lambda_rate * delta_days)
        conf_factor = max(0.1, min(1.0, confidence / 100.0))
        effective = p_prior * (1.0 - decay) * conf_factor
        return max(0.05, min(0.95, effective))
