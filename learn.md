# 📚 Project Learning Guide

---

## 1. Project Overview

The **multi‑agent Knowledge Graph** project implements a coordination framework for concurrent writes to a Neo4j graph database. It defines several *coordination protocols* (Ad‑Hoc, Arbiter, etc.) that handle conflict detection, arbitration, and distributed locking using Redis. The codebase is organized into a classic Python package layout under `src/` with supporting scripts, configuration, and extensive markdown documentation.

---

## 2. Directory Structure

```
.
├── .env                     # Environment variables (Neo4j URL, Redis URL, etc.)
├── .pytest_cache/          # PyTest cache (ignored by version control)
├── analysis/               # Placeholder for analysis artefacts
├── data/                   # Data ingestion / raw files (if any)
├── docker-compose.yml      # Docker services for Neo4j & Redis
├── exampleprd.md           # Example product requirements doc
├── exampletechspec.md       # Example technical specification doc
├── learning_strategy.md    # Example learning guide (now superseded by this file)
├── prd.md                  # Product requirements doc
├── pytest.ini              # PyTest configuration
├── requirements.txt         # Python dependencies
├── run_schema_init.py       # Initializes Neo4j schema on first run
├── schemas/                # Neo4j schema definition files (Cypher scripts)
├── sources/                # External source files (e.g., CSVs)
├── src/                    # **Core Python package**
│   ├── __init__.py
│   ├── coordination/       # Coordination protocols & utilities
│   │   ├── __init__.py
│   │   ├── adhoc.py        # Baseline “no‑coordination” protocol
│   │   ├── arbiter.py      # Conflict‑aware protocol (FCFS arbitration)
│   │   ├── arbitration_engine.py
│   │   ├── base.py         # Abstract base class for coordinators
│   │   ├── conflict_detector.py
│   │   └── lock_manager.py # Redis‑backed distributed lock manager
│   ├── db/                 # Database client wrapper for Neo4j
│   │   └── neo4j_client.py
│   ├── ontology/           # Ontology validation utilities
│   │   ├── __init__.py
│   │   └── validator.py
│   ├── schemas/            # Pydantic models used throughout the project
│   │   ├── __init__.py
│   │   └── models.py
│   └── utils/              # Miscellaneous helpers (time utilities, etc.)
│       ├── __init__.py
│       └── time.py
├── story-001.md            # Narrative/story documents (used by tests)
├── story-002.md
├── story-002b.md
├── story-003.md
├── story-004.md
├── story-005.md
├── sync_daily.py           # Cron‑like daily sync script
├── taskbreakdown.md        # High‑level task breakdown for the project
├── techspec.md             # Full technical specification
└── tests/                  # pytest test suite
```

---

## 3. Core Modules – Detailed Walk‑through

Below we provide **line‑by‑line explanations** for the most critical source files located in `src/coordination/`. These files implement the coordination protocols that the rest of the system relies on.

### 3.1 `src/coordination/base.py`

```python
"""
Base Coordinator Abstract Class
File: src/coordination/base.py
Story: STORY-004 (Task P1-001)

All three protocols implement this interface. Agents call submit() — the protocol handles the rest.
"""

from abc import ABC, abstractmethod
from src.schemas.models import GraphOperation, CoordinationResult


class BaseCoordinator(ABC):
    """Abstract base for all coordination protocols."""

    @abstractmethod
    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        """Process one agent graph‑write operation.

        Returns a ``CoordinationResult`` containing status, latency,
        and conflict information.
        """
        ...
```
**Explanation**:
1. Docstring links the file to its story and purpose.
2. Imports `ABC`/`abstractmethod` to define an abstract base class.
3. Imports the Pydantic models used for input (`GraphOperation`) and output (`CoordinationResult`).
4. Declares the single abstract coroutine `submit` that all concrete coordinators must implement.

---

### 3.2 `src/coordination/arbiter.py`

