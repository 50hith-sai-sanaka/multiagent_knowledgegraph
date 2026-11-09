# STORY-005 — Conflict Detector & Arbitration Engine
**Sprint 2 | 8 Points | Lead: @member2 | Reviewer: @member1**

---

## WHY THIS STORY EXISTS

The Ad-Hoc coordinator (Story-004) writes directly to Neo4j with **zero conflict awareness**.
When two agents try to write to the **same entity** at the same time, the second write silently
overwrites the first — classic Last-Write-Wins (LWW) corruption.

This story adds a **Conflict Detector** and **Arbitration Engine** so that:
1. Overlapping writes are detected **before** they hit Neo4j.
2. A deterministic policy (First-Come-First-Served) picks the winner.
3. Losers are rejected cleanly — no silent corruption.

---

## PRE-FLIGHT CHECK

Run these FIRST. All must pass before you write a single line of code.

```bash
# 1 — All Sprint 1 + Story-004 tests must pass
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# Expected last line:  35 passed in X.XXs

# 2 — Redis must be up
docker exec redis-cti redis-cli ping
# Expected: PONG

# 3 — Neo4j must be up
docker ps | grep neo4j
# Expected: a running container line
```

If anything fails, fix it before continuing.

---

## FILES YOU WILL CREATE

```
src/coordination/conflict_detector.py   ← Task CD-001
src/coordination/arbitration_engine.py  ← Task AE-001
src/coordination/arbiter.py             ← Task ARB-001
tests/test_arbiter_coordinator.py       ← Task T-001
```

And one file you will EDIT:
```
src/coordination/__init__.py            ← Task PKG-001  (add exports)
```

---

## TASK CD-001 — Create `src/coordination/conflict_detector.py`

Save exactly this content:

```python
"""
Conflict Detector
File: src/coordination/conflict_detector.py
Story: STORY-005 (Task CD-001)

Given a list of GraphOperation objects, finds pairs of operations that
conflict (share at least one lock_key). The caller (ArbiterCoordinator)
uses this list to decide which operations to accept or reject.

Algorithm: O(N·K) — for each operation, check each of its lock_keys
against a running map of key→first_operation. If the key already exists,
the current operation conflicts with the stored one.
"""

from typing import List, Tuple
from src.schemas.models import GraphOperation


class ConflictDetector:
    """Detects conflicting GraphOperation pairs by inspecting lock_keys."""

    def detect(
        self, operations: List[GraphOperation]
    ) -> List[Tuple[GraphOperation, GraphOperation]]:
        """Return a list of (op_a, op_b) pairs that share at least one lock key.

        The FIRST operation in the list to claim a key is stored as the owner.
        Any later operation that wants the same key conflicts with the owner.

        Args:
            operations: Ordered list of GraphOperation objects (earliest first).

        Returns:
            List of conflict pairs. Each pair is (winner_candidate, loser).
        """
        conflicts: List[Tuple[GraphOperation, GraphOperation]] = []
        key_owner: dict[str, GraphOperation] = {}

        for op in operations:
            for key in op.lock_keys:
                if key in key_owner:
                    # Current op conflicts with whoever first claimed this key
                    conflicts.append((key_owner[key], op))
                else:
                    key_owner[key] = op

        return conflicts
```

---

## TASK AE-001 — Create `src/coordination/arbitration_engine.py`

Save exactly this content:

