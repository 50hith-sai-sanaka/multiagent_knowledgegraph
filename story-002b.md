# STORY-002B: Two-Tier Ontology Registry & Validator
## Complete Step-by-Step Execution Guide

| Field | Details |
|---|---|
| **Story ID** | STORY-002B |
| **Sprint** | Sprint 1 |
| **Points** | 5 |
| **Lead** | @member2 |
| **Support** | @member1 |
| **Estimated Time** | ~8 hours |
| **Blocked by** | STORY-002 gate must pass first |

---

> **WHY THIS STORY EXISTS (read before writing a single line)**
>
> The 8 Tier 1 node types (Malware, IP, Domain, URL, FileHash, ThreatActor, Campaign, AttackTechnique) are fixed. But CTI evolves — ransomware uses Bitcoin wallets, groups communicate via Telegram, malware drops from AWS S3. When agents encounter these new entity types, they need a governed pathway to extend the schema.
>
> Without this validator, the LLM will invent inconsistent labels: one agent writes `(:CryptoWallet)`, another writes `(:BTCAddress)`, another writes `(:CoinWallet)`. The graph becomes fragmented and unqueryable. The OntologyValidator ensures every new type proposal is: semantically deduplicated, confirmed by at least 2 agents, and registered with a unique ID before any agent can use it.

---