```python
"""
Arbiter Coordinator — Protocol 2 (Conflict‑Aware)
File: src/coordination/arbiter.py
Story: STORY-005 (Task ARB-001)

Wraps ConflictDetector + ArbitrationEngine + Neo4j writes.

submit() accepts a LIST of GraphOperation objects (batch submission).
  1. Detect conflicts.
  2. Arbitrate (FCFS — first op wins).
  3. Execute only ACCEPTED ops against Neo4j.
  4. Return a CoordinationResult summarising the round.

Status mapping:
  "success"  -> all ops accepted
  "partial"  -> some ops rejected
  "failure"  -> no ops accepted (or an error occurred)
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
    """Conflict‑aware coordinator implementing FCFS arbitration.

    Usage:
        coordinator = ArbiterCoordinator(neo4j_client)
        result = await coordinator.submit([op1, op2, op3])
    """

    def __init__(self, neo4j_client):
        self._client = neo4j_client
        self._detector = ConflictDetector()
        self._engine = ArbitrationEngine()

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
            decision = decisions[op.operation_id]
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
**Key points**:
- Imports and logger set‑up (lines 1‑19).
- Class definition with usage example (lines 33‑39).
- Constructor stores Neo4j client and helper components (lines 41‑45).
- `submit` normalises input, runs conflict detection, arbitration, and conditional Cypher execution.
- Builds a rich `CoordinationResult` containing telemetry.

---

### 3.3 `src/coordination/conflict_detector.py`

```python
"""
Conflict Detector
File: src/coordination/conflict_detector.py
Story: STORY-005 (Task CD-001)

Given a list of GraphOperation objects, finds pairs of operations that
conflict (share at least one lock_key). The caller (ArbiterCoordinator) uses this list to decide which operations to accept or reject.

Algorithm: O(N·K) — for each operation, check each of its lock_keys
against a running map of key-\>first_operation. If the key already exists,
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
        key_owner: dict = {}

        for op in operations:
            for key in op.lock_keys:
                if key in key_owner:
                    conflicts.append((key_owner[key], op))
                else:
                    key_owner[key] = op

        return conflicts
```
**Explanation**:
- Maintains a map `key_owner` of the first operation that claimed each lock key.
- Subsequent ops that reference the same key generate a conflict tuple.
- Returns all conflict pairs for the arbitration engine.

---

### 3.4 `src/coordination/arbitration_engine.py`

```python
"""
Arbitration Engine
File: src/coordination/arbitration_engine.py
Story: STORY-005 (Task AE-001)

Applies a First‑Come‑First‑Served (FCFS) policy to a list of conflict pairs
produced by ConflictDetector.

Policy rules:
  - The FIRST operation in each conflict pair is ALWAYS accepted.
  - Any operation that appears as the SECOND (loser) in any pair is rejected.
  - Operations not involved in any conflict are accepted by default.

NOTE: GraphOperation contains a list field (lock_keys) which makes it
unhashable, so we cannot use it directly as a dict key. We use operation_id
(a str) as the key in all internal bookkeeping.

Output: a dict mapping operation_id (str) -> ArbitrationDecision.
"""

from typing import Dict, List, Tuple
from src.schemas.models import ArbitrationDecision, GraphOperation


class ArbitrationEngine:
    """Applies FCFS arbitration to a list of conflict pairs."""

    def resolve(
        self,
        all_operations: List[GraphOperation],
        conflicts: List[Tuple[GraphOperation, GraphOperation]],
    ) -> Dict[str, ArbitrationDecision]:
        """Produce an ArbitrationDecision for every operation.

        Args:
            all_operations: The full list of GraphOperation objects (in submission order).
            conflicts:       Conflict pairs from ConflictDetector.detect().

        Returns:
            A dict mapping operation_id (str) -> ArbitrationDecision.
        """
        loser_ids: set = {loser.operation_id for _, loser in conflicts}

        decisions: Dict[str, ArbitrationDecision] = {}
        for op in all_operations:
            if op.operation_id in loser_ids:
                decisions[op.operation_id] = ArbitrationDecision(
                    decision="reject",
                    reason=(
                        f"Conflict detected on shared lock key(s); "
                        f"operation {op.operation_id} rejected by FCFS policy."
                    ),
                )
            else:
                decisions[op.operation_id] = ArbitrationDecision(
                    decision="accept", reason=None
                )

        return decisions
```
**Explanation**:
- Extracts loser IDs from conflict pairs.
- Assigns `accept` to all non‑losers, `reject` with a reason to losers.

---

### 3.5 `src/coordination/adhoc.py`

```python
"""
Protocol 1 — Ad‑Hoc Coordinator (Baseline / Worst Case)
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
    """Uncoordinated direct writer – baseline for performance tests.

    The coordinator receives a ``GraphOperation`` and issues a single MERGE
    statement to Neo4j. No lock acquisition, no conflict detection, no
    arbitration – just fire‑and‑forget.
    """

    def __init__(self, neo4j_client):
        self._client = neo4j_client

    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        start = time.monotonic()

        cypher = (
            f"MERGE (n:{operation.node_label} {{{operation.node_key}: $val}}) "
            f"SET n += $props "
            f"SET n.node_schema_version = '1.0' "
            f"SET n.last_writer = $principal "
            f"SET n.last_write_ts = timestamp()"
        )
        props = dict(operation.properties)
        props[operation.node_key] = operation.node_value

        await self._client.run(
            cypher,
            {
                "val": operation.node_value,
                "props": props,
                "principal": operation.principal,
            },
        )

        latency_ms = (time.monotonic() - start) * 1000
        return CoordinationResult(
            run_id=str(uuid.uuid4()),
            protocol="AD_HOC",
            ablation_mode="NONE",
            operation_id=operation.operation_id,
            status="ACCEPTED",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            latency_ms=latency_ms,
            agent_id=operation.principal,
        )
