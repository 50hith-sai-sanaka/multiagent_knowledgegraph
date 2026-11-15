"""
Two-Tier Ontology Validator & Provisional Entity Staging
File: src/ontology/validator.py
Sprint: Sprint 1 (STORY-003)

Provides governance for dynamic schema extensions.
Validates proposed node labels and relationship types against fixed Tier-1
vocabulary, performs semantic similarity checks, and supports Tier-2
provisional staging.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Tier 1 Frozen Vocabularies ---
TIER1_NODE_TYPES: frozenset[str] = frozenset({
    "Malware", "ThreatActor", "Campaign", "IP", "Domain", "URL", "FileHash", "AttackTechnique"
})

TIER1_RELATIONSHIP_METADATA: Dict[str, Dict[str, Any]] = {
    "USES_C2": {"is_functional": True, "description": "IP/Domain infrastructure is utilized as C2 by Malware family"},
    "HOSTED_ON": {"is_functional": False, "description": "URL or Domain is hosted on IP infrastructure"},
    "DISTRIBUTED_VIA": {"is_functional": False, "description": "Malware is distributed via URL"},
    "ATTRIBUTED_TO": {"is_functional": False, "description": "Malware or Campaign attributed to ThreatActor"},
    "PART_OF": {"is_functional": False, "description": "Infrastructure or campaign subset"},
    "EXPLOITS": {"is_functional": False, "description": "Exploitation of vulnerability or technique"},
    "TARGETS": {"is_functional": False, "description": "Victim industry or regional targeting"},
    "MITIGATED_BY": {"is_functional": False, "description": "Security countermeasure mitigation"},
}

TIER1_RELATIONSHIP_TYPES: frozenset[str] = frozenset(TIER1_RELATIONSHIP_METADATA.keys())
SIMILARITY_THRESHOLD: float = 0.85


class OntologyDecision(str, Enum):
    MERGE = "MERGE"
    PENDING = "PENDING"
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass
class OntologyValidationResult:
    decision: OntologyDecision
    proposed_term: str
    proposed_category: str  # "NODE_LABEL" or "RELATIONSHIP_TYPE"
    similarity_score: float = 0.0
    target_type: Optional[str] = None
    confirmation_count: int = 0
    term_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reason: str = ""


class OntologyValidator:
    """Validate proposed terms against Tier-1 schema with Tier-2 Provisional staging."""

    def __init__(self, neo4j_client=None) -> None:
        self._client = neo4j_client
        self._model = None

    def _get_tier1_set(self, category: str) -> frozenset[str]:
        if category == "NODE_LABEL":
            return TIER1_NODE_TYPES
        if category == "RELATIONSHIP_TYPE":
            return TIER1_RELATIONSHIP_TYPES
        raise ValueError(f"Unknown category {category!r}. Must be 'NODE_LABEL' or 'RELATIONSHIP_TYPE'.")

    def is_predicate_functional(self, predicate: str) -> bool:
        pred = predicate.upper()
        if pred in ("USES_C2", "HAS_SAMPLE"):
            return True
        meta = TIER1_RELATIONSHIP_METADATA.get(pred)
        return meta["is_functional"] if meta else False

    def _compute_nearest_similarity(self, proposed: str, candidates: frozenset[str]) -> Tuple[float, str]:
        """Return (score, candidate_name)."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as exc:
                logger.warning("Failed to load sentence-transformers model: %s. Using token overlap fallback.", exc)
                return self._token_overlap_similarity(proposed, candidates)

        try:
            from sentence_transformers import util
            candidate_list = list(candidates)
            proposed_emb = self._model.encode(proposed, convert_to_tensor=True)
            candidate_embs = self._model.encode(candidate_list, convert_to_tensor=True)
            scores = util.cos_sim(proposed_emb, candidate_embs)[0]
            best_idx = int(scores.argmax())
            return float(scores[best_idx]), candidate_list[best_idx]
        except Exception:
            return self._token_overlap_similarity(proposed, candidates)

    def _token_overlap_similarity(self, proposed: str, candidates: frozenset[str]) -> Tuple[float, str]:
        proposed_clean = proposed.lower().replace("_", " ").replace("-", " ")
        best_candidate = next(iter(candidates))
        best_score = 0.0

        for cand in candidates:
            cand_clean = cand.lower().replace("_", " ").replace("-", " ")
            t_words = set(proposed_clean.split())
            c_words = set(cand_clean.split())
            if t_words and c_words:
                overlap = len(t_words & c_words) / float(len(t_words | c_words))
                if overlap > best_score:
                    best_score = overlap
                    best_candidate = cand

        return best_score, best_candidate

    def validate(
        self,
        proposed_term: str,
        category: str,
        confirmation_count: int = 0,
    ) -> OntologyValidationResult:
        tier1 = self._get_tier1_set(category)

        # Step 1: Case-insensitive Tier-1 Exact Match
        lower_map = {t.lower(): t for t in tier1}
        term_clean = proposed_term.strip()
        if term_clean.lower() in lower_map:
            canon = lower_map[term_clean.lower()]
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                proposed_term=proposed_term,
                proposed_category=category,
                similarity_score=1.0,
                target_type=canon,
                confirmation_count=confirmation_count,
                reason=f"Exact match to Tier 1 {category}: {canon}",
            )

        # Step 2: Semantic Similarity
        score, nearest = self._compute_nearest_similarity(proposed_term, tier1)
        if score >= SIMILARITY_THRESHOLD:
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                proposed_term=proposed_term,
                proposed_category=category,
                similarity_score=score,
                target_type=nearest,
                confirmation_count=confirmation_count,
                reason=f"Semantic similarity {score:.3f} >= {SIMILARITY_THRESHOLD} to '{nearest}'",
            )

        # Steps 3-5: Quorum governance
        if confirmation_count >= 2:
            decision = OntologyDecision.APPROVE
            reason = f"New {category} '{proposed_term}' approved by {confirmation_count} distinct agents"
        elif confirmation_count == 1:
            decision = OntologyDecision.PENDING
            reason = f"New {category} '{proposed_term}' is PENDING: 1 agent confirmation so far"
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

    async def validate_and_route(
        self,
        proposed_term: str,
        category: str,
        principal: str,
        neo4j_client=None,
    ) -> Dict[str, Any]:
        """Routes term through validation and returns canonical term and is_functional."""
        val_result = self.validate(proposed_term, category, confirmation_count=1)

        if val_result.decision == OntologyDecision.MERGE:
            canon = val_result.target_type or proposed_term
            is_func = self.is_predicate_functional(canon) if category == "RELATIONSHIP_TYPE" else False
            return {"canonical_term": canon, "status": "APPROVED", "is_functional": is_func}

        status = "PROVISIONAL"
        client = neo4j_client or self._client
        if client:
            try:
                records = await client.run(
                    "MERGE (o:OntologyTerm {term_name: $name, term_type: $cat}) "
                    "ON CREATE SET o.status = 'PENDING', o.confirming_principals = [$p], o.confirmation_count = 1 "
                    "ON MATCH SET o.confirming_principals = CASE "
                    "  WHEN o.confirming_principals IS NULL THEN [$p] "
                    "  WHEN NOT $p IN o.confirming_principals THEN o.confirming_principals + [$p] "
                    "  ELSE o.confirming_principals END "
                    "WITH o, size(o.confirming_principals) AS cnt "
                    "SET o.confirmation_count = cnt, "
                    "    o.status = CASE WHEN cnt >= 2 THEN 'APPROVED' ELSE o.status END "
                    "RETURN o.status AS status",
                    {"name": proposed_term, "cat": category, "p": principal},
                )
                if records and isinstance(records, list) and "status" in records[0]:
                    status = "APPROVED" if records[0]["status"] == "APPROVED" else "PROVISIONAL"
            except Exception as e:
                logger.warning("Could not persist ontology provisional decision: %s", e)

        return {
            "canonical_term": proposed_term,
            "status": status,
            "is_functional": False,
        }

    async def persist_decision(self, result: OntologyValidationResult) -> None:
        """Write an OntologyTerm node for non-MERGE decisions."""
        if result.decision == OntologyDecision.MERGE:
            return

        if self._client is None:
            logger.warning("No Neo4j client – OntologyTerm not persisted for %s", result.proposed_term)
            return

        cypher = """
        MERGE (o:OntologyTerm {term_id: $term_id})
        SET o.term_name = $term_name,
            o.term_type = $term_type,
            o.status = $status,
            o.confirming_principals = coalesce(o.confirming_principals, []),
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