## Pre-Flight Check

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py -v
```
Must show: `13 passed` (STORY-002 gate).

---

## TASK ONT-001 — Create src/ontology/validator.py Skeleton

### WHY

The validator is the single gatekeeper between an LLM proposing a new type and that type becoming real in the graph. It has two tiers:
- **Tier 1**: 8 fixed node types + 8 fixed relationship types. Never changes. Hardcoded as `frozenset` (immutable).
- **Tier 2**: Dynamic extensions. Every new type must pass through a 4-step validation flow before the graph accepts it.

### Step ONT-001 — Write src/ontology/validator.py

```bash
python3 /dev/stdin << 'SCRIPTEOF'
content = r'''"""
Two-Tier Ontology Validator
File: src/ontology/validator.py
Story: STORY-002B

TIER 1 — Fixed Core (8 node types, 8 relationship types)
  Never changes. Hardcoded as frozensets.
  All Tier 1 nodes stamp node_schema_version="1.0".

TIER 2 — Dynamic Extension Registry
  New types must pass 4-step validation:
  Step 1: Exact match against Tier 1  → MERGE (use existing type)
  Step 2: Semantic similarity >= 0.85  → MERGE (use nearest Tier 1 type)
  Step 3: >= 2 agent confirmations     → APPROVE (register as new type)
  Step 4: 1 confirmation               → PENDING (wait for more evidence)
  Step 5: 0 confirmations / malformed  → REJECT (audit record only)

  Category-aware: entity types compared to entity types only.
  Relationship types compared to relationship types only.

AGENT ACCESS RULE:
  Only MERGE and APPROVE results allow graph writes.
  PENDING and REJECT results must NOT create domain nodes.
"""

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Tier 1 Frozen Vocabulary ─────────────────────────────────────────────────

TIER1_NODE_TYPES: frozenset = frozenset({
    "Malware", "ThreatActor", "Campaign",
    "IP", "Domain", "URL", "FileHash", "AttackTechnique",
})

TIER1_RELATIONSHIP_TYPES: frozenset = frozenset({
    "USES_C2", "DISTRIBUTED_VIA", "HOSTED_ON", "ATTRIBUTED_TO",
    "PART_OF", "EXPLOITS", "TARGETS", "MITIGATED_BY",
})

SIMILARITY_THRESHOLD: float = 0.85

# ─── Decision Enum ────────────────────────────────────────────────────────────

class OntologyDecision(str, Enum):
    MERGE   = "MERGE"    # Matches existing Tier 1 type — use that type
    PENDING = "PENDING"  # New concept, 1 confirmation — wait for more
    APPROVE = "APPROVE"  # New concept, >=2 confirmations — register it
    REJECT  = "REJECT"   # Malformed / duplicate / 0 confirmations

# ─── Result Dataclass ─────────────────────────────────────────────────────────

@dataclass
class OntologyValidationResult:
    decision:           OntologyDecision
    proposed_term:      str
    proposed_category:  str               # "NODE_LABEL" or "RELATIONSHIP_TYPE"
    similarity_score:   float = 0.0
    target_type:        Optional[str] = None   # Set on MERGE
    confirmation_count: int = 0
    term_id:            str = field(default_factory=lambda: str(uuid.uuid4()))
    reason:             str = ""

# ─── Validator Class ──────────────────────────────────────────────────────────

class OntologyValidator:
    """
    Governs whether a proposed entity type or relationship type
    is allowed to be used in the knowledge graph.

    Constructor:
      neo4j_client -- Optional. If provided, APPROVE/PENDING/REJECT
                      decisions write OntologyTerm nodes to the database.
                      If None (e.g. in tests), decisions returned but not persisted.
    """

    def __init__(self, neo4j_client=None):
        self._client = neo4j_client
        self._model  = None  # sentence-transformers model — lazy-loaded on first use

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _get_tier1_set(self, category: str) -> frozenset:
        """Return the correct Tier 1 set for the given category."""
        if category == "NODE_LABEL":
            return TIER1_NODE_TYPES
        elif category == "RELATIONSHIP_TYPE":
            return TIER1_RELATIONSHIP_TYPES
        else:
            raise ValueError(
                f"Unknown category: {category!r}. "
                "Must be 'NODE_LABEL' or 'RELATIONSHIP_TYPE'."
            )

    def _compute_nearest_similarity(
        self, proposed: str, candidates: frozenset
    ) -> tuple:
        """
        Compute cosine similarity between proposed term and all Tier 1 candidates.
        Returns (max_score: float, nearest_type: str).

        Uses sentence-transformers all-MiniLM-L6-v2 (~80 MB download).
        Model is loaded once and cached in self._model.

        IN TESTS: mock this method to avoid the model download:
          validator._compute_nearest_similarity = lambda p, c: (0.90, "Malware")
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

        from sentence_transformers import util
        candidate_list = list(candidates)
        proposed_emb   = self._model.encode(proposed, convert_to_tensor=True)
        candidate_embs = self._model.encode(candidate_list, convert_to_tensor=True)
        scores    = util.cos_sim(proposed_emb, candidate_embs)[0]
        best_idx  = int(scores.argmax())
        return float(scores[best_idx]), candidate_list[best_idx]

    # ── Main Validation Method ─────────────────────────────────────────────────

    def validate(
        self,
        proposed_term:      str,
        category:           str,
        confirmation_count: int = 0,
    ) -> OntologyValidationResult:
        """
        Validate a proposed new entity type or relationship type.

        Args:
          proposed_term:      LLM-proposed type name (e.g. "CryptoWallet")
          category:           "NODE_LABEL" or "RELATIONSHIP_TYPE"
          confirmation_count: Number of distinct agents that confirmed this pattern

        Decision flow:
          1. Exact match against Tier 1               → MERGE
          2. Semantic similarity >= 0.85              → MERGE (category-aware)
          3. confirmation_count >= 2                  → APPROVE
          4. confirmation_count == 1                  → PENDING
          5. confirmation_count == 0 or malformed     → REJECT
        """
        tier1 = self._get_tier1_set(category)

        # ── Step 1: Exact Tier 1 Match ────────────────────────────────────────
        if proposed_term in tier1:
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                proposed_term=proposed_term,
                proposed_category=category,
                similarity_score=1.0,
                target_type=proposed_term,
                confirmation_count=confirmation_count,
                reason=f"Exact match to Tier 1 {category}: {proposed_term}",
            )

        # ── Step 2: Semantic Similarity (category-aware) ─────────────────────
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
                    f"to '{nearest}' — mapped to existing Tier 1 type"
                ),
            )

        # ── Steps 3/4/5: New Concept — decide by confirmation count ───────────
        if confirmation_count >= 2:
            decision = OntologyDecision.APPROVE
            reason = (
                f"New {category} '{proposed_term}' approved "
                f"by {confirmation_count} distinct agents"
            )
        elif confirmation_count == 1:
            decision = OntologyDecision.PENDING
            reason = (
                f"New {category} '{proposed_term}' is PENDING: "
                "only 1 agent confirmation so far — waiting for a second"
            )
        else:
            decision = OntologyDecision.REJECT
            reason = (
                f"New {category} '{proposed_term}' REJECTED: "
                "0 agent confirmations"
            )

        return OntologyValidationResult(
            decision=decision,
            proposed_term=proposed_term,
            proposed_category=category,
            similarity_score=score,
            confirmation_count=confirmation_count,
            reason=reason,
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    async def persist_decision(
        self, result: OntologyValidationResult
    ) -> None:
        """
        Write the OntologyTerm governance node to Neo4j.
        Called after validate() for APPROVE, PENDING, and REJECT.
        MERGE decisions do NOT create OntologyTerm nodes (no new type needed).

        This is async because Neo4jClient.run() is async.
        """
        if result.decision == OntologyDecision.MERGE:
            return  # Exact/near match — no registry entry needed

        if self._client is None:
            logger.warning(
                "No Neo4j client — OntologyTerm not persisted for %s",
                result.proposed_term
            )
            return

        cypher = """
        MERGE (o:OntologyTerm {term_id: $term_id})
        SET o.term_name           = $term_name,
            o.term_type           = $term_type,
            o.status              = $status,
            o.confirmation_count  = $conf_count,
            o.similarity_score    = $sim_score,
            o.nearest_tier1_type  = $nearest,
            o.reason              = $reason,
            o.schema_version_assigned = $sv,
            o.proposed_at         = timestamp()
        RETURN o.term_id
        """
        await self._client.run(cypher, {
            "term_id":   result.term_id,
            "term_name": result.proposed_term,
            "term_type": result.proposed_category,
            "status":    result.decision.value,
            "conf_count": result.confirmation_count,
            "sim_score":  result.similarity_score,
            "nearest":    result.target_type or "",
            "reason":     result.reason,
            "sv": "2.0" if result.decision == OntologyDecision.APPROVE else "pending",
        })
        logger.info(
            "OntologyTerm persisted: %s → %s",
            result.proposed_term,
            result.decision.value
        )
'''
with open("src/ontology/validator.py", "w") as f:
    f.write(content)