```python
"""
Arbitration Engine
File: src/coordination/arbitration_engine.py
Story: STORY-005 (Task AE-001)

Applies a First-Come-First-Served (FCFS) policy to a list of conflict pairs
produced by ConflictDetector.

Policy rules:
  - The FIRST operation in each conflict pair is ALWAYS accepted.
  - Any operation that appears as the SECOND (loser) in any pair is rejected.
  - Operations that are not involved in any conflict are accepted by default.

Output: a dict mapping each GraphOperation → ArbitrationDecision.
"""

from typing import Dict, List, Tuple
from src.schemas.models import ArbitrationDecision, GraphOperation


class ArbitrationEngine:
    """Applies FCFS arbitration to a list of conflict pairs."""

    def resolve(
        self,
        all_operations: List[GraphOperation],
        conflicts: List[Tuple[GraphOperation, GraphOperation]],
    ) -> Dict[GraphOperation, ArbitrationDecision]:
        """Produce an ArbitrationDecision for every operation.

        Args:
            all_operations: The full list of GraphOperation objects (in submission order).
            conflicts:       Conflict pairs from ConflictDetector.detect().

        Returns:
            A dict where every operation maps to its ArbitrationDecision.
        """
        # Collect all operations that LOST a conflict (second element of each pair)
        losers: set[GraphOperation] = {loser for _, loser in conflicts}

        decisions: Dict[GraphOperation, ArbitrationDecision] = {}
        for op in all_operations:
            if op in losers:
                decisions[op] = ArbitrationDecision(
                    decision="reject",
                    reason=f"Conflict detected on shared lock key(s); operation {op.operation_id} rejected by FCFS policy.",
                )
            else:
                decisions[op] = ArbitrationDecision(decision="accept", reason=None)

        return decisions
```

---

## TASK ARB-001 — Create `src/coordination/arbiter.py`

Save exactly this content:

```python
"""
Arbiter Coordinator — Protocol 2 (Conflict-Aware)
File: src/coordination/arbiter.py
Story: STORY-005 (Task ARB-001)

Wraps ConflictDetector + ArbitrationEngine + Neo4j writes.

submit() accepts a LIST of GraphOperation objects (batch submission).
  1. Detect conflicts.
  2. Arbitrate (FCFS — first op wins).
  3. Execute only ACCEPTED ops against Neo4j.
  4. Return a CoordinationResult summarising the round.

Status mapping:
  "success"  → all ops accepted
  "partial"  → some ops rejected
  "failure"  → no ops accepted (or an error occurred)
"""

import logging
import time
import uuid
from typing import List, Union

from src.coordination.base import BaseCoordinator
from src.coordination.conflict_detector import ConflictDetector
from src.coordination.arbitration_engine import ArbitrationEngine
from src.schemas.models import GraphOperation, CoordinationResult

logger = logging.getLogger(__name__)


class ArbiterCoordinator(BaseCoordinator):
    """Conflict-aware coordinator implementing FCFS arbitration.

    Usage:
        coordinator = ArbiterCoordinator(neo4j_client)
        result = await coordinator.submit([op1, op2, op3])
    """

    def __init__(self, neo4j_client):
        self._client = neo4j_client
        self._detector = ConflictDetector()
        self._engine = ArbitrationEngine()

    # BaseCoordinator requires submit(GraphOperation) → CoordinationResult.
    # We extend the signature to also accept a list for batch submission.
    async def submit(
        self,
        operation: Union[GraphOperation, List[GraphOperation]],
    ) -> CoordinationResult:
        """Process one or more GraphOperation objects with conflict arbitration.

        Args:
            operation: A single GraphOperation or a list of them.

        Returns:
            CoordinationResult describing the outcome.
        """
        start = time.monotonic()

        # Normalise: always work with a list
        ops: List[GraphOperation] = (
            [operation] if isinstance(operation, GraphOperation) else list(operation)
        )

        # Step 1 — Detect conflicts
        conflicts = self._detector.detect(ops)

        # Step 2 — Arbitrate
        decisions = self._engine.resolve(ops, conflicts)

        # Step 3 — Execute accepted ops
        committed = 0
        for op in ops:
            decision = decisions[op]
            if decision.decision == "accept":
                cypher = (
                    f"MERGE (n:{op.node_label} {{{op.node_key}: $val}}) "
                    f"SET n += $props "
                    f"SET n.node_schema_version = '1.0' "
                    f"SET n.last_writer = $principal "
                    f"SET n.last_write_ts = timestamp()"
                )
                props = dict(op.properties)
                props[op.node_key] = op.node_value
                await self._client.run(
                    cypher,
                    {
                        "val": op.node_value,
                        "props": props,
                        "principal": op.principal,
                    },
                )
                committed += 1
                logger.debug("Committed op %s", op.operation_id)
            else:
                logger.info(
                    "Rejected op %s — reason: %s",
                    op.operation_id,
                    decision.reason,
                )

        latency_ms = (time.monotonic() - start) * 1000

        # Step 4 — Build result
        attempted = len(ops)
        rejected = attempted - committed

        if committed == attempted:
            status = "success"
        elif committed > 0:
            status = "partial"
        else:
            status = "failure"

        detail = (
            f"{committed}/{attempted} operations committed; "
            f"{rejected} rejected by FCFS arbitration."
        )

        return CoordinationResult(
            run_id=str(uuid.uuid4()),
            protocol="ARBITRATION",
            ablation_mode="NONE",
            operation_id=ops[0].operation_id if ops else "",
            status=status,
            detail=detail,
            operations_attempted=attempted,
            operations_committed=committed,
            conflict_detected=len(conflicts) > 0,
            latency_ms=latency_ms,
            agent_id=ops[0].principal if ops else "",
        )
```