```
**Explanation**:
- Provides a *baseline* without any coordination, useful for measuring raw performance and demonstrating the problem of lost updates.
- Directly executes a MERGE Cypher and returns a simple `CoordinationResult`.

---

### 3.6 `src/coordination/lock_manager.py`

```python
"""
Redis Distributed Lock Manager
File: src/coordination/lock_manager.py
Story: STORY-003

Provides SemanticLockManager — acquires/releases Redis locks with:
  - Sorted multi‑key acquisition (deadlock prevention)
  - Atomic Lua‑based release (foreign token cannot steal lock)
  - asyncio.Lock fallback when USE_REDIS=false
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

class LockTimeoutError(Exception):
    """Raised when a lock cannot be acquired within timeout_ms."""

class SemanticLockManager:
    """Distributed lock manager using Redis SETNX + TTL.

    All lock_keys are always acquired in sorted lexicographical order
    to prevent deadlocks across concurrent agents.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_ms: int = 10_000,
        timeout_ms: int = 5_000,
        use_redis: Optional[bool] = None,
    ):
        from dotenv import load_dotenv
        load_dotenv()
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ttl_ms = ttl_ms
        self.timeout_ms = timeout_ms
        if use_redis is None:
            use_redis = os.getenv("USE_REDIS", "true").lower() != "false"
        self._use_redis = use_redis
        self._redis = None
        self._local_locks: Dict[str, asyncio.Lock] = {}

    async def connect(self) -> None:
        if self._use_redis:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("SemanticLockManager connected to Redis at %s", self.redis_url)
        else:
            logger.info("SemanticLockManager using asyncio.Lock fallback (USE_REDIS=false)")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def acquire(self, lock_keys: List[str]) -> Dict[str, str]:
        """Acquire locks for all keys in sorted order.
        Returns Dict[key → token]. Pass to release().
        Raises LockTimeoutError if any lock cannot be acquired.
        """
        sorted_keys = sorted(lock_keys)
        tokens: Dict[str, str] = {}
        deadline = time.monotonic() + self.timeout_ms / 1000.0
        for key in sorted_keys:
            token = str(uuid.uuid4())
            acquired = False
            while time.monotonic() < deadline:
                if self._use_redis and self._redis:
                    ok = await self._redis.set(
                        f"lock:{key}", token, px=self.ttl_ms, nx=True
                    )
                    if ok:
                        acquired = True
                        break
                else:
                    if key not in self._local_locks:
                        self._local_locks[key] = asyncio.Lock()
                    lock = self._local_locks[key]
                    try:
                        await asyncio.wait_for(lock.acquire(), timeout=0.05)
                        acquired = True
                        break
                    except asyncio.TimeoutError:
                        pass
                await asyncio.sleep(0.05)
            if not acquired:
                await self.release(tokens)
                raise LockTimeoutError(
                    f"Could not acquire lock for '{key}' within {self.timeout_ms}ms"
                )
            tokens[key] = token
        logger.debug("Acquired %d locks: %s", len(tokens), list(tokens.keys()))
        return tokens

    async def release(self, tokens: Dict[str, str]) -> None:
        """Release locks using token verification. Silent on already‑released locks."""
        for key, token in tokens.items():
            if self._use_redis and self._redis:
                result = await self._redis.eval(_RELEASE_SCRIPT, 1, f"lock:{key}", token)
                if result == 0:
                    logger.warning("Lock for '%s' was already released or stolen", key)
            else:
                lock = self._local_locks.get(key)
                if lock and lock.locked():
                    lock.release()
        logger.debug("Released %d locks", len(tokens))

    @asynccontextmanager
    async def locked(self, lock_keys: List[str]):
        """Async context manager: acquire → yield → release (always).
        Usage:
          async with lock_manager.locked(["key1", "key2"]):
              # safe work here
        """
        tokens = await self.acquire(lock_keys)
        try:
            yield tokens
        finally:
            await self.release(tokens)
