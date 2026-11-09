# ProGRESS: Provenance-Grounded Multi-Agent Knowledge Graph — Task Breakdown

**Epic ID:** EPIC-PROGRESS-01  
**Epic Description:** Build a multi-agent, provenance-aware Cyber Threat Intelligence (CTI) Knowledge Graph system using Neo4j, FastAPI, LangGraph, MCP, and A2A peer protocols. Evaluate three coordination protocols (Ad-Hoc, MPAC, MPAC-Ablation) against each other using authentic real-world CTI data.

| Field | Details |
|---|---|
| Related PRD | [prd.md](file:///Users/sohithsai/multiagent_knowledgegraph/prd.md) |
| Related TechSpec | [techspec.md](file:///Users/sohithsai/multiagent_knowledgegraph/techspec.md) |
| Total Story Points | **94 points** |
| Total Sprints | **5 Sprints** |
| Team Members | **@member1 (Lead — ~55% workload)**, **@member2 (Support — ~45% workload)** |
| Phase 1 Status | ✅ **COMPLETED & VERIFIED** (16,270 records, 259 overlaps, 63 conflicts) |
| Current Phase | Phase 2 — Neo4j Schema & CoordinationAdapter Engine |

> **Status note (2026-11-04):** This breakdown is a historical plan; its story/status checkboxes and dataset counts are not synchronized with the current workspace. STORY-012 (`story-012-dynamic-agent-runtime.md`) records the current corrective implementation work, and [RUNTIME.md](RUNTIME.md) is the current run/verification guide.

---

> **MANDATORY RULE — Sequential Testing Gates:**  
> No story can begin until the story it depends on has passed ALL its unit tests. Every story ends with a `pytest` run. The `⛔ GATE` label marks these mandatory checkpoint tests. Skipping a gate is not allowed.

---

## Team Responsibility Matrix

| Member | Role | Primary Domain | Est. Total Hours |
|---|---|---|---|
| **@member1** | Lead Engineer | Infrastructure, Coordination Protocols, Agent Workflows, Benchmarking | ~60 hours |
| **@member2** | Support Engineer | Pydantic Models, Ontology Registry/Validator, Conflict/Arbitration Logic, FastAPI Endpoints, GraphRAG | ~66 hours |

---

## EPIC Stories Overview

| Story | Title | Sprint | Points | Lead | Support | Status |
|---|---|---|---|---|---|---|
| **STORY-001** | Neo4j Docker Setup & Schema Initialization | Sprint 1 | 5 | @member1 | @member2 | ⚪ Not Started |
| **STORY-002** | Core Pydantic Data Contracts & Utilities | Sprint 1 | 5 | @member2 | @member1 | ⚪ Not Started |
| **STORY-002B** | Two-Tier Ontology Registry & Validator | Sprint 1 | 5 | @member2 | @member1 | ⚪ Not Started |
| **STORY-003** | Redis Distributed Lock Manager | Sprint 1 | 8 | @member1 | — | ⚪ Not Started |
| **STORY-004** | Protocol 1 — Ad-Hoc Coordinator (Baseline) | Sprint 2 | 5 | @member1 | @member2 | ⚪ Not Started |
| **STORY-005** | Conflict Detector & Arbitration Engine | Sprint 2 | 8 | @member2 | @member1 | ⚪ Not Started |
| **STORY-006** | Protocol 2 — Full MPAC Coordinator | Sprint 2 | 8 | @member1 | @member2 | ⚪ Not Started |
| **STORY-007** | Protocol 3 — MPAC Ablation Coordinator | Sprint 2 | 5 | @member1 | — | ⚪ Not Started |
| **STORY-008** | MCP Tool Adapters (4 Sources) | Sprint 3 | 8 | @member2 | @member1 | ⚪ Not Started |
| **STORY-009** | G²CP Agent-to-Agent (A2A) Peer Hub | Sprint 3 | 8 | @member1 | @member2 | ⚪ Not Started |
| **STORY-010** | LangGraph Agent State Machine | Sprint 3 | 8 | @member1 | @member2 | ⚪ Not Started |
| **STORY-011** | FastAPI REST Gateway | Sprint 4 | 8 | @member2 | @member1 | ⚪ Not Started |
| **STORY-012** | GraphRAG Retriever & Evidence Synthesizer | Sprint 4 | 5 | @member2 | — | ⚪ Not Started |
| **STORY-013** | Benchmark Harness & Metric Evaluation Suite | Sprint 5 | 8 | @member1 | @member2 | ⚪ Not Started |
| **STORY-014** | Results Analysis, Visualization & Research Report | Sprint 5 | 5 | @member2 | @member1 | ⚪ Not Started |
| **TOTAL** | | **5 Sprints** | **94** | | | |

---

## Phase 1: COMPLETED — No Work Needed

All Phase 1 files are already built, tested, and verified. Do NOT modify them.

| File | What it Does | Status |
|---|---|---|
| `sources/threatfox.py` | Fetches & normalizes ThreatFox live feed (3,000 records) | ✅ Done |
| `sources/urlhaus.py` | Fetches & normalizes URLhaus live feed (10,000 records) | ✅ Done |
| `sources/malwarebazaar.py` | Fetches & normalizes MalwareBazaar CSV (1,536 records) | ✅ Done |
| `sources/otx.py` | Fetches & normalizes AlienVault OTX pulses (1,734 records) | ✅ Done |
| `schemas/cti.py` | `NormalizedCTIRecord` Pydantic schema | ✅ Done |
| `analysis/overlap.py` | Detects 259 cross-source IOC overlaps | ✅ Done |
| `analysis/conflict.py` | Detects 63 attribution/confidence conflicts | ✅ Done |
| `collect.py` | High-volume ingestion orchestrator | ✅ Done |
| `sync_daily.py` | Incremental daily deduplicating sync | ✅ Done |
| `tests/test_data_pipeline.py` | Phase 1 unit tests | ✅ 2/2 PASS |

**Verification command (run before starting Sprint 1):**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# Expected: 2 passed in < 1s
```

---

## Sprint 1: Infrastructure Foundation
**Sprint Goal:** Establish the database, data contracts, the Two-Tier Ontology Registry, and distributed locking infrastructure.  
**Sprint Points:** 23 points  
**Parallelism:** STORY-001 and STORY-002 run in parallel. STORY-002B starts after STORY-002 Gate passes. STORY-003 starts after STORY-001 Gate passes.

---

### STORY-001: Neo4j Docker Setup & Schema Initialization
**Story ID:** STORY-001 | **Points:** 5 | **Sprint:** 1 | **Lead:** @member1 | **Support:** @member2

**User Story:** As an engineer, I need Neo4j running locally with all graph constraints and indexes so agents can safely write to a validated, deduplicated graph.

**Acceptance Criteria:**
- [ ] Neo4j 5.20 container running on `localhost:7687` and `localhost:7474`
- [ ] Python async driver connects and verifies connection
- [ ] All **14** unique constraints applied: all 8 Tier 1 entity types (incl. `ThreatActor` and `Campaign`) + all provenance/governance types + `OntologyTerm` (TechSpec §3.2)
- [ ] `initialize_schema()` is idempotent (safe to run twice without errors)
- [ ] `run()` method is documented as internal-only infrastructure; agents must go through coordinator services, not call `run()` directly

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| INF-001 | Pull Neo4j 5.20 Docker image; write `docker-compose.yml` (includes Redis 7.2) | @member1 | 1h | ⚪ | None | TechSpec §8 Step 1 | `docker-compose up -d` starts Neo4j + Redis; Browser at `localhost:7474`; `redis-cli ping` returns PONG |
| INF-002 | Install all new dependencies; update `requirements.txt` (`neo4j`, `redis`, `langchain`, `langgraph`, `fastapi`, `uvicorn`, `matplotlib`, `sentence-transformers`) | @member1 | 1h | ⚪ | None | TechSpec §9.1 | `pip install -r requirements.txt` completes without conflicts |
| INF-003 | Create `src/db/neo4j_client.py` with async connection pool and `run()` method | @member1 | 2h | ⚪ | INF-001 | TechSpec §8 Step 1 | `Neo4jClient.connect()` succeeds; pool verified |
| INF-004 | Implement `initialize_schema()` — 14 constraints (all 8 Tier 1 + provenance + OntologyTerm) + 3 indexes | @member1 | 1h | ⚪ | INF-003 | TechSpec §3.2 | All 14 constraints + 3 indexes created; idempotent (runs twice without error) |
| INF-005 | Write `tests/test_neo4j_client.py` — verify connection, all 14 constraints, 3 indexes, uniqueness enforcement | @member2 | 1h | ⚪ | INF-004 | TechSpec §3.2 | 5 tests pass: connection, idempotency, constraint count, index count, uniqueness blocked |

**⛔ GATE — STORY-001:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_neo4j_client.py -v
# ALL PASS required before STORY-003 begins
```

**Risks:**
- ⚠️ Port conflict on 7687 if local Neo4j already installed. Run `lsof -i :7687` first.
- ⚠️ Python driver version mismatch. Pin `neo4j>=5.18.0` in requirements.
- ⚠️ `run()` must not be exposed to agents directly. Ensure all coordinators (STORY-004, 006) are the only entry point for agent-initiated graph writes.

---

### STORY-002: Core Pydantic Data Contracts & Utilities
**Story ID:** STORY-002 | **Points:** 5 | **Sprint:** 1 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an engineer, I need all shared Pydantic models and utility functions so every component speaks the same language with validated data structures.

**Acceptance Criteria:**
- [ ] 5 Pydantic models defined: `Claim`, `GraphOperation`, `ArbitrationDecision`, `CoordinationResult`, `A2AQuery`
- [ ] `Claim.generate_id()` includes `evidence_id` + `timestamp_iso` — collision-proof
- [ ] `GraphOperation.enforce_deterministic_lock_sorting()` sorts `lock_keys` lexicographically
- [ ] Timestamp normalizer parses all 4 feed formats into ISO-8601 UTC and Unix epoch

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| MDL-001 | Create `src/schemas/models.py` with `Claim` model and `generate_id()` SHA-256 hash | @member2 | 2h | ⚪ | None | TechSpec §3.3 | Same IOC at different timestamps produces different IDs |
| MDL-002 | Add `GraphOperation` with `@field_validator('lock_keys')` sorting | @member2 | 1h | ⚪ | MDL-001 | TechSpec §3.3 | Unsorted keys returned sorted; empty list raises `ValueError` |
| MDL-003 | Add `ArbitrationDecision`, `CoordinationResult`, `A2AQuery`, `A2AResponse` models | @member2 | 1h | ⚪ | MDL-001 | TechSpec §3.3 | All models importable and instantiable |
| MDL-004 | Create `src/utils/time.py` — heterogeneous timestamp normalizer | @member2 | 2h | ⚪ | None | TechSpec Key Finding 1 | Parses ThreatFox, URLhaus (UTC suffix), OTX ISO-8601T, Bazaar formats |
| MDL-005 | Write `tests/test_models.py` — hash collisions, lock sorting, timestamp edge cases | @member1 | 2h | ⚪ | MDL-004 | TechSpec §3.3 | All edge cases pass with 100% coverage |

**⛔ GATE — STORY-002:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py -v
# ALL PASS required before STORY-004, STORY-005, STORY-008, STORY-011 begin
```

**Note:** Runs fully in parallel with STORY-001.

---

### STORY-002B: Two-Tier Ontology Registry & Validator
**Story ID:** STORY-002B | **Points:** 5 | **Sprint:** 1 | **Lead:** @member2 | **Support:** @member1

**User Story:** As the multi-agent system, I need an Ontology Registry and Validator so that when agents encounter a new entity type not covered by the Tier 1 fixed schema, those types are safely governed, deduplicated, and approved by multi-agent consensus — preventing both schema rigidity and ontology fragmentation.

**Why This Story Exists:**
The Tier 1 schema covers 8 fixed node types (Malware, IP, Domain, URL, FileHash, ThreatActor, Campaign, AttackTechnique). When CTI evolves — e.g. ransomware using BTC wallets, cloud S3 dropper buckets, or Telegram C2 channels — agents need a governed pathway to extend the schema. Without this, the LLM will invent inconsistent relationship names, creating fragmented, unqueryable graph data. See TechSpec §3.4 for full architecture.

**Acceptance Criteria:**
- [ ] `OntologyValidator.validate()` returns MERGE for any Tier 1 exact match
- [ ] Semantic similarity check returns MERGE for cosine score >= 0.85 against any Tier 1 anchor type
- [ ] Two or more agent confirmations results in APPROVE + writes `(:OntologyTerm {status: "APPROVED"})` to Neo4j
- [ ] Fewer than 2 confirmations results in REJECT + audit `(:OntologyTerm {status: "REJECTED"})` log entry
- [ ] `OntologyTerm` uniqueness constraint (from STORY-001) enforces no duplicate term registrations
- [ ] All Tier 1 node creation paths stamp `node_schema_version="1.0"` on every node
- [ ] All Tier 1 relationship creation paths stamp `relationship_schema_version="1.0"` on every edge

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|---------------------|
| ONT-001 | Create `src/ontology/__init__.py` and `src/ontology/validator.py` — `OntologyValidator` skeleton with Tier 1 constant sets | @member2 | 1h | ⚪ | STORY-002 Gate | TechSpec §3.4 | File importable; `TIER1_NODE_TYPES` and `TIER1_RELATIONSHIP_TYPES` frozensets defined |
| ONT-002 | Implement `validate()` Step 1: exact Tier 1 match → MERGE | @member2 | 1h | ⚪ | ONT-001 | TechSpec §3.4 | Any exact Tier 1 type returns `OntologyDecision.MERGE` with `similarity_score=1.0` |
| ONT-003 | Implement `validate()` Step 2: semantic similarity using `sentence-transformers all-MiniLM-L6-v2` | @member2 | 2h | ⚪ | ONT-002 | TechSpec §3.4 | Score >= 0.85 returns MERGE with `target_type=nearest_tier1_type`; mock in tests |
| ONT-004 | Implement `validate()` Step 3: multi-agent approval (>=2 confirmations) → APPROVE + write OntologyTerm node | @member2 | 1h | ⚪ | ONT-003 | TechSpec §3.4 | APPROVED OntologyTerm written to Neo4j with `schema_version_assigned="2.0"` |
| ONT-005 | Implement `validate()` Step 4: reject path — write REJECTED OntologyTerm as audit log | @member2 | 30m | ⚪ | ONT-004 | TechSpec §3.4 | Rejected terms persisted; no domain node created |
| ONT-006 | Update `src/db/neo4j_client.py` Tier 1 MERGE statements to stamp `node_schema_version="1.0"` | @member1 | 1h | ⚪ | ONT-001 | TechSpec §3.1 | All 8 Tier 1 node types carry `node_schema_version` property after MERGE |
| ONT-007 | Update `src/db/neo4j_client.py` Tier 1 relationship creation to stamp `relationship_schema_version="1.0"` | @member1 | 30m | ⚪ | ONT-006 | TechSpec §3.1 | All Tier 1 relationship types carry `relationship_schema_version` property |
| ONT-008 | Write `tests/test_ontology_validator.py` — exact match MERGE, similarity MERGE, APPROVE (2 confirmations), REJECT (1 confirmation) | @member1 | 2h | ⚪ | ONT-005 | TechSpec §3.4 | All 4 decision paths pass; OntologyTerm node correctly written/not-written per decision |

**⛔ GATE — STORY-002B:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_ontology_validator.py -v
# ALL PASS required before Sprint 3 begins (validator is wired into STORY-010)
```

**Blocked by:** STORY-002 Gate (Pydantic models needed for `OntologyValidationResult` dataclass)

**Risks:**
- `sentence-transformers` adds ~400 MB. Use `all-MiniLM-L6-v2` (80 MB) for dev. Mock `_compute_nearest_similarity` in unit tests to avoid model download in CI.
- Similarity threshold of 0.85 is calibrated for CTI domain vocabulary. Tune if false-MERGE rate exceeds 5% on test cases.

**Note:** The validator is **built and tested standalone** in Sprint 1. It is **wired into the agent workflow** (Extract Claim node) in STORY-010 during Sprint 3.

---

### STORY-003: Redis Distributed Lock Manager
**Story ID:** STORY-003 | **Points:** 8 | **Sprint:** 1 | **Lead:** @member1 | **Support:** —

**User Story:** As the coordination engine, I need a Redis-backed distributed lock manager so multiple agent processes cannot simultaneously mutate the same entity node.

**Acceptance Criteria:**
- [ ] `SemanticLockManager` acquires Redis locks using `SETNX` + TTL (Redlock pattern)
- [ ] `acquire(keys, timeout_ms=5000)` always acquires in sorted lexicographical order
- [ ] `release(token)` uses atomic Lua script — foreign token cannot release lock
- [ ] Falls back to in-memory `asyncio.Lock` when `USE_REDIS=false`
- [ ] Lock timeout raises `LockTimeoutError` after specified ms

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| LCK-001 | Add Redis to `docker-compose.yml` | @member1 | 30m | ⚪ | INF-001 | TechSpec §8 Step 2 | `redis-cli ping` returns PONG |
| LCK-002 | Create `src/coordination/lock_manager.py` with `SemanticLockManager` skeleton | @member1 | 3h | ⚪ | LCK-001 | TechSpec §8 Step 2 | Class instantiates with Redis or fallback |
| LCK-003 | Implement `acquire()` with sorted multi-key acquisition and TTL | @member1 | 2h | ⚪ | LCK-002 | TechSpec §5.2 | Keys always acquired alphabetically; TTL set on Redis |
| LCK-004 | Implement `release()` with atomic Lua token verification | @member1 | 1h | ⚪ | LCK-003 | TechSpec §5.2 | Foreign token cannot release another agent's lock |
| LCK-005 | Implement `asyncio.Lock` in-memory fallback | @member1 | 1h | ⚪ | LCK-002 | TechSpec §8 Step 2 | Tests run without Redis using `USE_REDIS=false` |
| LCK-006 | Write `tests/test_lock_manager.py` — concurrency, timeout, deadlock prevention | @member1 | 2h | ⚪ | LCK-004 | TechSpec §8 Step 2 | Concurrent tasks serialized; timeout errors; deadlock test passes |

**⛔ GATE — STORY-003:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_lock_manager.py -v
# ALL PASS required before STORY-006 begins
```

**Blocked by:** STORY-001 Gate (Docker setup confirmed)

---

### Sprint 1 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# ALL tests must pass before any Sprint 2 story begins
# (test_data_pipeline + test_neo4j_client + test_models + test_ontology_validator + test_lock_manager)
```

---

## Sprint 2: Coordination Protocol Engine
**Sprint Goal:** Build all three coordination protocols — the core intellectual contribution.  
**Sprint Points:** 26 points  
**Prerequisite:** STORY-002B (Ontology Validator) must be complete before Sprint 3, as the validator is wired into STORY-010.  
**Build Order:** STORY-004 → STORY-005 → STORY-006 → STORY-007 (strictly sequential)

---

### STORY-004: Protocol 1 — Ad-Hoc Coordinator (Baseline)
**Story ID:** STORY-004 | **Points:** 5 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the benchmark system, I need the Ad-Hoc Coordinator to establish the control baseline — direct uncoordinated writes that intentionally produce corruption as measurable worst-case.

**Acceptance Criteria:**
- [ ] Writes directly to Neo4j without acquiring any locks
- [ ] No intent registration, no conflict detection — parallel uncoordinated
- [ ] Returns `CoordinationResult` with `protocol="AD_HOC"` and accurate `latency_ms`
- [ ] Concurrent conflicting writes produce observable data corruption (confirmed by test)

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| P1-001 | Create `src/coordination/base.py` — `BaseCoordinator` abstract class | @member2 | 1h | ⚪ | Sprint 1 Gate | TechSpec §5 | Abstract `submit(operation)` method defined |
| P1-002 | Implement `src/coordination/adhoc.py` — direct Cypher MERGE without locking | @member1 | 2h | ⚪ | P1-001 | TechSpec §5.1 | Writes domain triple without coordination |
| P1-003 | Write `tests/test_adhoc_coordinator.py` — write test + corruption demonstration | @member1 | 2h | ⚪ | P1-002 | TechSpec §5.1 | Concurrent conflicting writes confirm LWW overwrite (GIR < 100%) |

**⛔ GATE — STORY-004:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_adhoc_coordinator.py -v
# ALL PASS required before STORY-005 begins
```

**Blocked by:** Sprint 1 Full Gate

---

### STORY-005: Conflict Detector & Arbitration Engine
**Story ID:** STORY-005 | **Points:** 8 | **Sprint:** 2 | **Lead:** @member2 | **Support:** @member1

**User Story:** As the MPAC engine, I need a conflict detector and mathematical arbitration engine so the knowledge graph reaches a consistent, authoritative state.

**Acceptance Criteria:**
- [ ] `ConflictDetector.check()` identifies Attribution Conflicts and Temporal Churn (>30 days)
- [ ] `ArbitrationEngine.resolve()` applies: `Score = 0.40·Auth + 0.35·(Conf/100) + 0.25·Consensus`
- [ ] Consensus vote normalized to [0, 1] range
- [ ] EMA authority update: `Auth_t = (1-0.05)·Auth_{t-1} + 0.05·R_batch`
- [ ] Temporal churn: `|t_new - t_existing| > 30 days` → `INFRASTRUCTURE_REASSIGNED`
- [ ] Correctly selects winner from 63 verified conflict cases

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| CD-001 | Create `src/coordination/detector.py` — `ConflictDetector` class | @member2 | 3h | ⚪ | STORY-004 Gate | TechSpec §5.2 Step 4 | Returns `ConflictEvaluationResult` with `has_conflict`, `is_churn`, `existing_claim` |
| CD-002 | Implement 30-day temporal churn threshold | @member2 | 1h | ⚪ | CD-001 | TechSpec §5.2 | `is_churn=True` for >30 days; `is_active_conflict=True` for ≤30 days |
| CD-003 | Create `src/coordination/arbitrator.py` — `ArbitrationEngine` class | @member2 | 2h | ⚪ | CD-001 | TechSpec §5.2 Step 5 | `resolve()` returns `ArbitrationDecision` with correct winner and scores |
| CD-004 | Implement weighted formula with EMA authority update | @member2 | 1h | ⚪ | CD-003 | TechSpec §5.2 | Scores bounded [0.0, 1.0]; EMA updates principal weight after each batch |
| CD-005 | Write `tests/test_conflict_detector.py` — attribution conflict, churn, clean overlap | @member1 | 2h | ⚪ | CD-002 | TechSpec §5.2 | All 3 scenarios pass |
| CD-006 | Write `tests/test_arbitration_engine.py` — equal score tiebreak, abstain, EMA | @member1 | 2h | ⚪ | CD-004 | TechSpec §5.2 | Edge cases: equal score, all-abstain peers, authority boundary tests pass |

**⛔ GATE — STORY-005:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_conflict_detector.py tests/test_arbitration_engine.py -v
# ALL PASS required before STORY-006 begins
```

**Blocked by:** STORY-004 Gate

---

### STORY-006: Protocol 2 — Full MPAC Coordinator
**Story ID:** STORY-006 | **Points:** 8 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the multi-agent system, I need the Full MPAC Coordinator to execute the complete 7-step coordination lifecycle: session management, distributed locking, conflict detection, arbitration, atomic provenance write, and lock release.

**Acceptance Criteria:**
- [ ] All 7 MPAC steps execute in strict sequence
- [ ] Single atomic Neo4j transaction commits Claim + Evidence + Conflict + Decision when conflict exists
- [ ] Provenance (Claim + Evidence) always committed — even with no conflict
- [ ] Lock ALWAYS released in `finally` block — even on exception
- [ ] `status="ACCEPTED"` for clean writes; `status="RESOLVED"` for arbitrated conflicts

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| P2-001 | Create `src/coordination/mpac.py` — `MPACCoordinator` skeleton with session lifecycle | @member1 | 2h | ⚪ | STORY-005 Gate | TechSpec §5.2 | Session opens/closes correctly around each transaction |
| P2-002 | Wire `SemanticLockManager` into `submit()` with sorted key acquisition | @member1 | 1h | ⚪ | P2-001 | TechSpec §5.2 Step 3 | Lock acquired before Neo4j query; keys are sorted |
| P2-003 | Wire `ConflictDetector` and `ArbitrationEngine` into `submit()` | @member1 | 2h | ⚪ | P2-002 | TechSpec §5.2 Steps 4-5 | Detector runs on locked entity; arbitrator invoked only on active conflict |
| P2-004 | Implement `_write_with_provenance()` — atomic Neo4j transaction | @member2 | 3h | ⚪ | P2-003 | TechSpec §5.2 Step 6 | Single transaction writes domain nodes + Claim + Evidence + Conflict + Decision |
| P2-005 | Write `tests/test_mpac_coordinator.py` — clean write, conflict write, exception recovery | @member1 | 2h | ⚪ | P2-004 | TechSpec §5.2 | 3 scenarios: ACCEPTED, RESOLVED, exception still releases lock |

**⛔ GATE — STORY-006:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_mpac_coordinator.py -v
# ALL PASS required before STORY-007 begins
```

**Blocked by:** STORY-005 Gate AND STORY-003 Gate

---

### STORY-007: Protocol 3 — MPAC Ablation Coordinator
**Story ID:** STORY-007 | **Points:** 5 | **Sprint:** 2 | **Lead:** @member1 | **Support:** —

**User Story:** As the research benchmark, I need the Ablation Coordinator to run three controlled variants with one mechanism disabled each, to scientifically isolate which mechanism causes the improvement.

**Acceptance Criteria:**
- [ ] Mode A (`NO_A2A`): γ=0.0 in arbitration; all other steps unchanged
- [ ] Mode B (`NO_SEMANTIC_LOCKS`): lock acquisition skipped; conflicts detected post-hoc
- [ ] Mode C (`TIMESTAMP_ORDERED`): arbitration replaced by earliest-timestamp-wins
- [ ] Mode selectable via `ablation_mode: str` parameter
- [ ] `CoordinationResult` includes `ablation_mode` for benchmark tracking

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| P3-001 | Create `src/coordination/ablation.py` inheriting `MPACCoordinator` | @member1 | 1h | ⚪ | STORY-006 Gate | TechSpec §5.3 | Subclass overrides only the targeted method per mode |
| P3-002 | Implement Mode A (`NO_A2A`) — γ=0.0 | @member1 | 1h | ⚪ | P3-001 | TechSpec §5.3 | Peer vote excluded from score; all other steps identical |
| P3-003 | Implement Mode B (`NO_SEMANTIC_LOCKS`) — skip lock entirely | @member1 | 1h | ⚪ | P3-001 | TechSpec §5.3 | No Redis call; race conditions reintroduced |
| P3-004 | Implement Mode C (`TIMESTAMP_ORDERED`) — earliest timestamp wins | @member1 | 1h | ⚪ | P3-001 | TechSpec §5.3 | Claim with smallest `timestamp_epoch` wins; no authority formula |
| P3-005 | Write `tests/test_ablation_coordinator.py` — one test per mode | @member1 | 2h | ⚪ | P3-004 | TechSpec §5.3 | Each mode produces distinct measurably different behavior |

**⛔ GATE — STORY-007:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_ablation_coordinator.py -v
# ALL PASS required before Sprint 3 begins
```

**Blocked by:** STORY-006 Gate

---

### Sprint 2 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# ALL tests must pass before any Sprint 3 story begins
```

---

## Sprint 3: Multi-Agent Workflow Layer
**Sprint Goal:** Wire 4 principal agents to the coordination engine via MCP and A2A.  
**Sprint Points:** 24 points  
**Build Order:** STORY-008 → STORY-009 → STORY-010 (strictly sequential)

---

### STORY-008: MCP Tool Adapters (4 Sources)
**Story ID:** STORY-008 | **Points:** 8 | **Sprint:** 3 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an agent, I need MCP tool adapters for each data source to retrieve IOC evidence in a standardized format.

**Acceptance Criteria:**
- [ ] 4 MCP tools: `ThreatFoxMCPTool`, `URLhausMCPTool`, `MalwareBazaarMCPTool`, `OTXMCPTool`
- [ ] Each tool operates in offline mode against pre-saved normalized JSON files
- [ ] Each tool returns ONLY its own source's records (principal isolation)
- [ ] Returns empty list (not error) for unknown IOCs

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| MCP-001 | Create `src/mcp/base_tool.py` — abstract `BaseMCPTool` with `invoke()` | @member2 | 1h | ⚪ | Sprint 2 Gate | TechSpec Phase 3 | Abstract class defined; returns `MCPResponse` typed object |
| MCP-002 | Implement `ThreatFoxMCPTool` against `data/normalized/threatfox.json` | @member2 | 1h | ⚪ | MCP-001 | TechSpec Phase 3 | Returns matching records for given IOC; no cross-source leakage |
| MCP-003 | Implement `URLhausMCPTool` against `data/normalized/urlhaus.json` | @member2 | 1h | ⚪ | MCP-001 | TechSpec Phase 3 | Returns matching records from URLhaus only |
| MCP-004 | Implement `MalwareBazaarMCPTool` against `data/normalized/malwarebazaar.json` | @member2 | 1h | ⚪ | MCP-001 | TechSpec Phase 3 | Returns matching records from Bazaar only |
| MCP-005 | Implement `OTXMCPTool` against `data/normalized/otx.json` | @member2 | 1h | ⚪ | MCP-001 | TechSpec Phase 3 | Returns matching records from OTX only |
| MCP-006 | Create `src/mcp/tools.py` — dict keyed by principal ID | @member2 | 30m | ⚪ | MCP-005 | TechSpec Phase 3 | `MCP_TOOLS["Principal-ThreatFox"]` returns correct tool |
| MCP-007 | Write `tests/test_mcp_tools.py` — known IOC, unknown IOC, cross-source isolation | @member1 | 2h | ⚪ | MCP-006 | TechSpec Phase 3 | Known found; unknown returns []; isolation confirmed |

**⛔ GATE — STORY-008:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_tools.py -v
# ALL PASS required before STORY-009 begins
```

**Blocked by:** Sprint 2 Full Gate

---

### STORY-009: G²CP Agent-to-Agent (A2A) Peer Hub
**Story ID:** STORY-009 | **Points:** 8 | **Sprint:** 3 | **Lead:** @member1 | **Support:** @member2

**User Story:** As an agent, I need to query peer agents for corroborating evidence about an IOC before submitting my claim so the consensus vote is based on verifiable evidence.

**Acceptance Criteria:**
- [ ] `query_peers(ioc_value, requesting_agent_id)` broadcasts to all other agents (not self)
- [ ] Each peer returns `A2AResponse` with evidence and `vote` (CONFIRM / CONTRADICT / ABSTAIN)
- [ ] Peer response timeout: 350 ms maximum — exceeded peers return `vote=ABSTAIN`
- [ ] `consensus_score` normalized to [0, 1] using: `(V_support - V_contradict + N_peers) / (2 * N_peers)`
- [ ] Non-blocking — unresponsive peer does not stall the requesting agent

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| A2A-001 | Create `src/agents/a2a.py` — `G2CPPeerHub` with agent registry | @member1 | 2h | ⚪ | STORY-008 Gate | TechSpec §2.2 | Hub registers all 4 tools; dispatches to N-1 peers |
| A2A-002 | Implement `query_peers()` with `asyncio.wait_for()` and 350 ms timeout | @member1 | 2h | ⚪ | A2A-001 | TechSpec G²CP | Concurrent peer queries; timeout returns ABSTAIN gracefully |
| A2A-003 | Implement vote logic (CONFIRM / CONTRADICT / ABSTAIN) | @member2 | 1h | ⚪ | A2A-001 | TechSpec §5.2 | Vote assigned based on peer evidence vs. claim malware family |
| A2A-004 | Implement `consensus_score` normalizer | @member2 | 1h | ⚪ | A2A-003 | TechSpec §5.2 Formula | Output bounded [0, 1] |
| A2A-005 | Write `tests/test_a2a_hub.py` — full consensus, all-abstain, split-vote, timeout | @member1 | 2h | ⚪ | A2A-004 | TechSpec §5.2 | All 4 scenarios pass |

**⛔ GATE — STORY-009:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_hub.py -v
# ALL PASS required before STORY-010 begins
```

**Blocked by:** STORY-008 Gate

---

### STORY-010: LangGraph Agent State Machine
**Story ID:** STORY-010 | **Points:** 8 | **Sprint:** 3 | **Lead:** @member1 | **Support:** @member2

**User Story:** As a principal-bound agent, I need a 5-step LangGraph state machine to govern my complete loop so behavior is reproducible and observable.

**Acceptance Criteria:**
- [ ] All 4 principal agents use the same state machine with different MCP tool configurations
- [ ] 5 nodes: `Receive` → `Fetch Evidence (MCP)` → `Extract Claim` → `A2A Peer Check` → `Submit to Coordinator`
- [ ] `Claim.generate_id()` called with all 6 hash inputs in `Extract Claim` node
- [ ] Agent selects coordinator based on `protocol` flag
- [ ] End-to-end test: 10 conflict IOCs through all 4 agents simultaneously under MPAC

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| AG-001 | Create `src/agents/state.py` — `AgentState` TypedDict | @member2 | 1h | ⚪ | STORY-009 Gate | TechSpec §8 Step 6 | Fields: `task_package`, `evidence`, `claim`, `peer_votes`, `result` |
| AG-002 | Create `src/agents/workflow.py` — LangGraph `StateGraph` with 5 nodes | @member1 | 3h | ⚪ | AG-001 | TechSpec §8 Step 6 | Graph compiles and runs 5-step flow without errors |
| AG-003 | Implement `Fetch Evidence` node — calls principal's MCP tool | @member1 | 1h | ⚪ | AG-002 | TechSpec §8 Step 6 | Returns `MCPResponse` in `AgentState.evidence` |
| AG-004 | Implement `Extract Claim` node — calls `OntologyValidator`, then builds `GraphOperation` with sorted keys | @member2 | 2h | ⚪ | AG-002 | TechSpec §3.3 + §3.4 | `OntologyValidator.validate()` called first; MERGE/APPROVE continues; REJECT drops claim; `Claim.generate_id()` called with all 6 inputs |
| AG-005 | Implement `A2A Peer Check` node — calls `G2CPPeerHub.query_peers()` | @member1 | 1h | ⚪ | AG-002 | TechSpec §5.2 | Consensus votes attached to `GraphOperation.peer_consensus_votes` |
| AG-006 | Implement `Submit to Coordinator` node — dispatches to protocol | @member1 | 1h | ⚪ | AG-002 | TechSpec §8 Step 6 | Correct coordinator called; `CoordinationResult` returned |
| AG-007 | Write `tests/test_agent_workflow.py` — single agent E2E + 4-agent concurrent | @member2 | 2h | ⚪ | AG-006 | TechSpec §8 Step 6 | 4-agent concurrent run on 10 conflict IOCs passes without crash |

**⛔ GATE — STORY-010:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py -v
# ALL PASS required before Sprint 4 begins
```

**Blocked by:** STORY-009 Gate AND STORY-006 Gate

---

### Sprint 3 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# ALL tests must pass before any Sprint 4 story begins
```

---

## Sprint 4: API Gateway & GraphRAG Pipeline
**Sprint Goal:** Expose the system over FastAPI and build provenance-grounded natural language querying.  
**Sprint Points:** 13 points  
**Note:** STORY-011 and STORY-012 run in parallel after Sprint 3 Gate.

---

### STORY-011: FastAPI REST Gateway
**Story ID:** STORY-011 | **Points:** 8 | **Sprint:** 4 | **Lead:** @member2 | **Support:** @member1

**Acceptance Criteria:**
- [ ] `POST /api/v1/query` — natural language query → evidence-backed answer
- [ ] `GET /api/v1/graph/{entity_type}/{entity_value}` — 2-hop JSON subgraph
- [ ] `GET /api/v1/conflicts` — paginated conflict list with decisions
- [ ] `GET /api/v1/provenance/{claim_id}` — full provenance chain
- [ ] `POST /api/v1/benchmark/run` — triggers async benchmark; returns job_id
- [ ] `GET /api/v1/benchmark/results/{job_id}` — returns GIR, CR, CRA, PTC, latency
- [ ] 422 on invalid inputs; 404 with message for missing entities

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| API-001 | Create `src/api/main.py` — FastAPI app with startup Neo4j connection | @member2 | 1h | ⚪ | Sprint 3 Gate | TechSpec §4.2 | `uvicorn src.api.main:app` starts; `/docs` loads |
| API-002 | Implement `POST /api/v1/query` | @member2 | 2h | ⚪ | API-001 | TechSpec §4.2 | Returns JSON with answer, subgraph, provenance_trail, conflicts |
| API-003 | Implement `GET /api/v1/graph/{entity_type}/{entity_value}` | @member2 | 1h | ⚪ | API-001 | TechSpec §4.2 | Returns valid subgraph; 404 for unknown entity |
| API-004 | Implement `GET /api/v1/conflicts` with status filter and pagination | @member2 | 1h | ⚪ | API-001 | TechSpec §4.2 | Returns all 63 conflicts for `?status=all` |
| API-005 | Implement `GET /api/v1/provenance/{claim_id}` | @member2 | 1h | ⚪ | API-001 | TechSpec §4.2 | Returns Claim → Evidence → Principal chain |
| API-006 | Implement benchmark endpoints (run + results) | @member2 | 1h | ⚪ | API-001 | TechSpec §4.2 | Async job dispatched; results accessible after completion |
| API-007 | Write `tests/test_api_endpoints.py` — all 6 endpoints, valid + invalid inputs | @member1 | 2h | ⚪ | API-006 | TechSpec §4.2 | All return correct status codes; invalid → 422 |

**⛔ GATE — STORY-011:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_api_endpoints.py -v
# ALL PASS required before STORY-013 begins
```

---

### STORY-012: GraphRAG Retriever & Evidence Synthesizer
**Story ID:** STORY-012 | **Points:** 5 | **Sprint:** 4 | **Lead:** @member2 | **Support:** —

**Acceptance Criteria:**
- [ ] `GraphRAGRetriever.retrieve(query)` extracts entity from natural language
- [ ] Uses pattern-comprehension Cypher (NOT chained OPTIONAL MATCH) from TechSpec §6.1
- [ ] Returns `AnalystAnswer` with `answer_text`, `evidence_subgraph`, `conflicts`, `provenance_claims`

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| RAG-001 | Create `src/rag/retriever.py` with entity extractor | @member2 | 2h | ⚪ | Sprint 3 Gate | TechSpec §6 | Extracts `entity_type`, `entity_value` from query string |
| RAG-002 | Implement pattern-comprehension Cypher neighborhood query | @member2 | 2h | ⚪ | RAG-001 | TechSpec §6.1 | Nested provenance_claims returned; no chained OPTIONAL MATCH |
| RAG-003 | Write `tests/test_graphrag_retriever.py` — known, unknown, conflict entity | @member2 | 1h | ⚪ | RAG-002 | TechSpec §6 | All 3 scenarios pass |

**⛔ GATE — STORY-012:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_graphrag_retriever.py -v
# ALL PASS required before STORY-013 begins (runs parallel with STORY-011)
```

---

### Sprint 4 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# ALL tests must pass before any Sprint 5 story begins
```

---

## Sprint 5: Benchmark Execution & Research Evaluation
**Sprint Goal:** Run head-to-head benchmark, compute metrics, generate research report.  
**Sprint Points:** 13 points  
**Build Order:** STORY-013 → STORY-014

---

### STORY-013: Benchmark Harness & Metric Evaluation Suite
**Story ID:** STORY-013 | **Points:** 8 | **Sprint:** 5 | **Lead:** @member1 | **Support:** @member2

**Acceptance Criteria:**
- [ ] Runs identical workloads across all 3 protocols + 3 ablation modes
- [ ] Fresh clean Neo4j database reset between each protocol run
- [ ] All 4 agents at `concurrency_workers=4` under each protocol
- [ ] Computes GIR, CR, CRA (against 63 ground-truth), PTC, mean latency, p95 latency
- [ ] Results saved to `data/results/benchmark_results.json`

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| BM-001 | Create `benchmark/runner.py` — `BenchmarkRunner` orchestration class | @member1 | 3h | ⚪ | Sprint 4 Gate | TechSpec §7.1 | Runner accepts protocol list; identical workload dispatched to each |
| BM-002 | Implement Neo4j wipe/reset between protocol runs | @member1 | 1h | ⚪ | BM-001 | TechSpec §7.1 | `MATCH (n) DETACH DELETE n`; constraints re-applied before each run |
| BM-003 | Implement GIR and CR metric calculators | @member1 | 1h | ⚪ | BM-001 | TechSpec §7.2 | Both metrics bounded [0, 100] |
| BM-004 | Implement CRA calculator against `data/analysis/conflicts.json` | @member2 | 1h | ⚪ | BM-001 | TechSpec §7.2 | Decision.winning_claim compared against ground truth |
| BM-005 | Implement PTC calculator | @member2 | 1h | ⚪ | BM-001 | TechSpec §7.2 | All domain nodes checked for unbroken path to Evidence + Principal |
| BM-006 | Implement latency aggregation (mean, p95) per protocol | @member1 | 1h | ⚪ | BM-001 | TechSpec §7 | Collected from `CoordinationResult.latency_ms` |
| BM-007 | Write `tests/test_benchmark_runner.py` — mini-run (100 records) all protocols | @member1 | 2h | ⚪ | BM-006 | TechSpec §7 | All metrics computed; Protocol 2 GIR > Protocol 1 confirmed |

**⛔ GATE — STORY-013:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_benchmark_runner.py -v
# ALL PASS required before STORY-014 begins
```

---

### STORY-014: Results Analysis, Visualization & Research Report
**Story ID:** STORY-014 | **Points:** 5 | **Sprint:** 5 | **Lead:** @member2 | **Support:** @member1

**Acceptance Criteria:**
- [ ] Comparison table: GIR, CR, CRA, PTC, latency for all protocols
- [ ] Bar charts for each metric (Protocol 1 vs 2 vs 3 modes)
- [ ] `data/results/research_report.md` states which ablation mode degraded most vs. full MPAC
- [ ] All charts saved as PNG in `data/results/charts/`

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|----|------|-------|-----|--------|---------|-----|--------------------|
| RPT-001 | Create `benchmark/visualizer.py` — loads results and generates comparison table | @member2 | 2h | ⚪ | STORY-013 Gate | TechSpec §7.2 | Table saved as `data/results/comparison_table.md` |
| RPT-002 | Generate bar charts using `matplotlib` for GIR, CRA, PTC, latency | @member2 | 2h | ⚪ | RPT-001 | TechSpec §7 | 4 PNG charts saved to `data/results/charts/` |
| RPT-003 | Write `data/results/research_report.md` | @member1 | 2h | ⚪ | RPT-002 | prd.md | Narrative confirms Protocol 2 > Protocol 1; ablation conclusions stated |

---

### Final Project Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v --tb=short
# ALL tests across all 5 phases must pass — this is the project sign-off gate
```

---

## Summary Tables

### Story Summary

| Story | Title | Sprint | Points | Lead | Support | Status |
|---|---|---|---|---|---|---|
| STORY-001 | Neo4j Docker Setup & Schema | Sprint 1 | 5 | @member1 | @member2 | ⚪ |
| STORY-002 | Core Pydantic Models & Utilities | Sprint 1 | 5 | @member2 | @member1 | ⚪ |
| STORY-002B | Two-Tier Ontology Registry & Validator | Sprint 1 | 5 | @member2 | @member1 | ⚪ |
| STORY-003 | Redis Distributed Lock Manager | Sprint 1 | 8 | @member1 | — | ⚪ |
| STORY-004 | Protocol 1 — Ad-Hoc Coordinator | Sprint 2 | 5 | @member1 | @member2 | ⚪ |
| STORY-005 | Conflict Detector & Arbitration | Sprint 2 | 8 | @member2 | @member1 | ⚪ |
| STORY-006 | Protocol 2 — Full MPAC | Sprint 2 | 8 | @member1 | @member2 | ⚪ |
| STORY-007 | Protocol 3 — MPAC Ablation | Sprint 2 | 5 | @member1 | — | ⚪ |
| STORY-008 | MCP Tool Adapters | Sprint 3 | 8 | @member2 | @member1 | ⚪ |
| STORY-009 | G²CP A2A Peer Hub | Sprint 3 | 8 | @member1 | @member2 | ⚪ |
| STORY-010 | LangGraph Agent State Machine | Sprint 3 | 8 | @member1 | @member2 | ⚪ |
| STORY-011 | FastAPI REST Gateway | Sprint 4 | 8 | @member2 | @member1 | ⚪ |
| STORY-012 | GraphRAG Retriever | Sprint 4 | 5 | @member2 | — | ⚪ |
| STORY-013 | Benchmark Harness & Metrics | Sprint 5 | 8 | @member1 | @member2 | ⚪ |
| STORY-014 | Results & Research Report | Sprint 5 | 5 | @member2 | @member1 | ⚪ |
| **TOTAL** | | **5 Sprints** | **94** | | | |

### Workload Distribution

| Sprint | @member1 Hours | @member2 Hours |
|---|---|---|
| Sprint 1 (Stories 001-003 + 002B) | ~17h | ~14h |
| Sprint 2 (Stories 004-007) | ~18h | ~17h |
| Sprint 3 (Stories 008-010) | ~14h | ~15h |
| Sprint 4 (Stories 011-012) | ~2h | ~13h |
| Sprint 5 (Stories 013-014) | ~11h | ~7h |
| **TOTAL** | **~62h** | **~66h** |

### Sprint Planning Summary

| Sprint | Stories | Points | Demo Condition |
|---|---|---|---|
| Sprint 1 | 001, 002, 002B, 003 | 23 | `pytest tests/test_neo4j_client.py tests/test_models.py tests/test_ontology_validator.py tests/test_lock_manager.py` all pass |
| Sprint 2 | 004, 005, 006, 007 | 26 | Concurrent agents on 10 conflict IOCs — MPAC writes provenance; Ad-Hoc does not |
| Sprint 3 | 008, 009, 010 | 24 | 4-agent concurrent run on 63 conflict IOCs; OntologyValidator correctly rejects hallucinated entity types |
| Sprint 4 | 011, 012 | 13 | `curl POST /api/v1/query` returns provenance-grounded answer for real IOC |
| Sprint 5 | 013, 014 | 13 | Comparison table shows Protocol 2 GIR/CRA > Protocol 1; ablation isolates causal component |

---

## Dependency Chain

```text
     ✅ Phase 1 (COMPLETED)
    [sources/, schemas/, analysis/]
                   │
     ┌─────────────┴─────────────┐
     ▼                           ▼
STORY-001                   STORY-002
(Neo4j Docker)              (Pydantic Models)
     │                           │
     │                           ▼
     │                      STORY-002B
     │                 (Ontology Registry
     │                   & Validator)
     ▼                           │
STORY-003                        │
(Redis Locks)                    │
     └─────────────┬─────────────┘
                   ▼
           ⛔ Sprint 1 Gate
                   │
                   ▼
             STORY-004
          (Ad-Hoc Baseline)
                   │
                   ▼
             STORY-005
        (Conflict Detector +
         Arbitration Engine)
                   │
                   ▼
             STORY-006
         (Full MPAC Protocol)
                   │
                   ▼
             STORY-007
         (MPAC Ablation Suite)
                   │
           ⛔ Sprint 2 Gate
                   │
                   ▼
             STORY-008
         (MCP Tool Adapters)
                   │
                   ▼
             STORY-009
          (G²CP A2A Peer Hub)
                   │
                   ▼
             STORY-010
  (LangGraph State Machine +
   OntologyValidator wired in)
                   │
           ⛔ Sprint 3 Gate
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
  STORY-011              STORY-012
  (FastAPI API)          (GraphRAG)
        │                     │
        └──────────┬──────────┘
           ⛔ Sprint 4 Gate
                   │
                   ▼
             STORY-013
           (Benchmark Run)
                   │
                   ▼
             STORY-014
           (Research Report)
                   │
             ⛔ Final Gate
                ✅ DONE
```

---

## File Structure to Build

```text
multiagent_knowledgegraph/
├── src/
│   ├── db/
│   │   └── neo4j_client.py          ← STORY-001 (+ node/rel schema_version stamps: ONT-006/007)
│   ├── schemas/
│   │   └── models.py                ← STORY-002
│   ├── utils/
│   │   └── time.py                  ← STORY-002
│   ├── ontology/                    ← NEW — STORY-002B
│   │   ├── __init__.py
│   │   └── validator.py             ← OntologyValidator (MERGE / APPROVE / REJECT)
│   ├── coordination/
│   │   ├── base.py                  ← STORY-004
│   │   ├── lock_manager.py          ← STORY-003
│   │   ├── detector.py              ← STORY-005
│   │   ├── arbitrator.py            ← STORY-005
│   │   ├── adhoc.py                 ← STORY-004
│   │   ├── mpac.py                  ← STORY-006
│   │   └── ablation.py              ← STORY-007
│   ├── mcp/
│   │   ├── base_tool.py             ← STORY-008
│   │   └── tools.py                 ← STORY-008
│   ├── agents/
│   │   ├── state.py                 ← STORY-010
│   │   ├── a2a.py                   ← STORY-009
│   │   └── workflow.py              ← STORY-010 (OntologyValidator wired into Extract Claim node)
│   ├── rag/
│   │   └── retriever.py             ← STORY-012
│   └── api/
│       └── main.py                  ← STORY-011
├── benchmark/
│   ├── runner.py                    ← STORY-013
│   └── visualizer.py               ← STORY-014
├── tests/
│   ├── test_data_pipeline.py        ← DONE (Phase 1)
│   ├── test_neo4j_client.py         ← STORY-001
│   ├── test_models.py               ← STORY-002
│   ├── test_ontology_validator.py   ← STORY-002B  ← NEW
│   ├── test_lock_manager.py         ← STORY-003
│   ├── test_adhoc_coordinator.py    ← STORY-004
│   ├── test_conflict_detector.py    ← STORY-005
│   ├── test_arbitration_engine.py   ← STORY-005
│   ├── test_mpac_coordinator.py     ← STORY-006
│   ├── test_ablation_coordinator.py ← STORY-007
│   ├── test_mcp_tools.py            ← STORY-008
│   ├── test_a2a_hub.py              ← STORY-009
│   ├── test_agent_workflow.py       ← STORY-010
│   ├── test_api_endpoints.py        ← STORY-011
│   ├── test_graphrag_retriever.py   ← STORY-012
│   └── test_benchmark_runner.py     ← STORY-013
├── data/
│   └── results/
│       ├── benchmark_results.json
│       ├── comparison_table.md
│       ├── research_report.md
│       └── charts/
├── docker-compose.yml               ← STORY-001
├── requirements.txt                 ← STORY-001 (updated + sentence-transformers>=2.7.0)
└── taskbreakdown.md                 ← THIS FILE

```

---

## Status Key

Update each story as work progresses:

| Symbol | Meaning |
|---|---|
| ⚪ | Not Started |
| 🟡 | In Progress |
| ⛔ | Blocked (waiting on Gate) |
| ✅ | Done (Gate test passed) |

---

## Document Sign-Off

| Member | Role | Agreed |
|---|---|---|
| @member1 | Lead Engineer | ⬜ Pending |
| @member2 | Support Engineer | ⬜ Pending |