---

## TASK PKG-001 — Update `src/coordination/__init__.py`

Open `src/coordination/__init__.py` and **replace its entire contents** with:

```python
# Coordination package
from .base import BaseCoordinator
from .adhoc import AdHocCoordinator
from .lock_manager import SemanticLockManager
from .conflict_detector import ConflictDetector
from .arbitration_engine import ArbitrationEngine
from .arbiter import ArbiterCoordinator

__all__ = [
    "BaseCoordinator",
    "AdHocCoordinator",
    "SemanticLockManager",
    "ConflictDetector",
    "ArbitrationEngine",
    "ArbiterCoordinator",
]
```

---

## TASK T-001 — Create `tests/test_arbiter_coordinator.py`

Save exactly this content:

```python
"""
STORY-005 Gate Tests
File: tests/test_arbiter_coordinator.py
Owner: @member2

Tests for ConflictDetector, ArbitrationEngine, and ArbiterCoordinator.

Gate requirement: ALL 6 tests must pass before Story-005 is considered done.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.coordination.conflict_detector import ConflictDetector
from src.coordination.arbitration_engine import ArbitrationEngine
from src.coordination.arbiter import ArbiterCoordinator
from src.schemas.models import GraphOperation, ArbitrationDecision, CoordinationResult


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def make_mock_client():
    client = MagicMock()
    client.run = AsyncMock(return_value=[])
    return client


def make_op(entity: str, agent: str = "Agent-A", **kwargs):
    """Build a minimal but valid GraphOperation."""
    defaults = dict(
        operation_type="MERGE_NODE",
        operation_id=str(uuid.uuid4()),
        lock_keys=[f"entity:malware:{entity}"],
        node_label="Malware",
        node_key="name",
        node_value=entity,
        principal=agent,
        properties={},
        claim_id="test",
    )
    defaults.update(kwargs)
    return GraphOperation(**defaults)


@pytest.fixture
def arbiter():
    return ArbiterCoordinator(make_mock_client())


# ─────────────────────────────────────────
# ConflictDetector tests
# ─────────────────────────────────────────

def test_detector_no_conflict():
    """Two ops with DIFFERENT lock keys → zero conflicts."""
    detector = ConflictDetector()
    op1 = make_op("entity_A")
    op2 = make_op("entity_B")
    conflicts = detector.detect([op1, op2])
    assert conflicts == [], f"Expected no conflicts, got {conflicts}"


def test_detector_finds_conflict():
    """Two ops with the SAME lock key → one conflict pair returned."""
    detector = ConflictDetector()
    op1 = make_op("same_entity", agent="Agent-A")
    op2 = make_op("same_entity", agent="Agent-B")
    conflicts = detector.detect([op1, op2])
    assert len(conflicts) == 1
    winner, loser = conflicts[0]
    assert winner is op1   # first submitted wins
    assert loser  is op2   # second submitted loses


# ─────────────────────────────────────────
# ArbitrationEngine tests
# ─────────────────────────────────────────

def test_engine_accept_all_when_no_conflicts():
    """No conflicts → all ops get decision='accept'."""
    engine = ArbitrationEngine()
    op1 = make_op("entity_A")
    op2 = make_op("entity_B")
    decisions = engine.resolve([op1, op2], conflicts=[])
    assert decisions[op1].decision == "accept"
    assert decisions[op2].decision == "accept"


def test_engine_rejects_loser():
    """With one conflict pair, the loser gets decision='reject'."""
    engine = ArbitrationEngine()
    op1 = make_op("same_entity", agent="Agent-A")
    op2 = make_op("same_entity", agent="Agent-B")
    conflicts = [(op1, op2)]   # op1 is winner, op2 is loser
    decisions = engine.resolve([op1, op2], conflicts=conflicts)
    assert decisions[op1].decision == "accept"
    assert decisions[op2].decision == "reject"
    assert "FCFS" in decisions[op2].reason


# ─────────────────────────────────────────
# ArbiterCoordinator integration tests
# ─────────────────────────────────────────

async def test_arbiter_all_accepted(arbiter):
    """Two non-conflicting ops → status='success', both committed."""
    op1 = make_op("entity_A")
    op2 = make_op("entity_B")
    result = await arbiter.submit([op1, op2])
    assert isinstance(result, CoordinationResult)
    assert result.status == "success"
    assert result.operations_attempted == 2
    assert result.operations_committed == 2
    assert result.conflict_detected is False


async def test_arbiter_first_wins(arbiter):
    """Two conflicting ops → status='partial', first committed, second rejected."""
    op1 = make_op("same_entity", agent="Agent-A")
    op2 = make_op("same_entity", agent="Agent-B")
    result = await arbiter.submit([op1, op2])
    assert isinstance(result, CoordinationResult)
    assert result.status == "partial"
    assert result.operations_attempted == 2
    assert result.operations_committed == 1
    assert result.conflict_detected is True
    assert result.protocol == "ARBITRATION"
```