```
**Explanation**:
- Implements a robust distributed lock manager with Redis fallback to in‑process `asyncio.Lock`.
- Sorted acquisition prevents deadlocks.
- Tokens ensure only the lock owner can release the lock (Lua script).
- Provides an ergonomic async context manager via `locked`.

---

## 4. Supporting Modules (high‑level description)

| Module | Purpose | Key Types |
|--------|---------|-----------|
| `src/db/neo4j_client.py` | Thin async wrapper around Neo4j driver used by coordinators. | `Neo4jClient` (connect, run, close) |
| `src/ontology/validator.py` | Validates incoming graph payloads against an ontology. | `OntologyValidator.validate` |
| `src/schemas/models.py` | Central **pydantic** models: `GraphOperation`, `CoordinationResult`, `ArbitrationDecision`, etc. |
| `src/utils/time.py` | Helper functions for timestamps and latency formatting. |
| `run_schema_init.py` | CLI script that reads Cypher files from `schemas/` and creates constraints/indexes on Neo4j. |
| `sync_daily.py` | Example scheduled job that pulls a daily feed and writes to the graph using a chosen coordinator. |
| `collect.py` | Entry‑point used by tests to generate synthetic `GraphOperation` objects and drive the coordination flow. |
| `docker-compose.yml` | Spins up Neo4j and Redis containers for local development. |
| Markdown documentation (`exampleprd.md`, `techspec.md`, `story‑*.md`, …) | Narrative, PRD, technical spec, and user stories that the code implements. |

---

## 5. Data Flow – From API Call to Neo4j Write

1. **Client** creates a `GraphOperation` (node label, key, value, properties, lock_keys, operation_id, principal).
2. **Coordinator** receives the operation via `submit`.
3. For **Arbiter**:
   - `ConflictDetector.detect` scans `lock_keys` → conflict pairs.
   - `ArbitrationEngine.resolve` marks losers as `reject`.
   - Accepted ops are turned into MERGE Cypher statements and executed via `Neo4jClient.run`.
4. **Lock Manager** (used by more advanced protocols) would be invoked **before** conflict detection to obtain a distributed lock on each `lock_key`.
5. Coordinator builds a `CoordinationResult` containing run ID, protocol, status, latency, attempts/committed counts, and conflict flag.
6. Result is returned to the caller (HTTP handler, test, or scheduled job).

---

## 6. How to Run the Project

```bash
# 1️⃣ Start supporting services
docker-compose up -d   # Neo4j + Redis

# 2️⃣ Install dependencies (virtualenv recommended)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3️⃣ Initialise Neo4j schema (run once)
python run_schema_init.py

# 4️⃣ Example interactive usage (Python REPL)
>>> from src.db.neo4j_client import Neo4jClient
>>> from src.coordination.adhoc import AdHocCoordinator
>>> client = Neo4jClient()
>>> await client.connect()
>>> coord = AdHocCoordinator(client)
>>> op = GraphOperation(
...     node_label="Person",
...     node_key="id",
...     node_value="123",
...     properties={"name": "Alice"},
...     lock_keys=["person:123"],
...     operation_id="op-1",
...     principal="tester",
... )
>>> result = await coord.submit(op)
>>> print(result)
```
Replace `AdHocCoordinator` with `ArbiterCoordinator` to see conflict‑aware behaviour.

---

## 7. Frequently Asked Questions (FAQ)

| Question | Answer |
|----------|--------|
| **What is a `GraphOperation`?** | A pydantic model describing a single graph mutation (node label, key, value, properties, lock keys, etc.). |
| **Why a lock manager?** | Guarantees serialisable writes when multiple agents modify overlapping graph parts. Uses Redis for distributed coordination. |
| **When to use the Ad‑Hoc protocol?** | Only for performance baselines or non‑critical workloads where lost updates are acceptable. |
| **How does conflict detection work?** | First operation to claim a `lock_key` becomes the owner; later operations that request the same key are paired as conflicts. |
| **Can I add a new protocol?** | Yes. Subclass `BaseCoordinator`, implement `submit`, and plug it into the factory that creates coordinators. |
| **Where are Neo4j constraints defined?** | In the `schemas/` directory as `.cyp` files; `run_schema_init.py` applies them. |
| **How is latency measured?** | Coordinators record `time.monotonic()` before and after the write phase; the difference (ms) is stored in `CoordinationResult.latency_ms`. |

---

## 8. Where to Find More Information

- **Story Documents** (`story‑*.md`) – concrete use‑case scenarios used by the test suite.
- **Technical Specification** (`techspec.md`) – deeper architectural rationale.
- **Product Requirements** (`prd.md`, `exampleprd.md`) – high‑level goals.
- **Learning Strategy** (`learning_strategy.md`) – the original guide that this file supersedes.

---

*End of `learn.md`*
