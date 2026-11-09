from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Claim(BaseModel):
    """A claim about an indicator of compromise.

    The ``id`` is a deterministic SHA‑256 hash of ``evidence_id`` + ``timestamp``
    (ISO‑8601 UTC). This guarantees that identical evidence at different moments
    yields distinct IDs.
    """

    id: str | None = None
    evidence_id: str
    timestamp: datetime

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def generate_id(cls, evidence_id: str, ts: datetime) -> str:
        """Return a 64‑character hex SHA‑256 hash.

        Args:
            evidence_id: Identifier of the source evidence.
            ts: Timestamp (must be timezone‑aware; if not, UTC is assumed).
        """
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)  # noqa: UP017
        raw = f"{evidence_id}{ts.isoformat()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def model_post_init(self, __context, /) -> None:
        # Auto‑populate ``id`` if not supplied.
        if self.id is None:
            object.__setattr__(self, "id", self.generate_id(self.evidence_id, self.timestamp))


class GraphOperation(BaseModel):
    """Encapsulates a graph write operation with deterministic lock ordering.
    Only `operation` (any string) and `lock_keys` are required.
    All other fields have sensible defaults so tests can instantiate the model
    with minimal data or using the `operation_type` alias.
    """

    # Core operation fields (operation string, not limited to a literal)
    operation: str = Field(..., alias="operation_type")
    operation_id: str = ""
    lock_keys: list[str]
    node_label: str = ""
    node_key: str = ""
    node_value: str = ""
    properties: dict[str, Any] = {}
    principal: str = ""
    claim_id: str | None = None

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @field_validator("lock_keys")
    @classmethod
    def _sort_and_validate(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("lock_keys must contain at least one key")
        return sorted(v)


class ArbitrationDecision(BaseModel):
    """Result of an arbitration step between competing agents."""

    decision: Literal["accept", "reject", "escalate"]
    reason: str | None = None

    model_config = ConfigDict(frozen=True, extra="forbid")


class CoordinationResult(BaseModel):
    """Outcome of a coordination round.

    Basic fields (status, detail) are kept for backward compatibility.
    Additional fields support the Ad‑Hoc and future coordination protocols.
    """

    # Core result fields
    status: Literal["success", "partial", "failure", "ACCEPTED", "RESOLVED"]
    detail: str | None = None

    # Extended fields required by coordinators (optional with defaults)
    run_id: str | None = Field(default_factory=lambda: str(uuid.uuid4()))
    protocol: str | None = None
    ablation_mode: str | None = None
    operation_id: str | None = None
    agent_id: str | None = None
    operations_attempted: int = 0
    operations_committed: int = 0
    conflict_detected: bool = False
    latency_ms: float = 0.0

    model_config = ConfigDict(frozen=True, extra="forbid")


class A2AQuery(BaseModel):
    """Message sent from one agent to another (A2A = agent‑to‑agent)."""

    query_id: str
    payload: dict

    model_config = ConfigDict(frozen=True, extra="forbid")


class A2AResponse(BaseModel):
    """Response from one peer agent to an A2A peer query."""

    peer_id: str
    vote: Literal["CONFIRM", "CONTRADICT", "ABSTAIN"]
    evidence_summary: str | None = None
    confidence: int | None = None

    model_config = ConfigDict(frozen=True, extra="forbid")


__all__ = [
    "A2AResponse",
    "A2AQuery",
    "ArbitrationDecision",
    "Claim",
    "CoordinationResult",
    "GraphOperation",
]
