# src/ontology/validator.py
"""Two‑Tier Ontology Validator

Provides governance for dynamic schema extensions (Story 002B).
It validates a proposed node label or relationship type against the fixed Tier 1
vocabulary, performs semantic similarity checks, and decides whether the proposal
should be MERGE‑ed, PENDING, APPROVED or REJECTED.

The validator can be used standalone (e.g. in unit‑tests) or together with the
async ``Neo4jClient`` – in the latter case approved/pending/rejected decisions are
persisted as ``OntologyTerm`` nodes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ─── Tier 1 frozen vocabularies ────────────────────────────────────────────────
TIER1_NODE_TYPES: frozenset[str] = frozenset(
    {
        "Malware",
        "ThreatActor",
        "Campaign",
        "IP",
        "Domain",
        "URL",
        "FileHash",
        "AttackTechnique",
    }
)

TIER1_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "USES_C2",
        "DISTRIBUTED_VIA",
        "HOSTED_ON",
        "ATTRIBUTED_TO",
        "PART_OF",
        "EXPLOITS",
        "TARGETS",
        "MITIGATED_BY",
    }
)

# Similarity threshold for semantic MERGE decisions
SIMILARITY_THRESHOLD: float = 0.85


# ─── Decision enum ─────────────────────────────────────────────────────────────
class OntologyDecision(str, Enum):
    MERGE = "MERGE"  # Exact or high‑similarity match to Tier 1
    PENDING = "PENDING"  # New term, only one confirmation
    APPROVE = "APPROVE"  # New term, ≥2 confirmations
    REJECT = "REJECT"  # Malformed or 0 confirmations


# ─── Result container ────────────────────────────────────────────────────────
@dataclass
class OntologyValidationResult:
    decision: OntologyDecision
    proposed_term: str
    proposed_category: str  # "NODE_LABEL" or "RELATIONSHIP_TYPE"
    similarity_score: float = 0.0
    target_type: str | None = None  # Tier 1 type we map to on MERGE
    confirmation_count: int = 0
    term_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reason: str = ""


# ─── Validator class ────────────────────────────────────────────────────────
class OntologyValidator:
    """Validate a proposed ontology term.

    The validator is deliberately lightweight – it loads the heavy sentence‑
    transformer model only when needed. In unit‑tests the ``_compute_nearest_``
    method can be monkey‑patched to avoid the download.
    """

    def __init__(self, neo4j_client=None):
        self._client = neo4j_client
        self._model = None  # lazy‑loaded SentenceTransformer

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _get_tier1_set(self, category: str) -> frozenset[str]:
        if category == "NODE_LABEL":
            return TIER1_NODE_TYPES
        if category == "RELATIONSHIP_TYPE":
            return TIER1_RELATIONSHIP_TYPES
        raise ValueError(f"Unknown category {category!r}. Must be 'NODE_LABEL' or 'RELATIONSHIP_TYPE'.")

    def _compute_nearest_similarity(self, proposed: str, candidates: frozenset[str]) -> tuple[float, str]:
        """Return the highest cosine similarity and the matching Tier 1 term.

        The implementation uses ``sentence‑transformers``. If the model fails to
        load (e.g. offline environments) we log a warning and fall back to a
        similarity of ``0.0``.
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as exc:  # noqa: BLE001 – third-party model load, any error is possible
                logger.warning("Failed to load sentence‑transformers model: %s", exc)
                return 0.0, ""
        from sentence_transformers import util

        candidate_list = list(candidates)
        proposed_emb = self._model.encode(proposed, convert_to_tensor=True)
        candidate_embs = self._model.encode(candidate_list, convert_to_tensor=True)
        scores = util.cos_sim(proposed_emb, candidate_embs)[0]
        best_idx = int(scores.argmax())
        return float(scores[best_idx]), candidate_list[best_idx]

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def validate(
        self,
        proposed_term: str,
        category: str,
        confirmation_count: int = 0,
    ) -> OntologyValidationResult:
        """Validate ``proposed_term`` and return a structured result.

        Decision flow:
        1️⃣ Exact match against Tier 1 → ``MERGE``
        2️⃣ Semantic similarity ≥ ``SIMILARITY_THRESHOLD`` → ``MERGE``
        3️⃣ ``confirmation_count`` ≥ 2 → ``APPROVE``
        4️⃣ ``confirmation_count`` == 1 → ``PENDING``
        5️⃣ otherwise → ``REJECT``
        """
        tier1 = self._get_tier1_set(category)

        # Step 1 – exact match
        if proposed_term in tier1:
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                proposed_term=proposed_term,
                proposed_category=category,
                similarity_score=1.0,
                target_type=proposed_term,
                confirmation_count=confirmation_count,
                reason=f"Exact match to Tier 1 {category}: {proposed_term}",
            )

        # Step 2 – semantic similarity (category‑aware)
        score, nearest = self._compute_nearest_similarity(proposed_term, tier1)
        if score >= SIMILARITY_THRESHOLD:
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                proposed_term=proposed_term,
                proposed_category=category,
                similarity_score=score,
                target_type=nearest,
                confirmation_count=confirmation_count,
                reason=(
                    f"Semantic similarity {score:.3f} >= {SIMILARITY_THRESHOLD} "
                    f"to '{nearest}' — mapped to existing Tier 1 type"
                ),
            )

        # Steps 3‑5 – new concept handling based on confirmations
        if confirmation_count >= 2:
            decision = OntologyDecision.APPROVE
            reason = f"New {category} '{proposed_term}' approved by {confirmation_count} distinct agents"
        elif confirmation_count == 1:
            decision = OntologyDecision.PENDING
            reason = (
                f"New {category} '{proposed_term}' is PENDING: only 1 agent confirmation so far — waiting for a second"
            )
        else:
            decision = OntologyDecision.REJECT
            reason = f"New {category} '{proposed_term}' REJECTED: 0 agent confirmations"

        return OntologyValidationResult(
            decision=decision,
            proposed_term=proposed_term,
            proposed_category=category,
            similarity_score=score,
            confirmation_count=confirmation_count,
            reason=reason,
        )

    # ---------------------------------------------------------------------
    # Persistence (optional – requires a Neo4jClient instance)
    # ---------------------------------------------------------------------
    async def persist_decision(self, result: OntologyValidationResult) -> None:
        """Write an ``OntologyTerm`` node for non‑MERGE decisions.

        ``Neo4jClient`` is async, so this method is async as well. If the validator
        was instantiated without a client we simply log and return.
        """
        if result.decision == OntologyDecision.MERGE:
            return  # No registry entry needed

        if self._client is None:
            logger.warning("No Neo4j client – OntologyTerm not persisted for %s", result.proposed_term)
            return

        cypher = """
        MERGE (o:OntologyTerm {term_id: $term_id})
        SET o.term_name = $term_name,
            o.term_type = $term_type,
            o.status = $status,
            o.confirmation_count = $conf_count,
            o.similarity_score = $sim_score,
            o.nearest_tier1_type = $nearest,
            o.reason = $reason,
            o.schema_version_assigned = $sv,
            o.proposed_at = timestamp()
        RETURN o.term_id
        """
        await self._client.run(
            cypher,
            {
                "term_id": result.term_id,
                "term_name": result.proposed_term,
                "term_type": result.proposed_category,
                "status": result.decision.value,
                "conf_count": result.confirmation_count,
                "sim_score": result.similarity_score,
                "nearest": result.target_type or "",
                "reason": result.reason,
                "sv": "2.0" if result.decision == OntologyDecision.APPROVE else "pending",
            },
        )
        logger.info("OntologyTerm persisted: %s → %s", result.proposed_term, result.decision.value)
