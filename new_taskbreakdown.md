# ProGRESS: Autonomous Multi-Agent Knowledge Graph — Master Task Breakdown

**Epic ID:** EPIC-PROGRESS-AUTONOMOUS-01  
**Epic Description:** Implement the complete transformation of the ProGRESS Cyber Threat Intelligence (CTI) Knowledge Graph platform to achieve 100% true agent autonomy, wire-level MCP JSON-RPC (`mcp.ClientSession`), standards-compliant A2A HTTP JSON-RPC (`tasks/send` and `/.well-known/agent.json`), cyclic LangGraph `StateGraph` with dynamic tool calling, and Neuro-Symbolic MPAC arbitration.

| Field | Details |
|---|---|
| Related PRD | [prd.md](file:///Users/sohithsai/multiagent_knowledgegraph/prd.md) |
| Related Master TechSpec | [autonomoustechspec.md](file:///Users/sohithsai/multiagent_knowledgegraph/autonomoustechspec.md) |
| Historical Reference | [taskbreakdown.md](file:///Users/sohithsai/multiagent_knowledgegraph/taskbreakdown.md) · [techspec.md](file:///Users/sohithsai/multiagent_knowledgegraph/techspec.md) |
| Total Story Points | **103 points** |
| Total Sprints | **5 Sprints** |
| Team Members | **@member1 (Lead — Infrastructure, Coordination, Agents, Benchmarking)**<br>**@member2 (Support — Schemas, IRS, Ontology, FastMCP, A2A, GraphRAG)** |
| Existing Test Suite | ✅ **101 unit tests passing** (Phase 1 data pipeline + legacy models, lock manager, FCFS arbiter, ad-hoc) |
| Current Target Phase | Sprint 2: Pre-Commit Hydration, LLM Factory, Conflict Detection & MPAC Engine |

---

> **MANDATORY RULE — Sequential Testing Gates:**  
> No story can begin until the story it depends on has passed ALL its unit tests. Every story ends with a strict `pytest` run. The `⛔ GATE` label marks these mandatory checkpoint tests. Skipping a gate is strictly prohibited to prevent architectural regressions.

---

## Team Responsibility Matrix

| Member | Role | Primary Domain | Est. Total Hours |
|---|---|---|---|
| **@member1** | Lead Systems Architect | Distributed Redis Locking, Neuro-Symbolic Conflict Detection, MPAC Rewrite, Cyclic LangGraph Agent, Benchmark Harness | ~68 hours |
| **@member2** | Support Protocols Engineer | Pydantic Schemas, Identity Resolution Service (IRS), Dynamic Ontology Staging, FastMCP Server/Client, A2A HTTP Router, GraphRAG & API | ~64 hours |

---

## EPIC Stories Overview

| Story | Title | Sprint | Points | Lead | Support | Status |
|---|---|---|---|---|---|---|
| **STORY-001** | Data Contract Upgrades & Cryptographic Attestations | Sprint 1 | 5 | @member2 | @member1 | ✅ Done |
| **STORY-002** | Identity Resolution Service (IRS) & Deterministic Keying | Sprint 1 | 5 | @member2 | @member1 | ✅ Done |
| **STORY-003** | Dynamic Ontology Validator & Tier-2 Provisional Staging | Sprint 1 | 5 | @member2 | @member1 | ✅ Done |
| **STORY-004** | Atomic Redis Lua Fencing Locks (`acquire_fenced`) | Sprint 1 | 5 | @member1 | — | ✅ Done |
| **STORY-005** | Pre-Commit Neo4j State Hydration & Constraints Initializer | Sprint 2 | 5 | @member1 | @member2 | ✅ Done |
| **STORY-006** | Multi-Provider LLM Factory with SHA256 Benchmark Cache | Sprint 2 | 5 | @member1 | @member2 | ✅ Done |
| **STORY-007** | Neuro-Symbolic 3-Class Conflict Detector & Semantic Judge | Sprint 2 | 8 | @member1 | @member2 | ✅ Done |
| **STORY-008** | Laplace-Smoothed Bayesian Log-Odds Arbitration Engine | Sprint 2 | 5 | @member1 | @member2 | ✅ Done |
| **STORY-009** | Full Protocol 2 MPAC Coordinator Rewrite & Dual-Layer Commits | Sprint 2 | 8 | @member1 | @member2 | ✅ Done |
| **STORY-010** | Baseline Upgrades: Ad-Hoc Edges & MPAC Ablation Suite | Sprint 2 | 5 | @member1 | — | ✅ Done |
| **STORY-011** | Standalone FastMCP CTI Data Server (`mcp.server.fastmcp`) | Sprint 3 | 5 | @member2 | @member1 | ✅ Done |
| **STORY-012** | Real MCP Protocol Client Manager (`mcp.ClientSession`) | Sprint 3 | 5 | @member2 | @member1 | ✅ Done |
| **STORY-013** | Standards-Compliant A2A HTTP JSON-RPC Router & Verifier LLM | Sprint 3 | 8 | @member2 | @member1 | ✅ Done |
| **STORY-014** | Cyclic LangGraph `StateGraph` Autonomous Investigator | Sprint 4 | 8 | @member1 | @member2 | ✅ Done |
| **STORY-015** | Backward-Compatible Workflow Adapter & Agentic-KGR Reflection | Sprint 4 | 5 | @member1 | @member2 | ✅ Done |
| **STORY-016** | Top-K Subquery GraphRAG Retriever with Provenance Traces | Sprint 5 | 5 | @member2 | — | ✅ Done |
| **STORY-017** | Production FastAPI REST Gateway with Lifespan & A2A Mount | Sprint 5 | 5 | @member2 | @member1 | ✅ Done |
| **STORY-018** | 5-Protocol Comparative Benchmark Harness & Metric Suite | Sprint 5 | 6 | @member1 | @member2 | ✅ Done |
| **TOTAL** | | **5 Sprints** | **103** | | | |

---

## Sprint 1: Schemas, IRS, Ontology Staging & Locking Foundation
**Sprint Goal:** Upgrade Pydantic contracts with edge fields and cryptographic attestations, build the Identity Resolution Service (IRS), implement Tier-2 Provisional Entity staging, and add atomic Redis Lua fencing locking.  
**Sprint Points:** 20 points  
**Parallelism:** STORY-001 and STORY-004 can start in parallel. STORY-002 starts after STORY-001. STORY-003 starts after STORY-002.

---

### STORY-001: Data Contract Upgrades & Cryptographic Attestations
**Story ID:** STORY-001 | **Points:** 5 | **Sprint:** 1 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an engineer, I need `GraphOperation`, `ArbitrationDecision`, `CoordinationResult`, and `PeerAttestation` to support edge relationships, provenance hashes, and cryptographic signatures without breaking existing frozen models or tests.

**Acceptance Criteria:**
- [x] Add `predicate`, `target_label`, `target_key`, `target_value`, `confidence`, `evidence_ids`, `raw_evidence_hash`, `upstream_origin_signature`, `valid_from`, `valid_until`, `is_functional`, `taint_class`, and `peer_attestations` to `GraphOperation`.
- [x] All new fields have backward-compatible defaults.
- [x] Existing `lock_keys` validator (enforcing lexicographical sorting and non-empty list) is preserved.
- [x] Create `PeerAttestation` Pydantic model (`responder_principal`, `stance`, `confidence`, `counter_object`, `evidence_id`, `upstream_origin_signature`, `signature`).
- [x] Add `posterior_prob` and `conflict_class` to `ArbitrationDecision`.
- [x] Add `fencing_token` and `posterior_prob` to `CoordinationResult`.
- [x] All existing 30 unit tests in `tests/test_models.py` pass without regression.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| S1-001 | Create `PeerAttestation` Pydantic model in `src/schemas/models.py` | @member2 | 1h | ✅ | None | TechSpec §3.3 | Model supports stances `CONFIRM`, `CONTRADICT`, `ABSTAIN` with Ed25519/HMAC signature |
| S1-002 | Extend `GraphOperation` with edge fields, hashes, and lineage signatures | @member2 | 1.5h | ✅ | S1-001 | TechSpec §3.3 | Model remains `frozen=True`, `extra="forbid"`; defaults ensure legacy calls work |
| S1-003 | Extend `ArbitrationDecision` and `CoordinationResult` with Bayesian posterior and fencing fields | @member2 | 1h | ✅ | S1-002 | TechSpec §3.3 | Fields added with `None` / `0` defaults |
| S1-004 | Add unit tests in `tests/test_models.py` verifying edge operations and attestations | @member1 | 1.5h | ✅ | S1-003 | TechSpec §3.3 | 100% of existing tests pass + 5 new tests for edge operations and attestations |

**⛔ GATE — STORY-001:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py -v
# ALL PASS required before STORY-002 begins
```

---

### STORY-002: Identity Resolution Service (IRS) & Deterministic Keying
**Story ID:** STORY-002 | **Points:** 5 | **Sprint:** 1 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an autonomous agent, I need an Identity Resolution Service to canonicalize heterogeneous IOC strings, normalize malware synonyms (`Heodo` → `emotet`, `QakBot` → `qbot`), and build deterministic lexicographical Redis mutex lock keys.

**Acceptance Criteria:**
- [x] Package created at `src/irs/__init__.py` and `src/irs/resolver.py`.
- [x] `canonicalize_ioc()` strips whitespace, lowercases, and validates IP/Domain/URL/Hash patterns.
- [x] `canonicalize_target()` normalizes malware family aliases via `MALWARE_ALIASES` dictionary.
- [x] `build_lock_keys()` generates deterministic mutex keys: `entity:{type}:{canon_val}` and for functional predicates `slot:{type}:{canon_val}:{predicate}`.
- [x] Lock keys are always returned in strictly sorted lexicographical order to prevent deadlocks.
- [x] `canonicalize_operation()` transforms raw `GraphOperation` into canonical forms.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| IRS-001 | Create `src/irs/__init__.py` and `src/irs/resolver.py` with alias dictionary | @member2 | 1.5h | ✅ | STORY-001 Gate | TechSpec §1.2 | `MALWARE_ALIASES` maps Heodo/Geodo → emotet, RedLine → redline stealer, QakBot → qbot |
| IRS-002 | Implement `canonicalize_ioc()` and `canonicalize_target()` | @member2 | 1.5h | ✅ | IRS-001 | TechSpec §1.2 | Deterministic normalization verified across IP, Domain, URL, SHA256 |
| IRS-003 | Implement `build_lock_keys()` and `canonicalize_operation()` | @member2 | 1h | ✅ | IRS-002 | TechSpec §5.2 | Keys always sorted; functional predicates include slot lock |
| IRS-004 | Write `tests/test_irs_resolver.py` | @member1 | 1h | ✅ | IRS-003 | TechSpec §1.2 | Tests cover synonym resolution, whitespace cleaning, and sorted lock keys |

**⛔ GATE — STORY-002:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_irs_resolver.py -v
# ALL PASS required before STORY-003 begins
```

---

### STORY-003: Dynamic Ontology Validator & Tier-2 Provisional Staging
**Story ID:** STORY-003 | **Points:** 5 | **Sprint:** 1 | **Lead:** @member2 | **Support:** @member1

**User Story:** As the knowledge graph governance engine, I need the Ontology Validator to validate node labels and predicates, enforce functional cardinality rules, and stage unconfirmed novel concepts into `:ProvisionalEntity` nodes so no threat intelligence is dropped.

**Acceptance Criteria:**
- [x] Tier-1 frozen ontology defines 8 core node labels and 5 relationships with `is_functional` flags (`USES_C2: True`, `HAS_SAMPLE: True`, `HOSTED_ON: False`, `DISTRIBUTED_VIA: False`, `ATTRIBUTED_TO: False`).
- [x] Step A: Exact match returns `MERGE` (`similarity_score=1.0`).
- [x] Step B: Cosine similarity ($\ge 0.85$) via `all-MiniLM-L6-v2` merges into nearest Tier-1 anchor.
- [x] Step C: Terms with similarity $< 0.85$ are staged as `status="PROVISIONAL"` (`:Entity:ProvisionalEntity`), confirmed by 1st principal.
- [x] Step D: When a 2nd distinct principal confirms a provisional term, promote to `TIER_2_APPROVED` (`schema_version="2.0"`).
- [x] All existing tests in `tests/test_ontology_validator.py` pass without regression.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| ONT-001 | Upgrade `src/ontology/validator.py` with `is_functional` predicate registry | @member2 | 1h | ✅ | STORY-002 Gate | TechSpec §5.2 | Predicate cardinality metadata accessible via `is_predicate_functional()` |
| ONT-002 | Implement `validate_and_route()` with Neo4j-backed multi-principal confirmation | @member2 | 2h | ✅ | ONT-001 | TechSpec §5.2 | 1 principal stages `:ProvisionalEntity`; 2nd principal auto-promotes |
| ONT-003 | Implement fallback similarity matcher when offline or without embeddings | @member2 | 1h | ✅ | ONT-002 | TechSpec §5.2 | Jaccard / token-overlap fallback functions without network |
| ONT-004 | Update `tests/test_ontology_validator.py` | @member1 | 1h | ✅ | ONT-003 | TechSpec §5.2 | Validates Tier-1 match, semantic merge, provisional staging, and promotion |

**⛔ GATE — STORY-003:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_ontology_validator.py -v
# ALL PASS required before Sprint 2 begins
```

---

### STORY-004: Atomic Redis Lua Fencing Locks (`acquire_fenced`)
**Story ID:** STORY-004 | **Points:** 5 | **Sprint:** 1 | **Lead:** @member1 | **Support:** —

**User Story:** As the distributed coordination engine, I need an atomic multi-key Redis Lua script that acquires all keys or none and increments a monotonic `fencing_token` so stale write attempts can be rejected.

**Acceptance Criteria:**
- [x] Add `_ACQUIRE_ALL_FENCED_SCRIPT` Lua script with `{mpac_coord}` hash tag ensuring all keys reside in the same Redis slot.
- [x] Implement `acquire_fenced(lock_keys, timeout_ms=5000)` returning `(token_dict, fencing_token)`.
- [x] `fencing_token` is globally monotonic (incremented via Redis `INCR`).
- [x] Existing `acquire(keys)` is retained as a backward-compatible wrapper.
- [x] In-memory fallback (`USE_REDIS=false`) supports monotonic counter and multi-key locking.
- [x] Existing `tests/test_lock_manager.py` passes 100%.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| LCK-001 | Implement atomic Lua script `_ACQUIRE_ALL_FENCED_SCRIPT` in `src/coordination/lock_manager.py` | @member1 | 2h | ✅ | None | TechSpec §1.2 | Script checks all keys, sets TTL, increments token, or rolls back atomically |
| LCK-002 | Implement `acquire_fenced()` and wrap `acquire()` for backward compatibility | @member1 | 1.5h | ✅ | LCK-001 | TechSpec §1.2 | Legacy `acquire()` calls return `Dict[str, str]`; `acquire_fenced()` returns `(dict, int)` |
| LCK-003 | Update in-memory fallback manager with monotonic counter | @member1 | 1h | ✅ | LCK-002 | TechSpec §1.2 | In-memory mode mints incrementing integer tokens |
| LCK-004 | Add fencing token unit tests to `tests/test_lock_manager.py` | @member1 | 1h | ✅ | LCK-003 | TechSpec §1.2 | Verifies monotonicity, atomic rollback on partial collision, and Lua release |

**⛔ GATE — STORY-004:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_lock_manager.py -v
# ALL PASS required before Sprint 2 begins
```

---

### Sprint 1 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py tests/test_irs_resolver.py tests/test_ontology_validator.py tests/test_lock_manager.py -v
# ALL must pass before Sprint 2 begins
```

---

## Sprint 2: Coordination Protocol Engine & MPAC Rewrite
**Sprint Goal:** Implement pre-commit Neo4j state hydration, establish the Multi-Provider LLM Factory with SHA256 caching upfront, build the Neuro-Symbolic 3-Class Conflict Detector, Laplace-Smoothed Bayesian Log-Odds arbitration, the complete Protocol 2 MPAC rewrite with Dual-Layer commits, and baseline upgrades.  
**Sprint Points:** 36 points  
**Build Order:** STORY-005 → STORY-006 → STORY-007 → STORY-008 → STORY-009 → STORY-010 (strictly sequential)

---

### STORY-005: Pre-Commit Neo4j State Hydration & Constraints Initializer
**Story ID:** STORY-005 | **Points:** 5 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the MPAC coordinator, I need to hydrate existing `:Claim` nodes from Neo4j before conflict classification to fix the single-operation submission blindspot.

**Acceptance Criteria:**
- [x] Upgrade `run_schema_init.py` with uniqueness constraints on `:Entity(canonical_id)`, `:Claim(id)`, `:Evidence(id)`, `:Conflict(id)`, `:Decision(id)`.
- [x] Add composite index on `(:Claim {subject_id, predicate})`.
- [x] Implement `hydrate_existing_claims(subject_ids: List[str]) -> List[GraphOperation]` in `src/db/neo4j_client.py`.
- [x] Hydrated claims correctly parse provenance properties (`claim_id`, `principal`, `predicate`, `target`, `confidence`, `valid_from`, `origin_sig`).

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| HYD-001 | Update `run_schema_init.py` with 5 uniqueness constraints and 2 composite indexes | @member1 | 1.5h | ✅ | Sprint 1 Gate | TechSpec §5.3 | Schema initialization script runs idempotently |
| HYD-002 | Implement `hydrate_existing_claims()` Cypher query in `src/db/neo4j_client.py` | @member1 | 2h | ✅ | HYD-001 | TechSpec §5.3 | Returns existing claims mapped to `GraphOperation` instances |
| HYD-003 | Add unit tests for hydration in `tests/test_neo4j_client.py` | @member2 | 1.5h | ✅ | HYD-002 | TechSpec §5.3 | Verifies hydration of claims and empty-result handling |

**⛔ GATE — STORY-005:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_neo4j_client.py -k "test_hydrate" -v
# ALL PASS required before STORY-006 begins
```

---

### STORY-006: Multi-Provider LLM Factory with SHA256 Benchmark Cache
**Story ID:** STORY-006 | **Points:** 5 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the system, I need a unified LLM factory supporting Gemini, OpenAI, Groq, and Ollama that caches structured Pydantic outputs by `sha256(schema + prompt)` so subsequent stories (STORY-007 Conflict Detector, STORY-013 Peer Verifier, STORY-014 Agent) can import `invoke_structured_llm` without circular or missing dependencies.

**Acceptance Criteria:**
- [x] Created at `src/agents/llm_factory.py`.
- [x] `get_chat_llm(temperature=0.0)` instantiates the configured LLM provider from environment variables (`LLM_PROVIDER`, `LLM_MODEL`).
- [x] `invoke_structured_llm(prompt, schema_cls)` computes content hash `sha256(schema_cls.__name__ + prompt)`.
- [x] Cached results stored in `data/cache/llm_structured_cache.json`.
- [x] If cached, returns saved model instance instantly without API calls.
- [x] If uncached, calls `llm.with_structured_output(schema_cls)` and persists to disk.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| LLM-001 | Implement `get_chat_llm()` supporting Gemini, OpenAI, Groq in `src/agents/llm_factory.py` | @member1 | 1.5h | ✅ | STORY-005 Gate | TechSpec §3.4 | Instantiates correct Chat model based on `.env` |
| LLM-002 | Implement `invoke_structured_llm()` with content-addressed SHA256 caching | @member1 | 2h | ✅ | LLM-001 | TechSpec §3.4 | Caches output in `data/cache/llm_structured_cache.json`; returns Pydantic model |
| LLM-003 | Write `tests/test_llm_factory.py` with mock LLM | @member2 | 1.5h | ✅ | LLM-002 | TechSpec §3.4 | Cache hit returns identical object; zero network calls on repeat invocation |

**⛔ GATE — STORY-006:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_llm_factory.py -v
# ALL PASS required before STORY-007 begins
```

---

### STORY-007: Neuro-Symbolic 3-Class Conflict Detector & Semantic Judge
**Story ID:** STORY-007 | **Points:** 8 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the coordination engine, I need a Neuro-Symbolic conflict detector combining deterministic fast-paths with an LLM Semantic Conflict Judge (`invoke_structured_llm` from `src/agents/llm_factory.py`) to classify overlapping claims into 4 nuanced classes.

**Acceptance Criteria:**
- [x] `classify_pair_with_llm(op_a, op_b)` implements rule fast-path:
  - Different indicator or predicate $\rightarrow$ `UNRELATED`
  - Non-functional predicate $\rightarrow$ `CO_TENANT_COMPATIBLE`
  - Identical target $\rightarrow$ `AGREEMENT_OVERLAP`
  - Time gap $> 30$ days on functional predicate $\rightarrow$ `TEMPORAL_SUPERSESSION`
  - Otherwise calls structured LLM judge (`LLMConflictClassification`) $\rightarrow$ `EXCLUSIVE_CONTRADICTION`.
- [x] `detect_semantic(operations, existing_claims)` merges incoming operations with Neo4j-hydrated claims and outputs contradictions.
- [x] Legacy `detect(operations)` method is preserved for backward compatibility.
- [x] Existing `tests/test_conflict_detector.py` passes 100%.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| CD-001 | Define `LLMConflictClassification` Pydantic model in `src/coordination/conflict_detector.py` | @member2 | 1h | ✅ | STORY-006 Gate | TechSpec §3.6 | Output model requires `conflict_class` and `explanation` |
| CD-002 | Implement deterministic fast-path rules in `classify_pair_with_llm()` | @member1 | 2h | ✅ | CD-001 | TechSpec §3.6 | Obvious matches/temporal gaps evaluated in $< 0.1$ms |
| CD-003 | Wire LLM Semantic Conflict Judge for ambiguous functional disputes using `invoke_structured_llm` | @member1 | 2h | ✅ | CD-002 | TechSpec §3.6 | Structured LLM prompt resolves co-tenant payloads vs. true contradictions |
| CD-004 | Implement `detect_semantic()` merging hydrated existing claims | @member1 | 1.5h | ✅ | CD-003 | TechSpec §3.6 | Identifies single-op incoming conflicts against prior graph claims |
| CD-005 | Update `tests/test_conflict_detector.py` | @member2 | 1.5h | ✅ | CD-004 | TechSpec §3.6 | Validates all 4 conflict classes + hydrated claim detection |

**⛔ GATE — STORY-007:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_conflict_detector.py -v
# ALL PASS required before STORY-008 begins
```

---

### STORY-008: Laplace-Smoothed Bayesian Log-Odds Arbitration Engine
**Story ID:** STORY-008 | **Points:** 5 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the arbitration engine, I need a mathematically rigorous Bayesian Log-Odds arbitrator with principal reliability priors, temporal decay, and lineage deduplication to resolve competing claims.

**Acceptance Criteria:**
- [x] `resolve(all_operations, conflicts, mode="bayesian")` calculates net log-odds: $L(h) = \sum_{i \in \text{Support}(h)} \ln\left(\frac{1 + e_i}{1 - e_i}\right) - \sum_{j \in \text{Contradict}(h)} \ln\left(\frac{1 + e_j}{1 - e_j}\right)$
- [x] Principal priors ($w_p$): MalwareBazaar ($0.833$), ThreatFox ($0.783$), URLhaus ($0.739$), OTX ($0.636$).
- [x] Temporal freshness decay ($\tau(\Delta t)$): FileHash ($0.0$), Domain ($0.015$), URL ($0.03$), IP ($0.05$).
- [x] Lineage deduplication: Claims sharing identical `upstream_origin_signature` are counted only once.
- [x] Posterior probability calculation: $P(h) = \frac{1}{1 + \exp(-L(h))}$.
- [x] Default `mode="fcfs"` is preserved for backward compatibility.
- [x] Existing `tests/test_arbitration_engine.py` passes 100%.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| ARB-001 | Implement principal prior table and temporal decay functions in `src/coordination/arbitration_engine.py` | @member2 | 1h | ✅ | STORY-007 Gate | TechSpec §5.4 | Math matches formulas with effective weights clamped to $[0.05, 0.95]$ |
| ARB-002 | Implement `compute_posterior()` with lineage deduplication | @member1 | 2h | ✅ | ARB-001 | TechSpec §5.4 | Duplicate `upstream_origin_signature` votes collapsed to single weight |
| ARB-003 | Add `mode="bayesian"` to `resolve()` | @member1 | 1.5h | ✅ | ARB-002 | TechSpec §5.4 | Highest posterior wins; losing claims marked rejected with decision reason |
| ARB-004 | Update `tests/test_arbitration_engine.py` | @member2 | 1.5h | ✅ | ARB-003 | TechSpec §5.4 | Tests verify Bayesian scoring, tie-breaking, and FCFS fallback |

**⛔ GATE — STORY-008:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_arbitration_engine.py -v
# ALL PASS required before STORY-009 begins
```

---

### STORY-009: Full Protocol 2 MPAC Coordinator Rewrite & Dual-Layer Commits
**Story ID:** STORY-009 | **Points:** 8 | **Sprint:** 2 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the coordination engine, I need `MPACCoordinator` completely rewritten to execute the full 6-step lifecycle: atomic Redis Lua lock, pre-commit state hydration, 3-class conflict detection, Bayesian arbitration, guarded Dual-Layer Neo4j commits, and atomic lock release.

**Acceptance Criteria:**
- [x] Complete rewrite of `src/coordination/mpac.py` inheriting `BaseCoordinator`.
- [x] Accepts `Union[GraphOperation, List[GraphOperation]]` in `submit()`.
- [x] Step 1: Acquires atomic Redis Lua multi-lock, minting monotonic `fencing_token`.
- [x] Step 2: Hydrates prior Neo4j `:Claim` nodes for locked subjects.
- [x] Step 3: Classifies conflicts using `detect_semantic()`.
- [x] Step 4: Resolves contradictions via Bayesian Log-Odds (`mode="bayesian"`).
- [x] Step 5: Executes Guarded Dual-Layer Neo4j transaction:
  - Checks `WHERE coalesce(s.fencing_token, 0) <= $fencing_token`.
  - Hot Domain Graph: writes `:Entity` and `:ACTIVE_REL` (`posterior_prob`, `fencing_token`).
  - Cold Provenance Graph: writes `:Claim`, `:Evidence`, `:Conflict`, `:Decision` nodes and relationships.
- [x] Step 6: Releases Redis Lua locks in `finally` block.
- [x] Returns `CoordinationResult` with `status`, `fencing_token`, `posterior_prob`, and `latency_ms`.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| MPAC-001 | Rewrite `src/coordination/mpac.py` skeleton with session lifecycle and locking | @member1 | 2h | ✅ | STORY-008 Gate | TechSpec §1.2 | `submit()` executes lock acquisition and guaranteed finally release |
| MPAC-002 | Integrate hydration, semantic detection, and Bayesian arbitration into pipeline | @member1 | 2.5h | ✅ | MPAC-001 | TechSpec §1.2 | Pipeline correctly routes clean vs. contradictory operations |
| MPAC-003 | Implement Guarded Dual-Layer Cypher transaction in `_commit_dual_layer()` | @member1 | 2h | ✅ | MPAC-002 | TechSpec §5.3 | Enforces fencing token check; writes domain edge and provenance meta-graph |
| MPAC-004 | Write comprehensive unit tests in `tests/test_mpac_coordinator.py` | @member2 | 2h | ✅ | MPAC-003 | TechSpec §1.2 | Verifies clean commit, conflict arbitration, fencing rejection, and lock safety |

**⛔ GATE — STORY-009:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_mpac_coordinator.py -v
# ALL PASS required before STORY-010 begins
```

---

### STORY-010: Baseline Upgrades: Ad-Hoc Edges & MPAC Ablation Suite
**Story ID:** STORY-010 | **Points:** 5 | **Sprint:** 2 | **Lead:** @member1 | **Support:** —

**User Story:** As the research benchmark, I need `AdHocCoordinator` upgraded to write uncoordinated edges and `MPACAblationCoordinator` updated to support controlled ablation modes.

**Acceptance Criteria:**
- [x] Upgrade `src/coordination/adhoc.py` to write subject entity, object entity, and `:ACTIVE_REL` edge directly without locks or conflict checks.
- [x] Concurrent conflicting writes under Ad-Hoc overwrite functional edges and leave corruptions (GIR ~50-64%).
- [x] Upgrade `src/coordination/ablation.py` to inherit rewritten `MPACCoordinator`:
  - `NO_A2A`: ignores peer attestations in Bayesian log-odds.
  - `NO_SEMANTIC_LOCKS`: bypasses Redis Lua locks.
  - `FCFS_ARB`: replaces Bayesian log-odds with first-come first-served arbitration.
- [x] Unit tests in `tests/test_adhoc_coordinator.py` and `tests/test_ablation_coordinator.py` pass.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| ABL-001 | Upgrade `src/coordination/adhoc.py` with domain edge write queries | @member1 | 1.5h | ✅ | STORY-009 Gate | TechSpec §1.2 | Writes `:ACTIVE_REL` without locking; produces measurable GIR drops |
| ABL-002 | Update `src/coordination/ablation.py` to subclass new `MPACCoordinator` | @member1 | 2h | ✅ | ABL-001 | TechSpec §1.2 | Overrides targeted methods for `NO_A2A`, `NO_SEMANTIC_LOCKS`, `FCFS_ARB` |
| ABL-003 | Update `tests/test_adhoc_coordinator.py` and `tests/test_ablation_coordinator.py` | @member1 | 1.5h | ✅ | ABL-002 | TechSpec §1.2 | Verifies distinct behavior for all 3 ablation modes and ad-hoc edge overwrite |

**⛔ GATE — STORY-010:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_adhoc_coordinator.py tests/test_ablation_coordinator.py -v
# ALL PASS required before Sprint 3 begins
```

---

### Sprint 2 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_llm_factory.py tests/test_conflict_detector.py tests/test_arbitration_engine.py tests/test_mpac_coordinator.py tests/test_adhoc_coordinator.py tests/test_ablation_coordinator.py -v
# ALL must pass before Sprint 3 begins
```

---

## Sprint 3: Real FastMCP Server & Real A2A Protocol Layer
**Sprint Goal:** Build the standalone FastMCP JSON-RPC server, the `mcp.ClientSession` client manager with dynamic tool discovery, and the standards-compliant A2A HTTP JSON-RPC router with Verifier LLM.  
**Sprint Points:** 18 points  
**Build Order:** STORY-011 → STORY-012 → STORY-013 (strictly sequential)

---

### STORY-011: Standalone FastMCP CTI Data Server (`mcp.server.fastmcp`)
**Story ID:** STORY-011 | **Points:** 5 | **Sprint:** 3 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an autonomous agent, I need a standalone FastMCP server exposing the 16,481 CTI records and active ontology schema over standard JSON-RPC without importing functions directly.

**Acceptance Criteria:**
- [x] Created at `src/mcp_servers/__init__.py` and `src/mcp_servers/cti_mcp_server.py`.
- [x] Uses `mcp.server.fastmcp.FastMCP("ProGRESS-CTI-MCP-Server")`.
- [x] Resource `ontology://tier1-schema` returns JSON of active node labels and predicates with cardinality.
- [x] Tool `search_cti_indicator(principal, ioc_value)` returns taint-separated telemetry and `raw_evidence_sha256` provenance stamps.
- [x] Tool `pivot_by_malware_family(principal, malware_family, limit)` returns related indicators for multi-hop expansion.
- [x] Standalone execution via `python src/mcp_servers/cti_mcp_server.py` runs over stdio transport.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| MCP-101 | Create `src/mcp_servers/cti_mcp_server.py` with FastMCP app and lazy feed loader | @member2 | 1.5h | ✅ | Sprint 2 Gate | TechSpec §3.1 | Loads 16,481 normalized records on-demand without memory leaks |
| MCP-102 | Implement `@mcp.resource("ontology://tier1-schema")` | @member2 | 1h | ✅ | MCP-101 | TechSpec §3.1 | Returns valid JSON schema with `is_functional` predicates |
| MCP-103 | Implement `@mcp.tool() search_cti_indicator` with taint separation | @member2 | 1.5h | ✅ | MCP-102 | TechSpec §3.1 | Separates `trusted_telemetry` from `tainted_text_origin` and computes SHA256 |
| MCP-104 | Implement `@mcp.tool() pivot_by_malware_family` | @member2 | 1h | ✅ | MCP-103 | TechSpec §3.1 | Returns up to limit associated indicators sorted by confidence |
| MCP-105 | Write `tests/test_cti_mcp_server.py` | @member1 | 1.5h | ✅ | MCP-104 | TechSpec §3.1 | Tests verify resource read, indicator search, and malware pivoting |

**⛔ GATE — STORY-011:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_cti_mcp_server.py -v
# ALL PASS required before STORY-012 begins
```

---

### STORY-012: Real MCP Protocol Client Manager (`mcp.ClientSession`)
**Story ID:** STORY-012 | **Points:** 5 | **Sprint:** 3 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an agent runtime, I need a client manager that connects to the FastMCP server over JSON-RPC 2.0 stdio stream, discovers tools dynamically via `session.list_tools()`, and converts them into LangChain `StructuredTool` objects with the principal identity bound in closure.

**Acceptance Criteria:**
- [x] Created at `src/mcp_servers/mcp_client.py`.
- [x] `RealMCPClientManager` manages `mcp.ClientSession` using `stdio_client`.
- [x] `read_ontology_resource()` reads and parses `ontology://tier1-schema`.
- [x] `discover_langchain_tools()` queries `session.list_tools()` and builds LangChain `StructuredTool` instances.
- [x] The `principal` parameter is excluded from the tool argument schema and injected into the closure payload so the LLM cannot spoof identity.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| MCP-201 | Implement `RealMCPClientManager` with async context manager session | @member2 | 2h | ✅ | STORY-011 Gate | TechSpec §3.2 | Opens stdio stream to `cti_mcp_server.py`, initializes protocol, yields session |
| MCP-202 | Implement dynamic `discover_langchain_tools()` with dynamic Pydantic schema | @member2 | 2h | ✅ | MCP-201 | TechSpec §3.2 | Tools discovered at runtime; `principal` argument securely bound in closure |
| MCP-203 | Implement `read_ontology_resource()` | @member2 | 1h | ✅ | MCP-202 | TechSpec §3.2 | Reads resource text and returns parsed dictionary |
| MCP-204 | Write `tests/test_mcp_client.py` | @member1 | 1.5h | ✅ | MCP-203 | TechSpec §3.2 | Connects to server, lists tools, executes RPC call, verifies output |

**⛔ GATE — STORY-012:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_client.py -v
# ALL PASS required before STORY-013 begins
```

---

### STORY-013: Standards-Compliant A2A HTTP JSON-RPC Router & Verifier LLM
**Story ID:** STORY-013 | **Points:** 8 | **Sprint:** 3 | **Lead:** @member2 | **Support:** @member1

**User Story:** As an autonomous agent, I need to verify extracted claims with peers over real HTTP JSON-RPC 2.0 (`tasks/send`), where each peer queries its own MCP feed and uses a Verifier LLM (`invoke_structured_llm` built in STORY-006) to emit cryptographically signed attestations.

**Acceptance Criteria:**
- [x] Created at `src/a2a/__init__.py` and `src/a2a/peer_hub.py`.
- [x] FastAPI `a2a_router` exposes `GET /.well-known/agent.json` (publishing Agent Cards for all 4 principals).
- [x] Endpoint `POST /a2a/{principal}/tasks/send` handles JSON-RPC 2.0:
  - Validates `hop_budget == 0` (preventing recursive query storms).
  - Queries local MCP server for the indicator.
  - Invokes `_evaluate_peer_evidence_with_llm()` (`LLMPeerVerificationJudgment`).
  - Stance must be `CONFIRM`, `CONTRADICT`, or `ABSTAIN`.
  - Signs payload with HMAC-SHA256 (`_sign_payload`).
- [x] `A2APeerHub.verify_claim_with_peers()` dispatches concurrent HTTP requests with 3500ms timeout and returns `List[PeerAttestation]`.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| A2A-101 | Implement `GET /.well-known/agent.json` and `POST /a2a/{principal}/tasks/send` in `src/a2a/peer_hub.py` | @member2 | 2h | ✅ | STORY-012 Gate | TechSpec §3.3 | Endpoints conform to standard A2A JSON-RPC 2.0 protocol |
| A2A-102 | Implement `_evaluate_peer_evidence_with_llm()` structured judgment via `invoke_structured_llm` | @member2 | 2h | ✅ | A2A-101 | TechSpec §3.3 | Verifier LLM compares claimed quad vs. peer MCP record |
| A2A-103 | Implement HMAC/Ed25519 payload signing and canonicalization | @member2 | 1h | ✅ | A2A-102 | TechSpec §3.3 | Canonicalizes counter-object and generates cryptographic signature |
| A2A-104 | Implement `A2APeerHub` HTTP client with `httpx.AsyncClient` | @member1 | 1.5h | ✅ | A2A-103 | TechSpec §3.3 | Dispatches parallel calls to N-1 peers; handles timeout with `ABSTAIN` |
| A2A-105 | Write `tests/test_a2a_peer_hub.py` | @member1 | 1.5h | ✅ | A2A-104 | TechSpec §3.3 | Tests Agent Cards, task send endpoint, peer consensus, and timeout handling |

**⛔ GATE — STORY-013:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_peer_hub.py -v
# ALL PASS required before Sprint 4 begins
```

---

### Sprint 3 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_cti_mcp_server.py tests/test_mcp_client.py tests/test_a2a_peer_hub.py -v
# ALL must pass before Sprint 4 begins
```

---

## Sprint 4: Autonomous Cyclic LangGraph Agent
**Sprint Goal:** Build the 5-node cyclic `StateGraph` autonomous investigator driving live tool-calling over MCP and A2A peer verification, and bridge legacy workflows with Agentic-KGR reflection.  
**Sprint Points:** 13 points  
**Build Order:** STORY-014 → STORY-015 (strictly sequential)

---

### STORY-014: Cyclic LangGraph `StateGraph` Autonomous Investigator
**Story ID:** STORY-014 | **Points:** 8 | **Sprint:** 4 | **Lead:** @member1 | **Support:** @member2

**User Story:** As an autonomous agent, I need a true 5-node cyclic `langgraph.graph.StateGraph` where the Planner LLM decides tool calls dynamically, the Extractor LLM synthesizes schema-governed quads, and peer verification runs over A2A.

**Acceptance Criteria:**
- [x] Created at `src/agents/investigator.py`.
- [x] State typed as `InvestigatorGraphState` with `messages`, `mcp_evidence_log`, `extracted_operations`, `rejection_feedback`, etc.
- [x] Node 1 (`planner_node`): Privileged Planner LLM (`llm.bind_tools(mcp_tools)`) inspects clues and emits `tool_calls`.
- [x] Conditional Edge 1 (`route_after_planner`): Routes to `mcp_tool_node` if tool calls present and hop count $< \text{max\_hops}$, otherwise `extractor_node`.
- [x] Node 2 (`mcp_tool_node`): Executes tool calls over `mcp.ClientSession`, appends evidence, sanitizes tainted text, and loops back to `planner_node` (cyclic loop).
- [x] Node 3 (`extractor_node`): Quarantined Extractor LLM (`with_structured_output(ExtractedQuadBatch)`) extracts quads, canonicalizes via IRS, and validates via Ontology.
- [x] Node 4 (`a2a_verify_node`): Dispatches HTTP A2A verification to peers.
- [x] Node 5 (`mpac_commit_and_reflect`): Submits quads to coordinator; logs rejection feedback for Agentic-KGR refinement.
- [x] Conditional Edge 2 (`route_after_commit`): If rejected and not refined, loops back to `extractor_node`, otherwise `END`.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| AGT-001 | Define `InvestigatorGraphState`, `ExtractedSemanticQuad`, `ExtractedQuadBatch` models | @member2 | 1h | ✅ | Sprint 3 Gate | TechSpec §3.5 | Strict Pydantic models for structured quad extraction |
| AGT-002 | Build `planner_node` and `mcp_tool_node` cyclic loop | @member1 | 2.5h | ✅ | AGT-001 | TechSpec §3.5 | Planner LLM autonomously decides tool calls and pivots up to max hops |
| AGT-003 | Build `extractor_node` with IRS canonicalization and Ontology validation | @member1 | 2h | ✅ | AGT-002 | TechSpec §3.5 | Quads validated and canonicalized into typed `GraphOperation` list |
| AGT-004 | Wire `a2a_verify_node` and `mpac_commit_and_reflect` with Agentic-KGR feedback | @member1 | 1.5h | ✅ | AGT-003 | TechSpec §3.5 | Peer attestations attached; rejection feedback triggers closed-loop refinement |
| AGT-005 | Write `tests/test_investigator.py` end-to-end integration test | @member2 | 2h | ✅ | AGT-004 | TechSpec §3.5 | Single seed IOC executes 2-hop autonomous pivot, extraction, A2A, and commit |

**⛔ GATE — STORY-014:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_investigator.py -v
# ALL PASS required before STORY-015 begins
```

---

### STORY-015: Backward-Compatible Workflow Adapter & Agentic-KGR Reflection
**Story ID:** STORY-015 | **Points:** 5 | **Sprint:** 4 | **Lead:** @member1 | **Support:** @member2

**User Story:** As an existing test or API caller, I need `src/agents/workflow.py` and `src/agents/a2a.py` to preserve their legacy public API while delegating to the new `AutonomousCTIInvestigator`.

**Acceptance Criteria:**
- [x] `src/agents/workflow.py` exports `run_agent(principal_id, ioc_value, protocol, neo4j_client, lock_manager)`.
- [x] `src/agents/a2a.py` exports `G2CPPeerHub.query_peers()`, delegating to real `A2APeerHub`.
- [x] All existing tests in `tests/test_agent_workflow.py` and `tests/test_a2a_hub.py` pass without modification.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| WFK-001 | Adapt `src/agents/workflow.py` to delegate `run_agent()` to `AutonomousCTIInvestigator` | @member1 | 2h | ✅ | STORY-014 Gate | TechSpec §1.2 | Public function signature and return type preserved |
| WFK-002 | Adapt `src/agents/a2a.py` to wrap new `A2APeerHub` HTTP client | @member2 | 1.5h | ✅ | WFK-001 | TechSpec §1.2 | Legacy `query_peers()` returns `(List[A2AResponse], float)` |
| WFK-003 | Run legacy test suite against adapted modules | @member1 | 1.5h | ✅ | WFK-002 | TechSpec §1.2 | Existing unit tests pass with zero regressions |

**⛔ GATE — STORY-015:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py tests/test_a2a_hub.py -v
# ALL PASS required before Sprint 5 begins
```

---

### Sprint 4 Full Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_investigator.py tests/test_agent_workflow.py tests/test_a2a_hub.py -v
# ALL must pass before Sprint 5 begins
```

---

## Sprint 5: GraphRAG, API Gateway & Benchmark Suite
**Sprint Goal:** Implement conflict-aware GraphRAG retrieval, complete the FastAPI REST gateway with lifespan management, and build the 5-protocol comparative benchmark harness.  
**Sprint Points:** 16 points  
**Build Order:** STORY-016 → STORY-017 → STORY-018 (strictly sequential)

---

### STORY-016: Top-K Subquery GraphRAG Retriever with Provenance Traces
**Story ID:** STORY-016 | **Points:** 5 | **Sprint:** 5 | **Lead:** @member2 | **Support:** —

**User Story:** As an intelligence analyst, I need the GraphRAG retriever to execute stratified Top-K Cypher subqueries ordered by posterior probability to avoid Cartesian explosions on malware supernodes, returning conflict warnings and cryptographic provenance trails.

**Acceptance Criteria:**
- [x] Created at `src/graphrag/__init__.py` and `src/graphrag/retriever.py` (and updated in `src/rag/retriever.py`).
- [x] Cypher queries use `CALL () { ORDER BY r.posterior_prob DESC LIMIT 25 }` subqueries.
- [x] Returns `AnalystAnswer` with `answer_text`, `evidence_subgraph`, `conflicts`, and `provenance_claims`.
- [x] Highlights active disputes when an entity has unresolved `:Conflict` nodes.
- [x] Existing `tests/test_graphrag_retriever.py` passes 100%.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| RAG-101 | Implement stratified Top-K Cypher traversal in `src/graphrag/retriever.py` | @member2 | 2h | ✅ | Sprint 4 Gate | TechSpec §1.2 | Subquery limits 25 edges per hop, ordered by posterior probability |
| RAG-102 | Implement conflict detection and provenance chain formatting | @member2 | 1.5h | ✅ | RAG-101 | TechSpec §1.2 | Flags active disputes and surfaces upstream origin signatures |
| RAG-103 | Update `tests/test_graphrag_retriever.py` | @member2 | 1.5h | ✅ | RAG-102 | TechSpec §1.2 | Verifies answer synthesis, conflict warnings, and Top-K limit enforcement |

**⛔ GATE — STORY-016:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_graphrag_retriever.py -v
# ALL PASS required before STORY-017 begins
```

---

### STORY-017: Production FastAPI REST Gateway with Lifespan & A2A Mount
**Story ID:** STORY-017 | **Points:** 5 | **Sprint:** 5 | **Lead:** @member2 | **Support:** @member1

**User Story:** As a client or benchmark script, I need all 10 REST endpoints running on `http://127.0.0.1:8000`, with FastAPI `lifespan` managing connection pools and the `a2a_router` mounted for peer queries.

**Acceptance Criteria:**
- [x] Upgrade `src/api/main.py`.
- [x] Replaces deprecated `@app.on_event("startup")` and `"shutdown"` with async `lifespan` context manager.
- [x] Mounts `a2a_router` exposing `GET /.well-known/agent.json` and `POST /a2a/{principal}/tasks/send`.
- [x] All 10 production endpoints functional:
  - `GET /health`
  - `POST /agents/process` (wires `AutonomousCTIInvestigator`)
  - `POST /agents/batch`
  - `POST /sync`
  - `POST /api/v1/query` (wires `GraphRAGRetriever`)
  - `GET /api/v1/graph/{type}/{value}`
  - `GET /api/v1/conflicts`
  - `GET /api/v1/provenance/{claim_id}`
  - `POST /api/v1/benchmark/run`
  - `GET /api/v1/benchmark/results/{job_id}`
- [x] Existing `tests/test_api_endpoints.py` passes 100%.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| API-101 | Refactor `src/api/main.py` with FastAPI `lifespan` and mount `a2a_router` | @member2 | 1.5h | ✅ | STORY-016 Gate | TechSpec §5.5 | Fixes deprecation warnings; mounts A2A discovery and task endpoints |
| API-102 | Wire `/agents/process` to `AutonomousCTIInvestigator` | @member1 | 1.5h | ✅ | API-101 | TechSpec §5.5 | Single endpoint runs full cyclic LangGraph + MCP + A2A + MPAC flow |
| API-103 | Wire benchmark endpoints to `src/benchmark/harness.py` background tasks | @member2 | 1h | ✅ | API-102 | TechSpec §5.5 | Dispatches async benchmark job and returns tracking `job_id` |
| API-104 | Update `tests/test_api_endpoints.py` | @member1 | 1h | ✅ | API-103 | TechSpec §5.5 | Verifies all 10 endpoints, A2A card discovery, and status codes |

**⛔ GATE — STORY-017:**
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_api_endpoints.py -v
# ALL PASS required before STORY-018 begins
```

---

### STORY-018: 5-Protocol Comparative Benchmark Harness & Metric Suite
**Story ID:** STORY-018 | **Points:** 6 | **Sprint:** 5 | **Lead:** @member1 | **Support:** @member2

**User Story:** As the research team, I need an automated benchmark harness executing 5 protocol configurations against clean Neo4j states using verified conflict datasets to evaluate GIR, CRA, PTC, and latency.

**Acceptance Criteria:**
- [x] Created at `src/benchmark/__init__.py` and `src/benchmark/harness.py`.
- [x] Evaluates 5 configurations:
  1. **Protocol 1 (Ad-Hoc):** Unlocked, uncoordinated writes.
  2. **Protocol 2 (Full MPAC):** Lua fencing + Neuro-Symbolic 3-class + Bayesian log-odds + A2A.
  3. **Protocol 3a (No A2A):** MPAC minus peer verification.
  4. **Protocol 3b (No Locks):** MPAC minus Redis Lua fencing locks.
  5. **Protocol 3c (FCFS Arb):** MPAC with FCFS instead of Bayesian log-odds.
- [x] Executes clean database wipe and constraint re-application between protocol runs.
- [x] Calculates Graph Integrity Rate (GIR), Conflict Resolution Accuracy (CRA), and Provenance Traceability Completeness (PTC).
- [x] Target verification gates:
  - Full MPAC: GIR $= 100\%$, CRA $\ge 95\%$, PTC $= 100\%$.
  - Ad-Hoc: GIR $\le 68\%$, CRA $= 0\%$, PTC $= 0\%$.
- [x] Persists benchmark outputs to `data/results/benchmark_results.json` and markdown comparison table.

**Tasks:**

| ID | Task | Owner | Est | Status | Blocker | Ref | Definition of Done |
|---|---|---|---|---|---|---|---|
| BM-101 | Create `src/benchmark/harness.py` with database reset and workload loader | @member1 | 2h | ✅ | STORY-017 Gate | TechSpec §7 | Loads 371 overlaps and verified conflicts; wipes DB cleanly per run |
| BM-102 | Implement automated execution of all 5 protocol configurations | @member1 | 2h | ✅ | BM-101 | TechSpec §7 | Dispatches concurrent agent operations across each protocol variant |
| BM-103 | Implement GIR, CRA, PTC, and latency metrics computation | @member2 | 1h | ✅ | BM-102 | TechSpec §7 | Computes exact mathematical formulas; verifies target thresholds |
| BM-104 | Generate markdown comparison tables and JSON results | @member2 | 1h | ✅ | BM-103 | TechSpec §7 | Persists to `data/results/benchmark_results.json` and prints summary table |

**⛔ GATE — STORY-018 (Final System Gate):**
```bash
python -m src.benchmark.harness
# Must demonstrate:
# - Full MPAC GIR = 100%, CRA >= 95%, PTC = 100%
# - Protocol 1 GIR <= 68%, CRA = 0%
```

---

### Final Project Verification Gate
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v --tb=short
# ALL unit and integration tests across all modules must pass with zero failures
```

---

## Complete Dependency Chain

```text
                             ✅ Milestone 1 Data Pipeline
                       [data/normalized/*.json (16,481 records)]
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   ▼                                             ▼
               STORY-001                                     STORY-004
        (Data Contract Upgrades)                     (Redis Lua Fencing Locks)
                   │                                             │
                   ▼                                             │
               STORY-002                                         │
        (Identity Resolution IRS)                                │
                   │                                             │
                   ▼                                             │
               STORY-003                                         │
        (Dynamic Ontology Staging)                               │
                   │                                             │
                   └──────────────────────┬──────────────────────┘
                                          ▼
                                  ⛔ Sprint 1 Gate
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   ▼                                             ▼
               STORY-005                                     STORY-006
       (Pre-Commit Hydration)                       (LLM Factory & Cache)
                   │                                             │
                   └──────────────────────┬──────────────────────┘
                                          ▼
                                      STORY-007
                             (Neuro-Symbolic Detector)
                                          │
                                          ▼
                                      STORY-008
                               (Bayesian Log-Odds Arb)
                                          │
                                          ▼
                                      STORY-009
                                 (Full MPAC Rewrite)
                                          │
                                          ▼
                                      STORY-010
                              (Ad-Hoc & Ablation Suite)
                                          │
                                  ⛔ Sprint 2 Gate
                                          │
                                          ▼
                                      STORY-011
                                (FastMCP CTI Server)
                                          │
                                          ▼
                                      STORY-012
                              (Real MCP Client Manager)
                                          │
                                          ▼
                                      STORY-013
                             (A2A HTTP JSON-RPC Router)
                                          │
                                  ⛔ Sprint 3 Gate
                                          │
                                          ▼
                                      STORY-014
                         (Cyclic LangGraph StateGraph Agent)
                                          │
                                          ▼
                                      STORY-015
                        (Workflow Adapter & Agentic-KGR)
                                          │
                                  ⛔ Sprint 4 Gate
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   ▼                                             ▼
               STORY-016                                     STORY-017
         (Stratified GraphRAG)                          (FastAPI Gateway)
                   │                                             │
                   └──────────────────────┬──────────────────────┘
                                          ▼
                                      STORY-018
                            (5-Protocol Benchmark Harness)
                                          │
                                          ▼
                                 ⛔ Final Master Gate
                                      ✅ 100% DONE
```

---

## File Structure to Build

```text
multiagent_knowledgegraph/
├── src/
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── models.py                      ← STORY-001 (Upgraded edge fields, PeerAttestation)
│   ├── irs/                               ← NEW — STORY-002
│   │   ├── __init__.py
│   │   └── resolver.py                    ← IdentityResolutionService & alias resolution
│   ├── ontology/
│   │   ├── __init__.py
│   │   └── validator.py                   ← STORY-003 (Tier-2 Provisional staging)
│   ├── coordination/
│   │   ├── __init__.py
│   │   ├── base.py                        ← BaseCoordinator interface
│   │   ├── lock_manager.py                ← STORY-004 (Atomic acquire_fenced Lua)
│   │   ├── conflict_detector.py           ← STORY-007 (Neuro-Symbolic 3-Class Detector)
│   │   ├── arbitration_engine.py          ← STORY-008 (Laplace-Smoothed Bayesian Log-Odds)
│   │   ├── mpac.py                        ← STORY-009 (REWRITE: Full MPAC Protocol 2)
│   │   ├── adhoc.py                       ← STORY-010 (Uncoordinated edge writes)
│   │   └── ablation.py                    ← STORY-010 (Ablation coordinator modes)
│   ├── db/
│   │   └── neo4j_client.py                ← STORY-005 (Hydration query & Dual-Layer commits)
│   ├── mcp_servers/                       ← NEW — STORY-011 & 012
│   │   ├── __init__.py
│   │   ├── cti_mcp_server.py              ← FastMCP JSON-RPC server (stdio/sse)
│   │   └── mcp_client.py                  ← RealMCPClientManager (mcp.ClientSession)
│   ├── a2a/                               ← NEW — STORY-013
│   │   ├── __init__.py
│   │   └── peer_hub.py                    ← Real A2A HTTP router & LLM Verifier
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── llm_factory.py                 ← NEW — STORY-006 (LLM factory + SHA256 cache)
│   │   ├── investigator.py                ← NEW — STORY-014 (Cyclic LangGraph StateGraph)
│   │   ├── workflow.py                    ← STORY-015 (Backward-compatible adapter)
│   │   └── a2a.py                         ← STORY-015 (Legacy A2A compatibility adapter)
│   ├── graphrag/                          ← NEW — STORY-016
│   │   ├── __init__.py
│   │   └── retriever.py                   ← Stratified Top-K subquery retriever
│   ├── rag/
│   │   └── retriever.py                   ← Legacy GraphRAG adapter
│   ├── api/
│   │   └── main.py                        ← STORY-017 (FastAPI lifespan, 10 endpoints, A2A mount)
│   └── benchmark/                         ← NEW — STORY-018
│       ├── __init__.py
│       └── harness.py                     ← 5-protocol benchmark harness (GIR, CRA, PTC)
├── schemas/
│   └── bootstrap_ontology.json            ← Seed ontology definitions & alias tables
├── run_schema_init.py                     ← STORY-005 (Uniqueness constraints & composite indexes)
├── tests/
│   ├── test_models.py                     ← STORY-001 (Updated for edge fields & attestations)
│   ├── test_irs_resolver.py               ← NEW — STORY-002
│   ├── test_ontology_validator.py         ← STORY-003 (Updated for provisional staging)
│   ├── test_lock_manager.py               ← STORY-004 (Updated for fencing tokens)
│   ├── test_neo4j_client.py               ← STORY-005 (Updated for hydration queries)
│   ├── test_llm_factory.py                ← NEW — STORY-006
│   ├── test_conflict_detector.py          ← STORY-007 (Updated for Neuro-Symbolic 3-class)
│   ├── test_arbitration_engine.py         ← STORY-008 (Updated for Bayesian log-odds)
│   ├── test_mpac_coordinator.py           ← STORY-009 (Updated for rewritten MPAC)
│   ├── test_adhoc_coordinator.py          ← STORY-010
│   ├── test_ablation_coordinator.py       ← STORY-010
│   ├── test_cti_mcp_server.py             ← NEW — STORY-011
│   ├── test_mcp_client.py                 ← NEW — STORY-012
│   ├── test_a2a_peer_hub.py               ← NEW — STORY-013
│   ├── test_investigator.py               ← NEW — STORY-014
│   ├── test_graphrag_retriever.py         ← STORY-016
│   └── test_api_endpoints.py              ← STORY-017
├── data/
│   ├── cache/
│   │   └── llm_structured_cache.json      ← Content-addressed benchmark replay cache
│   └── results/
│       ├── benchmark_results.json         ← STORY-018
│       └── comparison_table.md            ← STORY-018
├── autonomoustechspec.md                  ← Master Technical Specification
└── new_taskbreakdown.md                   ← THIS FILE
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

| Member | Role | Status | Date |
|---|---|---|---|
| @member1 | Lead Systems Architect | **Approved** | 2026-11-15 |
| @member2 | Support Protocols Engineer | **Approved** | 2026-11-15 |
