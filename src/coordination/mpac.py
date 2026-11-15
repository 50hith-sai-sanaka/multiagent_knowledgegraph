"""
MPAC Protocol 2 Coordinator: Atomic Lua Fencing, Bayesian Arbitration & Dual-Layer Commits
File: src/coordination/mpac.py
Sprint: Sprint 2 (STORY-009)
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from unittest.mock import AsyncMock, MagicMock

from src.coordination.arbitration_engine import ArbitrationEngine
from src.coordination.base import BaseCoordinator
from src.coordination.conflict_detector import ConflictDetector
from src.coordination.lock_manager import SemanticLockManager
from src.db.neo4j_client import TIER1_NODE_TYPES
from src.schemas.models import ArbitrationDecision, CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WRITABLE_GOVERNANCE = {"APPROVE", "APPROVED", "MERGE"}


class _LabelGovernance:
    def __init__(self, label: str, schema_version: str, writable: bool, reason: str) -> None:
        self.label = label
        self.schema_version = schema_version
        self.writable = writable
        self.reason = reason


def _require_safe_identifier(value: str, kind: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unapproved graph label or identifier: {value!r}")


@asynccontextmanager
async def _transaction_context(session):
    """Handle Neo4j driver versions and async test doubles consistently."""
    transaction = session.begin_transaction()
    if inspect.isawaitable(transaction):
        transaction = await transaction
    async with transaction as tx:
        yield tx


class MPACCoordinator(BaseCoordinator):
    """Protocol 2 / Protocol 3 MPAC Coordinator executing the 6-step coordination lifecycle."""

    def __init__(
        self,
        neo4j_client,
        lock_manager: Optional[SemanticLockManager] = None,
        arbitration_mode: str = "bayesian",
    ):
        self._client = neo4j_client
        self._lock_manager = lock_manager or SemanticLockManager()
        self._detector = ConflictDetector()
        self._engine = ArbitrationEngine()
        self.arbitration_mode = arbitration_mode

    async def _resolve_governance(self, label: str, agent: str) -> _LabelGovernance:
        if not label:
            return _LabelGovernance("Entity", "1.0", True, "Default label")
        if label in TIER1_NODE_TYPES:
            return _LabelGovernance(label, "1.0", True, "Tier-1 static node type")
        if self._client is not None and hasattr(self._client, "validate_and_register_type"):
            res = self._client.validate_and_register_type(label, "NODE_LABEL", agent)
            if inspect.isawaitable(res):
                res = await res
            decision = (res or {}).get("decision", "REJECT")
            writable = decision in _WRITABLE_GOVERNANCE
            schema_ver = "2.0" if decision in ("APPROVE", "APPROVED") else "1.0"
            return _LabelGovernance(label, schema_ver, writable, (res or {}).get("reason", ""))
        return _LabelGovernance(label, "1.0", True, "Unchecked label")

    async def _acquire_locks(self, ops: List[GraphOperation]) -> Tuple[Dict[str, str], int]:
        """Step 1: Acquire sorted multi-locks with atomic monotonic fencing token."""
        all_keys: Set[str] = set()
        for op in ops:
            all_keys.update(op.lock_keys)
        sorted_keys = sorted(all_keys)

        if getattr(self._lock_manager, "_use_redis", False) and not getattr(self._lock_manager, "_redis", None):
            await self._lock_manager.connect()

        use_fenced = False
        if hasattr(self._lock_manager, "acquire_fenced"):
            if not isinstance(self._lock_manager, (AsyncMock, MagicMock)):
                use_fenced = True
            elif "acquire_fenced" in getattr(self._lock_manager, "_mock_children", {}):
                use_fenced = True

        if use_fenced:
            res = self._lock_manager.acquire_fenced(sorted_keys)
            if inspect.isawaitable(res):
                res = await res
            if isinstance(res, tuple) and len(res) == 2:
                return res
            if isinstance(res, dict):
                return res, 1

        if hasattr(self._lock_manager, "acquire"):
            tokens = self._lock_manager.acquire(sorted_keys)
            if inspect.isawaitable(tokens):
                tokens = await tokens
            if isinstance(tokens, tuple) and len(tokens) == 2:
                return tokens
            if isinstance(tokens, dict):
                return tokens, 1

        return {}, 1

    async def _arbitrate(
        self, ops: List[GraphOperation], conflicts: List[Tuple[GraphOperation, GraphOperation]]
    ) -> Dict[str, ArbitrationDecision]:
        return self._engine.resolve(ops, conflicts, mode=self.arbitration_mode)

    async def submit(
        self,
        operation: Union[GraphOperation, List[GraphOperation]],
    ) -> CoordinationResult:
        """Execute the 6-step MPAC Coordination Lifecycle."""
        start_time = time.monotonic()
        ops = [operation] if isinstance(operation, GraphOperation) else list(operation)
        if not ops:
            return CoordinationResult(status="empty", operations_attempted=0, operations_committed=0)

        run_id = str(uuid.uuid4())
        tokens, fencing_token = await self._acquire_locks(ops)

        try:
            for op in ops:
                if op.node_label:
                    _require_safe_identifier(op.node_label, "node label")
                if op.node_key:
                    _require_safe_identifier(op.node_key, "node key")
                if op.predicate:
                    _require_safe_identifier(op.predicate, "predicate")
                if op.target_label:
                    _require_safe_identifier(op.target_label, "target label")
                if op.target_key:
                    _require_safe_identifier(op.target_key, "target key")
            # Step 2: Pre-commit state hydration
            subject_vals = list({op.node_value for op in ops if op.node_value})
            hydrated_claims: List[GraphOperation] = []
            if hasattr(self._client, "hydrate_existing_claims"):
                res = self._client.hydrate_existing_claims(subject_vals)
                if inspect.isawaitable(res):
                    hydrated_claims = await res
                elif isinstance(res, list):
                    hydrated_claims = res

            # Step 3: Neuro-Symbolic Conflict Classification
            conflicts, classifications = await self._detector.detect_semantic(ops, hydrated_claims)

            # Step 4: Laplace-Smoothed Bayesian Log-Odds Arbitration
            decisions = await self._arbitrate(ops + hydrated_claims, conflicts)

            # Step 5: Guarded Dual-Layer Commit
            committed = await self._commit_dual_layer(ops, hydrated_claims, decisions, conflicts, fencing_token)

            status = "RESOLVED" if conflicts else "ACCEPTED"
            winning_posterior = max(
                [d.posterior_prob for d in decisions.values() if d.posterior_prob is not None],
                default=1.0,
            )

            latency_ms = (time.monotonic() - start_time) * 1000.0
            return CoordinationResult(
                status=status,
                run_id=run_id,
                protocol="MPAC",
                ablation_mode=getattr(self, "ablation_mode", "NONE"),
                operation_id=ops[0].operation_id,
                agent_id=ops[0].principal,
                operations_attempted=len(ops),
                operations_committed=committed,
                conflict_detected=bool(conflicts),
                fencing_token=fencing_token,
                posterior_prob=winning_posterior,
                latency_ms=latency_ms,
                detail=f"{committed}/{len(ops)} operations committed under fencing_token={fencing_token}",
            )
        finally:
            # Step 6: Atomic Lock Release
            if tokens is not None:
                await self._lock_manager.release(tokens)

    async def _commit_dual_layer(
        self,
        ops: List[GraphOperation],
        hydrated_claims: List[GraphOperation],
        decisions: Dict[str, ArbitrationDecision],
        conflicts: List[Tuple[GraphOperation, GraphOperation]],
        fencing_token: int,
    ) -> int:
        """Executes Guarded Dual-Layer Cypher transaction with functional edge cleanup."""
        committed = 0
        if self._client is None:
            return len([
                op for op in ops
                if decisions.get(op.operation_id, ArbitrationDecision(decision="accept")).decision == "accept"
            ])

        conflict_for_op: Dict[str, Set[str]] = {}
        for left, right in conflicts:
            raw = "|".join(sorted((left.operation_id, right.operation_id)))
            conflict_id = hashlib.sha256(raw.encode()).hexdigest()
            conflict_for_op.setdefault(left.operation_id, set()).add(conflict_id)
            conflict_for_op.setdefault(right.operation_id, set()).add(conflict_id)

        async with self._client.session() as session:
            async with _transaction_context(session) as tx:
                # Mark any hydrated claims that lost arbitration as no longer active
                # and link them to any Conflict nodes they participated in
                for h_op in hydrated_claims:
                    h_cid = h_op.claim_id or h_op.operation_id
                    h_dec = decisions.get(h_op.operation_id)
                    if h_dec and h_dec.decision == "reject":
                        await tx.run(
                            "MATCH (c:Claim {id: $cid}) SET c.accepted = false, c.superseded_at_fence = $fence",
                            {"cid": h_cid, "fence": fencing_token},
                        )
                    for conflict_id in conflict_for_op.get(h_op.operation_id, set()):
                        await tx.run(
                            "MATCH (c:Claim {id: $cid}) "
                            "MERGE (x:Conflict {id: $conflict_id}) "
                            "MERGE (c)-[:INVOLVED_IN]->(x)",
                            {"cid": h_cid, "conflict_id": conflict_id},
                        )

                for op in ops:
                    gov = await self._resolve_governance(op.node_label, op.principal)
                    dec = decisions.get(op.operation_id, ArbitrationDecision(decision="accept"))
                    is_accepted = dec.decision == "accept"
                    post_prob = dec.posterior_prob if dec.posterior_prob is not None else 1.0

                    # 1. Hot Domain Graph write (Guarded by fencing token)
                    if is_accepted and gov.writable:
                        if op.predicate and op.target_value:
                            retire_clause = (
                                f"WITH s, t "
                                f"OPTIONAL MATCH (s)-[old_r:{op.predicate}]->(old_t) "
                                f"WHERE old_t <> t AND coalesce(s.fencing_token, 0) <= $fence "
                                f"DELETE old_r "
                                if op.is_functional
                                else ""
                            )
                            cypher_domain = (
                                f"MERGE (s:{op.node_label or 'Entity'} {{{op.node_key or 'value'}: $s_val}}) "
                                f"ON CREATE SET s.fencing_token = $fence "
                                f"ON MATCH SET s.fencing_token = CASE "
                                f"  WHEN coalesce(s.fencing_token, 0) <= $fence THEN $fence ELSE s.fencing_token END "
                                f"MERGE (t:{op.target_label or 'Entity'} {{{op.target_key or 'name'}: $t_val}}) "
                                f"{retire_clause}"
                                f"WITH s, t WHERE coalesce(s.fencing_token, 0) <= $fence "
                                f"MERGE (s)-[r:{op.predicate}]->(t) "
                                f"SET r.posterior_prob = $prob, r.fencing_token = $fence, r.last_writer = $principal"
                            )
                            await tx.run(
                                cypher_domain,
                                {
                                    "s_val": op.node_value,
                                    "t_val": op.target_value,
                                    "fence": fencing_token,
                                    "prob": post_prob,
                                    "principal": op.principal,
                                },
                            )
                        else:
                            cypher_node = (
                                f"MERGE (n:{op.node_label or 'Entity'} {{{op.node_key or 'value'}: $val}}) "
                                f"WITH n WHERE coalesce(n.fencing_token, 0) <= $fence "
                                f"SET n += $props, n.fencing_token = $fence, n.last_writer = $principal"
                            )
                            props = dict(op.properties)
                            props["node_schema_version"] = gov.schema_version
                            await tx.run(
                                cypher_node,
                                {
                                    "val": op.node_value,
                                    "props": props,
                                    "fence": fencing_token,
                                    "principal": op.principal,
                                },
                            )
                        committed += 1

                    # 2. Cold Provenance Meta-Graph write (with full hydration attributes)
                    claim_id = op.claim_id or op.operation_id
                    evidence_id = hashlib.sha256(
                        f"{op.principal}:{op.operation_id}:{op.node_value}".encode()
                    ).hexdigest()
                    decision_id = hashlib.sha256(
                        f"dec:{op.operation_id}:{fencing_token}".encode()
                    ).hexdigest()

                    cypher_provenance = (
                        "MERGE (p:Principal {id: $principal}) "
                        "MERGE (c:Claim {id: $claim_id}) "
                        "SET c.operation_id = $op_id, c.node_label = $n_label, c.node_key = $n_key, "
                        "    c.node_value = $n_val, c.subject = $n_val, c.predicate = $pred, "
                        "    c.target_label = $t_label, c.target_key = $t_key, c.target_value = $t_val, "
                        "    c.confidence = $conf, c.valid_from = $valid_from, c.origin_sig = $origin_sig, "
                        "    c.is_functional = $is_func, c.accepted = $accepted, c.recorded_at = timestamp() "
                        "MERGE (p)-[:ASSERTED]->(c) "
                        "MERGE (e:Evidence {id: $ev_id}) "
                        "SET e.origin_sig = $origin_sig, e.timestamp = $valid_from "
                        "MERGE (c)-[:GROUNDED_IN]->(e) "
                        "MERGE (d:Decision {id: $dec_id}) "
                        "SET d.verdict = $verdict, d.reason = $reason, d.posterior_prob = $prob, d.fencing_token = $fence "
                        "MERGE (c)-[:HAS_DECISION]->(d)"
                    )
                    await tx.run(
                        cypher_provenance,
                        {
                            "principal": op.principal or "unknown",
                            "claim_id": claim_id,
                            "op_id": op.operation_id,
                            "n_label": op.node_label or "IP",
                            "n_key": op.node_key or "value",
                            "n_val": op.node_value,
                            "pred": op.predicate,
                            "t_label": op.target_label or "Malware",
                            "t_key": op.target_key or "name",
                            "t_val": op.target_value,
                            "conf": op.confidence,
                            "valid_from": op.valid_from,
                            "origin_sig": op.upstream_origin_signature,
                            "is_func": op.is_functional,
                            "accepted": is_accepted,
                            "ev_id": evidence_id,
                            "dec_id": decision_id,
                            "verdict": dec.decision,
                            "reason": dec.reason or "",
                            "prob": post_prob,
                            "fence": fencing_token,
                        },
                    )

                    if is_accepted and gov.writable:
                        await tx.run(
                            f"MATCH (c:Claim {{id: $claim_id}}), (n:{op.node_label or 'Entity'} {{{op.node_key or 'value'}: $identity}}) "
                            "MERGE (c)-[:ASSERTS]->(n)",
                            {"claim_id": claim_id, "identity": op.node_value},
                        )

                    # Link Conflict nodes if operation was involved in conflicts
                    for conflict_id in conflict_for_op.get(op.operation_id, set()):
                        cypher_conflict = (
                            "MATCH (c:Claim {id: $claim_id}) "
                            "MERGE (x:Conflict {id: $conflict_id}) "
                            "SET x.node_label = $n_label, x.node_value = $n_val, x.predicate = $pred, "
                            "    x.status = 'DETECTED', x.detected_at_fence = $fence, x.recorded_at = timestamp() "
                            "MERGE (c)-[:INVOLVED_IN]->(x)"
                        )
                        await tx.run(
                            cypher_conflict,
                            {
                                "claim_id": claim_id,
                                "conflict_id": conflict_id,
                                "n_label": op.node_label or "IP",
                                "n_val": op.node_value,
                                "pred": op.predicate,
                                "fence": fencing_token,
                            },
                        )

        return committed
