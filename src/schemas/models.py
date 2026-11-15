"""
Core Pydantic Data Contracts for ProGRESS
File: src/schemas/models.py
Sprint: Sprint 1 (STORY-001)

Provides:
  - Claim: Grounded threat claim with deterministic SHA256 ID
  - PeerAttestation: Cryptographically signed peer verification judgment
  - GraphOperation: Graph mutation operation (nodes + functional/non-functional edges)
  - ArbitrationDecision: Outcome of conflict resolution with Bayesian posterior
  - CoordinationResult: Protocol outcome with monotonic fencing token
  - A2AQuery / A2AResponse: Agent-to-Agent message schemas
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Claim(BaseModel):
    """A claim about an indicator of compromise.

    The id is a deterministic SHA-256 hash of evidence_id + timestamp (ISO-8601 UTC).
    Normalizes aware datetimes to UTC to prevent timezone offset hash collisions.
    """

    id: Optional[str] = None
    evidence_id: str
    timestamp: datetime

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def generate_id(cls, evidence_id: str, ts: datetime) -> str:
        """Return a 64-character hex SHA-256 hash normalized to UTC."""
        if ts.tzinfo is None:
            utc_ts = ts.replace(tzinfo=timezone.utc)
        else:
            utc_ts = ts.astimezone(timezone.utc)
        raw = f"{evidence_id}{utc_ts.isoformat()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if self.id is None:
            object.__setattr__(self, "id", self.generate_id(self.evidence_id, self.timestamp))


class PeerAttestation(BaseModel):
    """Cryptographically signed peer attestation returned via A2A G2CP protocol."""

    responder_principal: str = Field(description="Principal ID of the peer e.g. 'urlhaus'")
    stance: Literal["CONFIRM", "CONTRADICT", "ABSTAIN"] = Field(description="Peer verification stance")
    confidence: int = Field(default=80, ge=0, le=100, description="Confidence in the judgment")
    counter_object: Optional[str] = Field(default=None, description="Competing canonical malware if CONTRADICT")
    evidence_id: str = Field(default="", description="Peer local record ID")
    upstream_origin_signature: str = Field(default="", description="Upstream reporter signature for dedup")
    signature: str = Field(default="", description="HMAC-SHA256 signature over claim")

    model_config = ConfigDict(frozen=True, extra="forbid")


class GraphOperation(BaseModel):
    """Encapsulates a graph write operation with deterministic lock ordering.

    Supports both node writes and edge relationships (subject -[predicate]-> target).
    Pure node operations leave predicate empty, preventing accidental slot locks.
    """

    # Core operation fields
    operation: str = Field(..., alias="operation_type")
    operation_id: str = Field(default_factory=lambda: f"op-{uuid.uuid4().hex[:8]}")
    lock_keys: List[str]

    # Subject entity fields
    node_label: str = ""
    node_key: str = ""
    node_value: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    principal: str = ""
    claim_id: Optional[str] = None

    # Edge relationship fields (Default empty string for predicate indicates pure node write)
    predicate: str = ""
    target_label: str = ""
    target_key: str = ""
    target_value: str = ""
    confidence: int = 80
    evidence_ids: List[str] = Field(default_factory=list)
    raw_evidence_hash: str = ""
    upstream_origin_signature: str = ""
    valid_from: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: Optional[str] = None
    is_functional: bool = False
    taint_class: str = "TRUSTED_TELEMETRY"
    peer_attestations: List[PeerAttestation] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @field_validator("lock_keys")
    @classmethod
    def _sort_and_validate(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("lock_keys must contain at least one key")
        return sorted(v)


class ArbitrationDecision(BaseModel):
    """Result of an arbitration step between competing agents."""

    decision: Literal["accept", "reject", "escalate"]
    reason: Optional[str] = None
    winning_operation_id: Optional[str] = None
    posterior_prob: Optional[float] = None
    conflict_class: Optional[str] = None

    model_config = ConfigDict(frozen=True, extra="forbid")


class CoordinationResult(BaseModel):
    """Outcome of a coordination round."""

    status: Literal["success", "partial", "failure", "ACCEPTED", "RESOLVED", "empty"]
    detail: Optional[str] = None
    run_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    protocol: Optional[str] = None
    ablation_mode: Optional[str] = None
    operation_id: Optional[str] = None
    agent_id: Optional[str] = None
    operations_attempted: int = 0
    operations_committed: int = 0
    conflict_detected: bool = False
    latency_ms: float = 0.0

    # Added for MPAC Protocol 2 monotonicity and Bayesian arbitration
    fencing_token: int = 0
    posterior_prob: Optional[float] = None

    model_config = ConfigDict(frozen=True, extra="forbid")


class A2AQuery(BaseModel):
    """Message sent from one agent to another."""

    query_id: str
    payload: dict

    model_config = ConfigDict(frozen=True, extra="forbid")


class A2AResponse(BaseModel):
    """Response from one peer agent to an A2A peer query."""

    peer_id: str
    vote: Literal["CONFIRM", "CONTRADICT", "ABSTAIN"]
    evidence_summary: Optional[str] = None
    confidence: Optional[int] = None

    model_config = ConfigDict(frozen=True, extra="forbid")


__all__ = [
    "A2AQuery",
    "A2AResponse",
    "ArbitrationDecision",
    "Claim",
    "CoordinationResult",
    "GraphOperation",
    "PeerAttestation",
]