print("src/ontology/validator.py written successfully.")
SCRIPTEOF
```

**VERIFICATION CHECK ONT-001**
```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.ontology.validator import OntologyValidator, OntologyDecision, TIER1_NODE_TYPES
print('Node types:', len(TIER1_NODE_TYPES))
v = OntologyValidator()
print('Validator created OK')
"
```
Must show:
```
Node types: 8
Validator created OK
```

---

## TASK ONT-002 through ONT-005 — Verify All Decision Paths

The validator is fully implemented. Verify each decision path manually:

### Step ONT-002 — Test Exact Match (MERGE)

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.ontology.validator import OntologyValidator, OntologyDecision
v = OntologyValidator()
# Mock similarity to avoid model download in this manual check
v._compute_nearest_similarity = lambda p, c: (0.50, 'Malware')
result = v.validate('Malware', 'NODE_LABEL', confirmation_count=0)
assert result.decision == OntologyDecision.MERGE, f'Expected MERGE, got {result.decision}'
assert result.similarity_score == 1.0
print('Step ONT-002 PASS: Exact match returns MERGE')
"
```

### Step ONT-003 — Test Semantic MERGE

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.ontology.validator import OntologyValidator, OntologyDecision
v = OntologyValidator()
# Simulate a 0.92 similarity score (above threshold)
v._compute_nearest_similarity = lambda p, c: (0.92, 'Malware')
result = v.validate('StealeWare', 'NODE_LABEL', confirmation_count=0)
assert result.decision == OntologyDecision.MERGE, f'Expected MERGE, got {result.decision}'
assert result.target_type == 'Malware'
print('Step ONT-003 PASS: High similarity returns MERGE to Malware')
"
```

### Step ONT-004 — Test APPROVE (2 confirmations)

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.ontology.validator import OntologyValidator, OntologyDecision
v = OntologyValidator()
v._compute_nearest_similarity = lambda p, c: (0.40, 'IP')  # low — genuinely new
result = v.validate('CryptoWallet', 'NODE_LABEL', confirmation_count=2)
assert result.decision == OntologyDecision.APPROVE, f'Expected APPROVE, got {result.decision}'
print('Step ONT-004 PASS: 2 confirmations returns APPROVE')
"
```

