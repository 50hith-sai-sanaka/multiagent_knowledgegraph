# STORY-004: Protocol 1 — Ad-Hoc Coordinator (Baseline)
## Complete Step-by-Step Execution Guide

| Field | Details |
|---|---|
| **Story ID** | STORY-004 |
| **Sprint** | Sprint 2 |
| **Points** | 5 |
| **Lead** | @member1 |
| **Blocked by** | Sprint 1 Full Gate (all Sprint 1 tests must pass) |

---

> **WHY THIS STORY EXISTS**
>
> The Ad-Hoc Coordinator is the intentional **worst case**. It writes directly to Neo4j with no locking, no conflict detection, no arbitration. Concurrent writes produce Last-Write-Wins (LWW) data corruption.
>
> Without this baseline, you cannot demonstrate that MPAC improves anything. The benchmark shows: Protocol 1 GIR (low) vs Protocol 2 GIR (high). This story builds the Protocol 1 side of that comparison.

---

## Pre-Flight Check

```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v 2>&1 | tail -3
```
Must show all Sprint 1 tests passing.

---

## TASK P1-001 — Create src/coordination/base.py

Save this as `src/coordination/base.py`:

```python
"""
Base Coordinator Abstract Class
File: src/coordination/base.py
Story: STORY-004 (Task P1-001)

All three protocols implement this interface.
Agents call submit() — the protocol handles the rest.
"""

from abc import ABC, abstractmethod
from src.schemas.models import GraphOperation, CoordinationResult


class BaseCoordinator(ABC):
    """Abstract base for all coordination protocols."""

    @abstractmethod
    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        """
        Process one agent graph-write operation.
        Returns CoordinationResult with status, latency, and conflict info.
        """
        ...
```

**VERIFICATION CHECK P1-001**
```bash
PYTHONPATH=. ./venv/bin/python3 -c "from src.coordination.base import BaseCoordinator; print('OK')"
```

---

## TASK P1-002 — Create src/coordination/adhoc.py

Save this as `src/coordination/adhoc.py`:

```python
"""
Protocol 1 — Ad-Hoc Coordinator (Baseline / Worst Case)
File: src/coordination/adhoc.py
Story: STORY-004 (Task P1-002)

Writes DIRECTLY to Neo4j WITHOUT:
  - Distributed locking (no SemanticLockManager)
  - Conflict detection (no ConflictDetector)
  - Arbitration (no ArbitrationEngine)
  - Full provenance (minimal claim tracking only)

PURPOSE: establish the benchmark control baseline.
Concurrent writes INTENTIONALLY produce LWW corruption.
GIR < 100% is the expected and desired outcome for Protocol 1.

NEVER use this for production data — benchmark only.
"""

import logging
import time
import uuid
from src.coordination.base import BaseCoordinator
from src.schemas.models import GraphOperation, CoordinationResult

logger = logging.getLogger(__name__)


class AdHocCoordinator(BaseCoordinator):
    """
    Uncoordinated direct writer. Benchmark baseline.
    """

    def __init__(self, neo4j_client):
        self._client = neo4j_client

    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        t_start = time.monotonic()

        # Direct MERGE — no validation, no locking, no conflict detection
        cypher = (
            f"MERGE (n:{operation.node_label} {{{operation.node_key}: $val}}) "
            f"SET n += $props "
            f"SET n.node_schema_version = '1.0' "
            f"SET n.last_writer = $principal "
            f"SET n.last_write_ts = timestamp()"
        )
        props = dict(operation.properties)
        props[operation.node_key] = operation.node_value

        await self._client.run(cypher, {
            "val":       operation.node_value,
            "props":     props,
            "principal": operation.principal,
        })

        latency = (time.monotonic() - t_start) * 1000
        return CoordinationResult(
            run_id=str(uuid.uuid4()),
            protocol="AD_HOC",
            ablation_mode="NONE",
            operation_id=operation.operation_id,
            status="ACCEPTED",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            latency_ms=latency,
            agent_id=operation.principal,
        )
```

**VERIFICATION CHECK P1-002**
```bash
PYTHONPATH=. ./venv/bin/python3 -c "from src.coordination.adhoc import AdHocCoordinator; print('OK')"
```

---

## TASK P1-003 — Create tests/test_adhoc_coordinator.py

Save this as `tests/test_adhoc_coordinator.py`:

```python
"""
STORY-004 Gate Tests
File: tests/test_adhoc_coordinator.py
Owner: @member1
"""

import uuid
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.coordination.adhoc import AdHocCoordinator
from src.schemas.models import GraphOperation, CoordinationResult


def make_mock_client(rows=None):
    client = MagicMock()
    client.run = AsyncMock(return_value=rows or [])
    return client


def make_op(**kwargs):
    defaults = dict(
        operation_id=str(uuid.uuid4()), operation_type="MERGE_NODE",
        node_label="Malware", node_key="name", node_value="__test_adhoc__",
        claim_id="test", principal="Agent-Test",
    )
    defaults.update(kwargs)
    return GraphOperation(**defaults)


async def test_adhoc_returns_accepted():
    """Ad-Hoc coordinator must return status=ACCEPTED."""
    coord = AdHocCoordinator(make_mock_client())
    result = await coord.submit(make_op())
    assert result.status == "ACCEPTED"
    assert result.protocol == "AD_HOC"


async def test_adhoc_latency_is_positive():
    """Latency must be >= 0."""
    coord = AdHocCoordinator(make_mock_client())
    result = await coord.submit(make_op())
    assert result.latency_ms >= 0


async def test_adhoc_returns_coordination_result():
    """Result must be a CoordinationResult instance."""
    coord = AdHocCoordinator(make_mock_client())
    result = await coord.submit(make_op())
    assert isinstance(result, CoordinationResult)
    assert result.run_id
    assert result.agent_id == "Agent-Test"
```

**VERIFICATION CHECK P1-003**
```bash
grep -c "^async def test_" tests/test_adhoc_coordinator.py
```
Must show: `3`

---

## GATE — Run Story-004 Tests

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_adhoc_coordinator.py -v
```
Must show: `3 passed`

## Completion Checklist

- [ ] `src/coordination/base.py` imports OK
- [ ] `src/coordination/adhoc.py` imports OK
- [ ] `tests/test_adhoc_coordinator.py` has 3 tests
- [ ] GATE: `3 passed`

**STORY-004 DONE → Begin STORY-005 (Conflict Detector & Arbitration Engine)**