---

## EXECUTION — Run Everything Step by Step

### Step 1 — Verify files exist
```bash
ls src/coordination/conflict_detector.py
ls src/coordination/arbitration_engine.py
ls src/coordination/arbiter.py
ls tests/test_arbiter_coordinator.py
# All four must print the filename with no errors
```

### Step 2 — Quick import smoke test
```bash
PYTHONPATH=. ./venv/bin/python -c "
from src.coordination.conflict_detector import ConflictDetector
from src.coordination.arbitration_engine import ArbitrationEngine
from src.coordination.arbiter import ArbiterCoordinator
print('All imports OK')
"
# Expected output: All imports OK
```

### Step 3 — Run ONLY the new Story-005 tests
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_arbiter_coordinator.py -v
```

**Expected output:**
```
tests/test_arbiter_coordinator.py::test_detector_no_conflict PASSED
tests/test_arbiter_coordinator.py::test_detector_finds_conflict PASSED
tests/test_arbiter_coordinator.py::test_engine_accept_all_when_no_conflicts PASSED
tests/test_arbiter_coordinator.py::test_engine_rejects_loser PASSED
tests/test_arbiter_coordinator.py::test_arbiter_all_accepted PASSED
tests/test_arbiter_coordinator.py::test_arbiter_first_wins PASSED
6 passed in X.XXs
```

### Step 4 — Run the FULL test suite (regression check)
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```

**Expected output (last line):**
```
41 passed in X.XXs
```

If you see any FAILED lines → check the error message and compare your file contents against the code in this document exactly.

---

## ACCEPTANCE GATE

Story-005 is DONE when:
- [ ] `PYTHONPATH=. ./venv/bin/pytest tests/test_arbiter_coordinator.py -v` → **6 passed**
- [ ] `PYTHONPATH=. ./venv/bin/pytest tests/ -v` → **41 passed, 0 failed**

---

## QUICK REFERENCE — Models used in this story

| Model | File | Key fields |
|-------|------|------------|
| `GraphOperation` | `src/schemas/models.py` | `operation_type` (alias), `lock_keys`, `node_label`, `node_key`, `node_value`, `principal` |
| `ArbitrationDecision` | `src/schemas/models.py` | `decision` ∈ {`accept`, `reject`, `escalate`}, `reason` |
| `CoordinationResult` | `src/schemas/models.py` | `status` ∈ {`success`, `partial`, `failure`, `ACCEPTED`}, `operations_attempted`, `operations_committed`, `conflict_detected`, `protocol` |

---

*End of STORY-005 execution guide.*