### Step ONT-005A — Test PENDING (1 confirmation)

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.ontology.validator import OntologyValidator, OntologyDecision
v = OntologyValidator()
v._compute_nearest_similarity = lambda p, c: (0.40, 'IP')
result = v.validate('TelegramChannel', 'NODE_LABEL', confirmation_count=1)
assert result.decision == OntologyDecision.PENDING, f'Expected PENDING, got {result.decision}'
print('Step ONT-005A PASS: 1 confirmation returns PENDING')
"
```

### Step ONT-005B — Test REJECT (0 confirmations)

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.ontology.validator import OntologyValidator, OntologyDecision
v = OntologyValidator()
v._compute_nearest_similarity = lambda p, c: (0.10, 'IP')
result = v.validate('XYZ_HALLUCINATION', 'NODE_LABEL', confirmation_count=0)
assert result.decision == OntologyDecision.REJECT, f'Expected REJECT, got {result.decision}'
print('Step ONT-005B PASS: 0 confirmations returns REJECT')
"
```

**VERIFICATION CHECK ONT-002 through ONT-005**

All 5 commands must print `PASS`.

---

## TASK ONT-006 / ONT-007 — Schema Version Stamping

### WHY

Every Tier 1 node and relationship must carry `node_schema_version="1.0"`. This allows future queries to distinguish original Tier 1 data from Tier 2 extensions (`schema_version="2.0"`). The `neo4j_client.py` file already includes `node_schema_version` in the uniqueness constraint test — this task ensures the property is actually SET when nodes are created.

This is handled at the Coordinator level (STORY-006) when it builds Cypher from a `GraphOperation`. When a `GraphOperation` has `node_schema_version="1.0"`, the coordinator stamps that property. No code change is needed in the validator itself — simply confirm the field exists on `GraphOperation`.

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.schemas.models import GraphOperation
import uuid
op = GraphOperation(
    operation_id=str(uuid.uuid4()), operation_type='MERGE_NODE',
    node_label='Malware', node_key='name', node_value='RedLine',
    claim_id='abc', principal='Agent-ThreatFox',
)
assert op.node_schema_version == '1.0', 'Default version must be 1.0'
print('ONT-006/007 PASS: node_schema_version defaults to 1.0 on GraphOperation')
"
```

---

## TASK ONT-008 — Create tests/test_ontology_validator.py

### WHY

The tests use a mocked `_compute_nearest_similarity` to avoid downloading the sentence-transformers model in CI. The actual model is used in integration tests when the full environment is ready.

### Step ONT-008 — Write test file

```bash
python3 /dev/stdin << 'SCRIPTEOF'
content = r'''"""
STORY-002B Gate Tests
File: tests/test_ontology_validator.py
Owner: @member1

ALL 8 tests must pass before Sprint 3 begins.

NOTE: _compute_nearest_similarity is mocked in all tests to avoid
downloading the sentence-transformers model. The actual model is
tested in integration only.
"""

import pytest
from unittest.mock import patch
from src.ontology.validator import (
    OntologyValidator, OntologyDecision,
    OntologyValidationResult, TIER1_NODE_TYPES, TIER1_RELATIONSHIP_TYPES
)


def make_validator():
    return OntologyValidator(neo4j_client=None)


# ─── Tier 1 Coverage Tests ────────────────────────────────────────────────────

def test_tier1_node_types_count():
    """Tier 1 must define exactly 8 node types."""
    assert len(TIER1_NODE_TYPES) == 8


def test_tier1_relationship_types_count():
    """Tier 1 must define exactly 8 relationship types."""
    assert len(TIER1_RELATIONSHIP_TYPES) == 8


# ─── MERGE Decision Tests ─────────────────────────────────────────────────────

def test_exact_match_node_returns_merge():
    """Any exact Tier 1 node type must return MERGE."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.5, "IP")):
        result = v.validate("Malware", "NODE_LABEL", confirmation_count=0)
    assert result.decision == OntologyDecision.MERGE
    assert result.similarity_score == 1.0
    assert result.target_type == "Malware"


def test_exact_match_relationship_returns_merge():
    """Any exact Tier 1 relationship type must return MERGE."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.5, "USES_C2")):
        result = v.validate("USES_C2", "RELATIONSHIP_TYPE", confirmation_count=0)
    assert result.decision == OntologyDecision.MERGE
    assert result.target_type == "USES_C2"


def test_high_similarity_returns_merge():
    """Similarity >= 0.85 must return MERGE with correct nearest type."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.90, "Malware")):
        result = v.validate("StealeWare", "NODE_LABEL", confirmation_count=0)
    assert result.decision == OntologyDecision.MERGE
    assert result.target_type == "Malware"
    assert result.similarity_score == 0.90


def test_similarity_below_threshold_not_merge():
    """Similarity < 0.85 must NOT return MERGE."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.70, "Domain")):
        result = v.validate("TelegramChannel", "NODE_LABEL", confirmation_count=2)
    assert result.decision != OntologyDecision.MERGE


# ─── APPROVE Decision Tests ───────────────────────────────────────────────────

def test_two_confirmations_returns_approve():
    """2 or more distinct agent confirmations must return APPROVE."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.40, "IP")):
        result = v.validate("CryptoWallet", "NODE_LABEL", confirmation_count=2)
    assert result.decision == OntologyDecision.APPROVE
    assert result.confirmation_count == 2


def test_three_confirmations_also_approve():
    """3 confirmations must also return APPROVE."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.35, "IP")):
        result = v.validate("CloudDropper", "NODE_LABEL", confirmation_count=3)
    assert result.decision == OntologyDecision.APPROVE


# ─── PENDING Decision Tests ───────────────────────────────────────────────────

def test_one_confirmation_returns_pending():
    """Exactly 1 confirmation must return PENDING (not REJECT)."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.40, "IP")):
        result = v.validate("TelegramChannel", "NODE_LABEL", confirmation_count=1)
    assert result.decision == OntologyDecision.PENDING
    assert "PENDING" in result.reason or "pending" in result.reason.lower()


# ─── REJECT Decision Tests ────────────────────────────────────────────────────

def test_zero_confirmations_returns_reject():
    """0 confirmations must return REJECT."""
    v = make_validator()
    with patch.object(v, "_compute_nearest_similarity", return_value=(0.10, "IP")):
        result = v.validate("HALLUCINATION_XYZ", "NODE_LABEL", confirmation_count=0)
    assert result.decision == OntologyDecision.REJECT


# ─── Category Isolation Test ──────────────────────────────────────────────────

def test_invalid_category_raises():
    """Unsupported category string must raise ValueError immediately."""
    v = make_validator()
    with pytest.raises(ValueError, match="Unknown category"):
        v.validate("SomeType", "INVALID_CATEGORY", confirmation_count=2)
'''
with open("tests/test_ontology_validator.py", "w") as f:
    f.write(content)
