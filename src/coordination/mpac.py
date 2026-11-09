"""MPAC coordinator with deterministic locking and evidence-grounded writes."""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

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


@asynccontextmanager
async def _transaction_context(session):
    """Handle Neo4j driver versions and async test doubles consistently."""
    transaction = session.begin_transaction()
    if inspect.isawaitable(transaction):
        transaction = await transaction
    async with transaction as tx:
        yield tx


class MPACCoordinator(BaseCoordinator):
    """Coordinate graph operations with semantic locks and FCFS arbitration.

    The coordinator is deliberately conservative: Tier-1 node labels and
    validated property identifiers only. Values are passed as Cypher parameters.
    """

    def __init__(self, neo4j_client, lock_manager: SemanticLockManager | None = None):
        self._client = neo4j_client
        self._lock_manager = lock_manager or SemanticLockManager()
        self._detector = ConflictDetector()
        self._engine = ArbitrationEngine()

    async def _acquire_locks(self, ops: list[GraphOperation]) -> dict[str, str]:
        keys = sorted({key for op in ops for key in op.lock_keys})
        if getattr(self._lock_manager, "_use_redis", False) and not getattr(self._lock_manager, "_redis", None):
            await self._lock_manager.connect()
        return await self._lock_manager.acquire(keys)

    async def _arbitrate(
        self, ops: list[GraphOperation], conflicts: list[tuple[GraphOperation, GraphOperation]]
    ) -> dict[str, ArbitrationDecision]:
        if not conflicts:
            return {}
        return self._engine.resolve(ops, conflicts)

    async def submit(
        self, operation: GraphOperation | list[GraphOperation]
    ) -> CoordinationResult:
        started = time.monotonic()
        ops = [operation] if isinstance(operation, GraphOperation) else list(operation)
        session_id = str(uuid.uuid4())
        tokens = await self._acquire_locks(ops)
        try:
            conflicts = self._detector.detect(ops)
            decisions = await self._arbitrate(ops, conflicts)
            committed = await self._write_with_provenance(ops, decisions, conflicts)
            attempted = len(ops)
            status = "ACCEPTED" if not conflicts else "RESOLVED"
            result = CoordinationResult(
                run_id=session_id,
                protocol="MPAC",
                ablation_mode=getattr(self, "ablation_mode", "NONE"),
                operation_id=ops[0].operation_id if ops else "",
                status=status,
                detail=f"{committed}/{attempted} domain writes committed; {attempted - committed} rejected",
                operations_attempted=attempted,
                operations_committed=committed,
                conflict_detected=bool(conflicts),
                latency_ms=(time.monotonic() - started) * 1000,
                agent_id=ops[0].principal if ops else "",
            )
            logger.info("MPAC session %s completed: %s", session_id, status)
            return result
        finally:
            await self._lock_manager.release(tokens)

    async def _govern_label(self, op: GraphOperation) -> _LabelGovernance:
        """Allow Tier-1 labels immediately and approved Tier-2 labels after governance.

        Pending or rejected proposals stay auditable and do not authorize a domain write.
        Unsafe identifiers fail before any Cypher is built.
        """
        if not _IDENTIFIER.fullmatch(op.node_label):
            raise ValueError(f"Unapproved graph label: {op.node_label!r}")
        if op.node_label in TIER1_NODE_TYPES:
            return _LabelGovernance(op.node_label, "1.0", True, "Tier-1 label")
        registrar = getattr(self._client, "validate_and_register_type", None)
        if registrar is None:
            raise ValueError(f"Unapproved graph label: {op.node_label!r}")
        result = await registrar(op.node_label, "NODE_LABEL", op.principal or "unknown")
        decision = str(result.get("decision", "REJECT")).upper()
        target = str(result.get("target_type") or op.node_label)
        if not _IDENTIFIER.fullmatch(target):
            raise ValueError(f"Unapproved graph label: {target!r}")
        reason = str(result.get("reason") or decision)
        if decision in _WRITABLE_GOVERNANCE and (decision != "MERGE" or target in TIER1_NODE_TYPES):
            version = "1.0" if target in TIER1_NODE_TYPES else "2.0"
            return _LabelGovernance(target, version, True, reason)
        if decision == "MERGE":
            return _LabelGovernance(op.node_label, "2.0", False, reason)
        return _LabelGovernance(op.node_label, "2.0", False, reason)

    @staticmethod
    def _validate_operation(op: GraphOperation) -> None:
        if not _IDENTIFIER.fullmatch(op.node_label):
            raise ValueError(f"Unapproved graph label: {op.node_label!r}")
        if not _IDENTIFIER.fullmatch(op.node_key):
            raise ValueError(f"Unsafe node key: {op.node_key!r}")
        for key in op.properties:
            if not _IDENTIFIER.fullmatch(key):
                raise ValueError(f"Unsafe property key: {key!r}")

    @staticmethod
    def _property_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list) and all(isinstance(v, (str, int, float, bool)) for v in value):
            return value
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)

    async def _write_with_provenance(
        self,
        ops: list[GraphOperation],
        decisions: dict[str, ArbitrationDecision],
        conflicts: list[tuple[GraphOperation, GraphOperation]],
    ) -> int:
        """Atomically write accepted domain nodes and linked audit/provenance.

        Rejected operations produce claim/evidence/conflict/decision records but
        never execute a domain-node MERGE or SET.
        """
        if self._client is None:
            raise RuntimeError("Neo4j client is required")
        conflict_for_op: dict[str, set[str]] = {}
        for left, right in conflicts:
            raw = "|".join(sorted((left.operation_id, right.operation_id)))
            conflict_id = hashlib.sha256(raw.encode()).hexdigest()
            conflict_for_op.setdefault(left.operation_id, set()).add(conflict_id)
            conflict_for_op.setdefault(right.operation_id, set()).add(conflict_id)

        committed = 0
        async with self._client.session() as session:
            async with _transaction_context(session) as tx:
                for op in ops:
                    governed = await self._govern_label(op)
                    if governed.label != op.node_label:
                        op = op.model_copy(update={"node_label": governed.label})
                    self._validate_operation(op)
                    decision = decisions.get(op.operation_id)
                    accepted = (decision is None or decision.decision == "accept") and governed.writable
                    if not governed.writable:
                        decision = ArbitrationDecision(decision="reject", reason=governed.reason)
                    claim_id = op.claim_id or op.operation_id or str(uuid.uuid4())
                    evidence_id = hashlib.sha256(
                        f"{op.principal}|{op.operation_id}|{op.node_value}".encode()
                    ).hexdigest()
                    raw_props = dict(op.properties)
                    source = str(raw_props.pop("source", op.principal))
                    record_id = str(raw_props.pop("record_id", op.operation_id))
                    timestamp = str(raw_props.pop("timestamp", ""))
                    raw_data = raw_props.pop("raw_data", None)
                    safe_props = {
                        key: converted
                        for key, value in raw_props.items()
                        if key not in {op.node_key, "node_schema_version", "created_by", "last_writer", "last_write_ts"}
                        and (converted := self._property_value(value)) is not None
                    }
                    safe_props[op.node_key] = op.node_value
                    safe_props["node_schema_version"] = governed.schema_version
                    safe_props["last_writer"] = op.principal
                    safe_props["last_write_ts"] = int(time.time() * 1000)
                    if accepted:
                        await tx.run(
                            f"MERGE (n:{op.node_label} {{{op.node_key}: $identity}}) SET n += $props",
                            {"identity": op.node_value, "props": safe_props},
                        )
                        committed += 1
                    raw_json = json.dumps(raw_data, sort_keys=True, default=str) if raw_data is not None else ""
                    await tx.run(
                        "MERGE (p:Principal {id: $principal}) "
                        "MERGE (e:Evidence {id: $evidence_id}) "
                        "SET e.source = $source, e.record_id = $record_id, e.timestamp = $timestamp, "
                        "    e.raw_data_json = $raw_json "
                        "MERGE (c:Claim {id: $claim_id}) "
                        "SET c.operation_id = $operation_id, c.node_label = $label, "
                        "    c.node_key = $node_key, c.node_value = $node_value, "
                        "    c.accepted = $accepted, c.recorded_at = timestamp() "
                        "MERGE (p)-[:ASSERTED]->(c) "
                        "MERGE (c)-[:GROUNDED_IN]->(e)",
                        {
                            "principal": op.principal or "unknown",
                            "evidence_id": evidence_id,
                            "source": source,
                            "record_id": record_id,
                            "timestamp": timestamp,
                            "raw_json": raw_json,
                            "claim_id": claim_id,
                            "operation_id": op.operation_id,
                            "label": op.node_label,
                            "node_key": op.node_key,
                            "node_value": op.node_value,
                            "accepted": accepted,
                        },
                    )
                    if accepted:
                        await tx.run(
                            f"MATCH (c:Claim {{id: $claim_id}}), (n:{op.node_label} {{{op.node_key}: $identity}}) "
                            "MERGE (c)-[:ASSERTS]->(n)",
                            {"claim_id": claim_id, "identity": op.node_value},
                        )
                    if decision is not None:
                        await tx.run(
                            "MATCH (c:Claim {id: $claim_id}) "
                            "MERGE (d:Decision {id: $decision_id}) "
                            "SET d.verdict = $verdict, d.reason = $reason, d.created_at = timestamp() "
                            "MERGE (c)-[:HAS_DECISION]->(d)",
                            {
                                "claim_id": claim_id,
                                "decision_id": hashlib.sha256(f"{op.operation_id}|decision".encode()).hexdigest(),
                                "verdict": decision.decision,
                                "reason": decision.reason or "",
                            },
                        )
                    for conflict_id in conflict_for_op.get(op.operation_id, set()):
                        await tx.run(
                            "MATCH (c:Claim {id: $claim_id}) "
                            "MERGE (x:Conflict {id: $conflict_id}) "
                            "SET x.node_label = $label, x.node_key = $node_key, x.node_value = $node_value, "
                            "    x.status = 'DETECTED', x.created_at = timestamp() "
                            "MERGE (c)-[:INVOLVED_IN]->(x)",
                            {
                                "claim_id": claim_id,
                                "conflict_id": conflict_id,
                                "label": op.node_label,
                                "node_key": op.node_key,
                                "node_value": op.node_value,
                            },
                        )
        return committed