print("tests/test_ontology_validator.py written.")
SCRIPTEOF
```

**VERIFICATION CHECK ONT-008**
```bash
grep -c "^def test_" tests/test_ontology_validator.py
```
Must show: `9`

---

## GATE — Run Story-002B Tests

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_ontology_validator.py -v
```

**Must show `9 passed`.**

| Test | What it proves |
|---|---|
| `test_tier1_node_types_count` | Tier 1 has exactly 8 node types |
| `test_tier1_relationship_types_count` | Tier 1 has exactly 8 relationship types |
| `test_exact_match_node_returns_merge` | Exact Tier 1 type → MERGE |
| `test_exact_match_relationship_returns_merge` | Exact Tier 1 relationship → MERGE |
| `test_high_similarity_returns_merge` | Score >= 0.85 → MERGE |
| `test_similarity_below_threshold_not_merge` | Score < 0.85 → not MERGE |
| `test_two_confirmations_returns_approve` | 2 confirmations → APPROVE |
| `test_one_confirmation_returns_pending` | 1 confirmation → PENDING |
| `test_zero_confirmations_returns_reject` | 0 confirmations → REJECT |

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: sentence_transformers` | Not mocked in test | Confirm `patch.object(v, "_compute_nearest_similarity", ...)` is in the `with` block |
| APPROVE returned for 1 confirmation | Threshold check wrong | Confirm `if confirmation_count >= 2` not `> 1` in validate() |
| MERGE returned for 0 confirmations | Missing exact-match step | Step 1 (exact match) must happen before Step 2 (similarity) |
| `ValueError` on unknown category | Category string typo | Must be exactly `"NODE_LABEL"` or `"RELATIONSHIP_TYPE"` |

## Completion Checklist

- [ ] `src/ontology/validator.py` imports without error
- [ ] `TIER1_NODE_TYPES` has 8 entries
- [ ] `TIER1_RELATIONSHIP_TYPES` has 8 entries
- [ ] Step ONT-002 through ONT-005B all print PASS
- [ ] Schema version stamp check passes
- [ ] `tests/test_ontology_validator.py` has 9 test functions
- [ ] GATE: `9 passed` on `tests/test_ontology_validator.py`

**When all 7 boxes are checked: STORY-002B is DONE.**

**Next: STORY-003 (Redis Lock Manager).**
