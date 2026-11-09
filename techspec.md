# ProGRESS: Provenance-Grounded Multi-Agent Knowledge Graph Construction & Coordination System - Technical Design Specification

## Document Information

| Field | Details |
|---|---|
| Feature / Module | ProGRESS Core / Multi-Agent CTI Knowledge Graph Engine |
| Related PRD | [prd.md](file:///Users/sohithsai/multiagent_knowledgegraph/prd.md) |
| Date Created | 2026-10-12 |
| Last Updated | 2026-10-12 |
| Prepared By | Principal AI Systems Architect & CTI Research Engineer |
| Reviewers | Research Advisors, Distributed Systems Lead, Security Board |
| Status | Approved for Phase 2 Implementation |

> **Implementation status notice (2026-11-04):** The phase checklist below reflects the original October plan and is not a current completion record. Several components now exist, but tests and external-service verification differ from the planned state. See [RUNTIME.md](RUNTIME.md) for the current implementation map, reconciled dataset snapshot, and unverified integrations.

---

## 1. Overview

### 1.1 Purpose

This technical design specification details **HOW** we implement **ProGRESS** (Provenance-Grounded Multi-Agent Knowledge Graph Construction System). It establishes the complete end-to-end engineering blueprint for building:
1. **Four Principal-Bound Autonomous Agents** interfacing with heterogeneous Cyber Threat Intelligence (CTI) sources (**ThreatFox**, **URLhaus**, **MalwareBazaar**, and **AlienVault OTX**) via the **Model Context Protocol (MCP)**.
2. **Graph-Grounded Agent-to-Agent (A2A)** communication protocol based on **G²CP** for collaborative cross-verification of threat claims.
3. A shared, dual-layer **Neo4j Knowledge Graph** combining domain security topology with an epistemic provenance and conflict meta-graph.
4. The **`CoordinationAdapter` Framework** implementing and comparing **three distinct operational protocols**:
   - **Protocol 1: Ad-Hoc Protocol (Baseline / Control System):** Direct uncoordinated asynchronous mutations.
   - **Protocol 2: Full MPAC Protocol (Experimental System):** Multi-Principal Agent Coordination featuring Session Lifecycles, Intent Registration, Semantic Entity Locking, Pre-Commit Conflict Detection, and Authority/Confidence-Weighted Arbitration.
   - **Protocol 3: MPAC Ablation Protocol (Ablation Suite):** Isolated sub-protocol variants to scientifically prove which coordination mechanisms are causal.
5. An enterprise **FastAPI Gateway** exposing REST endpoints and WebSockets for downstream **GraphRAG analyst queries** and automated comparative benchmarking.

---

### 1.2 Background & Theoretical Foundations

CTI data is decentralized, high-volume, and frequently contradictory. When multiple agents independently assert facts about shared infrastructure (e.g., whether IP `185.220.101.4` is a `RedLine Stealer` or `AgentTesla` C2 server), uncoordinated database writes result in corrupted graph topology, overwritten confidence weights, and lost evidence provenance.

This specification translates core principles from six premier peer-reviewed research papers into an executable software architecture:
- **MPAC (*arXiv:2604.09744*):** Defines the formal state machine separating agent identity, principal authority, and shared mutable database state.
- **G²CP (*arXiv:2602.13370*):** Replaces unstructured agent chatter with graph-grounded structured claim tuples and verifiable subgraph exchanges.
- **Trust-Aware Traceability (*arXiv:2606.17203*):** Establishes an unbroken cryptographic-style provenance trail linking graph nodes back to authentic raw API dumps.
- **Agentic-KGR (*arXiv:2510.09156*):** Implements closed-loop feedback where arbitration decisions guide subsequent agent extraction.
- **GraphWorld (*OpenReview:xUDGChZsfG*):** Provides the shared collaborative environment model for multi-agent graph construction.
- **Decentralized State Governance (*SSRN:6837300*):** Supplies multi-principal dispute arbitration rules.

---

### 1.3 Scope & Implementation Phases

#### Phase 1: Data Ingestion & Normalization Foundation *(Completed & Verified)*
- [x] Live public bulk feed ingestion for ThreatFox, URLhaus, MalwareBazaar, and AlienVault OTX.
- [x] Standardized CTI record schema in [schemas/cti.py](file:///Users/sohithsai/multiagent_knowledgegraph/schemas/cti.py) incorporating `threat_type`, `status`, `reference_url`, `campaign`, `attack_ids`, and `aliases`.
- [x] Dual-mode execution (Live API mode + Offline replay fixtures in `data/fixtures/`).
- [x] High-volume empirical dataset generated: **16,270 normalized records**, **12,012 unique IOCs**, **259 cross-source overlaps**, and **63 verified conflicts**.
- [x] Automated incremental daily synchronization pipeline in [sync_daily.py](file:///Users/sohithsai/multiagent_knowledgegraph/sync_daily.py).

#### Phase 2: Neo4j Schema & CoordinationAdapter Engine *(Current Deliverable)*
- [ ] Neo4j Dual-Layer Graph Client (`src/db/neo4j_client.py`).
- [ ] `CoordinationAdapter` abstract base class and 3 protocol implementations:
  - `AdHocCoordinator` (`src/coordination/adhoc.py`)
  - `MPACCoordinator` (`src/coordination/mpac.py`)
  - `MPACAblationCoordinator` (`src/coordination/ablation.py`)
- [ ] Semantic In-Memory Entity Lock Manager (`src/coordination/lock_manager.py`).
- [ ] Multi-Principal Conflict Arbitration Engine (`src/coordination/arbitrator.py`).

#### Phase 3: Multi-Agent Workflow & Communication *(Next Deliverable)*
- [ ] MCP Tool Adapters for ThreatFox, URLhaus, MalwareBazaar, OTX (`src/mcp/tools.py`).
- [ ] G²CP-compliant Agent-to-Agent (A2A) peer communication hub (`src/agents/a2a.py`).
- [ ] LangGraph State Machine for Principal-Bound Agents (`src/agents/workflow.py`).

#### Phase 4: FastAPI Gateway & GraphRAG Pipeline *(Next Deliverable)*
- [ ] FastAPI Backend Service (`src/api/main.py`) exposing `/query`, `/graph`, `/conflicts`, `/provenance`, and `/benchmark`.
- [ ] Neo4j GraphRAG Context Retriever & Evidence Synthesizer (`src/rag/retriever.py`).

#### Phase 5: Automated Benchmarking & Evaluation Suite *(Final Deliverable)*
- [ ] Head-to-Head Comparative Benchmark Harness running identical workloads across Protocols 1, 2, and 3 (`benchmark/runner.py`).
- [ ] Metric visualizer generating publication-ready tables and charts for $GIR$, $CRA$, $PTC$, and latency.

---

## 2. Architecture & Data Flow Specification

### 2.1 Component Data Flow & Architecture Diagrams

```text
DIAGRAM A: DATA INGESTION & DUAL-MODE NORMALIZATION PIPELINE (PHASE 1)
================================================================================
           ThreatFox API             URLhaus API          MalwareBazaar API       AlienVault OTX API
       (threatfox.abuse.ch)      (urlhaus.abuse.ch)       (bazaar.abuse.ch)      (otx.alienvault.com)
                 │                         │                      │                       │
                 ▼                         ▼                      ▼                       ▼
       ┌───────────────────┐     ┌───────────────────┐  ┌───────────────────┐   ┌───────────────────┐
       │ ThreatFoxSource   │     │ URLhausSource     │  │MalwareBazaarSource│   │ OTXSource         │
       │ (JSON Bulk Export)│     │ (JSON Recent Export│  │ (CSV Export Feed) │   │ (Subscribed Pulse)│
       └─────────┬─────────┘     └─────────┬─────────┘  └─────────┬─────────┘   └─────────┬─────────┘
                 │                         │                      │                       │
                 ├─────────────────────────┼──────────────────────┼───────────────────────┤
                 ▼                         ▼                      ▼                       ▼
            [data/raw/]               [data/raw/]            [data/raw/]             [data/raw/]
          threatfox.json             urlhaus.json        malwarebazaar.json           otx.json
                 │                         │                      │                       │
                 └─────────────────────────┼──────────────────────┼───────────────────────┘
                                           ▼
                             ┌───────────────────────────┐
                             │   schemas/cti.py          │
                             │   NormalizedCTIRecord     │
                             │  - ioc_type & ioc_value   │
                             │  - malware_family         │
                             │  - threat_type & status   │
                             │  - attack_ids (MITRE)     │
                             │  - reference_url (Proof)  │
                             └─────────────┬─────────────┘
                                           ▼
                                  [data/normalized/]
                            ├── threatfox.json     (3,000 records)
                            ├── urlhaus.json      (10,000 records)
                            ├── malwarebazaar.json (1,536 records)
                            ├── otx.json           (1,734 records)
                            └── normalized_cti.json (16,270 records)
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
             [analysis/overlap.py]                 [analysis/conflict.py]
             Cross-Source Overlaps                 Attribution & Confidence
             (259 shared IOCs)                     Disputes (63 conflicts)
```

```text
DIAGRAM B: MULTI-AGENT EXECUTION, A2A PEER QUERYING & COORDINATION SUBMISSION
================================================================================
                               Normalized Task Packages
                                (from data/normalized/)
                                           │
         ┌───────────────────┬─────────────┴───────┬───────────────────┐
         ▼                   ▼                     ▼                   ▼
   [Principal A]       [Principal B]         [Principal C]       [Principal D]
    (ThreatFox)         (URLhaus)           (MalwareBazaar)         (OTX)
         │                   │                     │                   │
         ▼                   ▼                     ▼                   ▼
   ┌───────────┐       ┌───────────┐         ┌───────────┐       ┌───────────┐
   │  AGENT A  │       │  AGENT B  │         │  AGENT C  │       │  AGENT D  │
   │ LangGraph │       │ LangGraph │         │ LangGraph │       │ LangGraph │
   └─────┬─────┘       └─────┬─────┘         └─────┬─────┘       └─────┬─────┘
         │                   │                     │                   │
         │ [MCP Tool]        │ [MCP Tool]          │ [MCP Tool]        │ [MCP Tool]
         ▼                   ▼                     ▼                   ▼
     Fetch IOC           Fetch URL             Fetch Hash          Fetch Pulse
         │                   │                     │                   │
         ▼                   ▼                     ▼                   ▼
    Extract Claim       Extract Claim         Extract Claim       Extract Claim
         │                   │                     │                   │
         └───────────── G²CP Graph-Grounded Peer Verification ─────────┘
                       (Agent A queries Agent B & D: "Verify IP 185.x.x.x")
                                           │
                                           ▼
                             Assemble GraphOperation Payload
                                           │
                                           ▼
                                 CoordinationAdapter
                                           │
                 ┌─────────────────────────┼─────────────────────────┐
                 ▼                         ▼                         ▼
         [PROTOCOL 1]              [PROTOCOL 2]              [PROTOCOL 3]
       Ad-Hoc Coordinator       Full MPAC Coordinator     MPAC Ablation Suite
       (Baseline Control)       (Formal Governance)       (Causal Analysis)
```

```text
DIAGRAM C: THE THREE COORDINATION PROTOCOLS & NEO4J WRITES
================================================================================
           PROTOCOL 1: AD-HOC                  PROTOCOL 2: FULL MPAC               PROTOCOL 3: ABLATION
     ┌────────────────────────────┐       ┌────────────────────────────┐       ┌────────────────────────────┐
     │ Receive GraphOperation     │       │ 1. Open Agent Session      │       │ Configurable Ablation:     │
     └─────────────┬──────────────┘       │ 2. Register Write Intent   │       │ - Ablation A: No A2A       │
                   │                      └─────────────┬──────────────┘       │ - Ablation B: No Locks     │
                   ▼                                    ▼                      │ - Ablation C: Unweighted   │
     ┌────────────────────────────┐       ┌────────────────────────────┐       └─────────────┬──────────────┘
     │ Direct Parallel Cypher:    │       │ 3. Semantic Entity Lock    │                     │
     │ MERGE (m:Malware)-[:C2]->IP│       │    (Lock key: "ip:185.x")  │                     ▼
     └─────────────┬──────────────┘       └─────────────┬──────────────┘       ┌────────────────────────────┐
                   │                                    ▼                      │ Sub-Protocol Path          │
                   ▼                      ┌────────────────────────────┐       └─────────────┬──────────────┘
     [Consequences of No Lock:]           │ 4. Pre-Commit Conflict Det.│                     │
     - Property Overwrites                │    Check active graph for  │                     │
     - Duplicate Edges                    │    divergent attributions  │                     │
     - Zero Claim Provenance              └─────────────┬──────────────┘                     │
     - Unrecorded Contradictions                        │                                    │
                   │                             Conflict Found?                             │
                   │                             ┌──────┴──────┐                             │
                   │                             │             │                             │
                   │                          [Yes]           [No]                           │
                   │                             ▼             ▼                             │
                   │                 ┌───────────────┐ ┌───────────────┐                     │
                   │                 │ 5. Arbitration│ │ Skip Arbitrate│                     │
                   │                 │ - Weight diff │ └───────┬───────┘                     │
                   │                 │ - Consensus   │         │                             │
                   │                 └───────┬───────┘         │                             │
                   │                         └────────┬────────┘                             │
                   │                                  ▼                                      │
                   │                      ┌────────────────────────────┐                     │
                   │                      │ 6. Atomic Neo4j Write:     │                     │
                   │                      │ - Domain Nodes & Edges     │                     │
                   │                      │ - Claim & Evidence Nodes   │                     │
                   │                      │ - Decision & Conflict Nodes│                     │
                   │                      └─────────────┬──────────────┘                     │
                   │                                    ▼                                    │
                   │                      ┌────────────────────────────┐                     │
                   │                      │ 7. Release Entity Lock     │                     │
                   │                      │ 8. Close Session           │                     │
                   │                      └─────────────┬──────────────┘                     │
                   │                                    │                                    │
                   ▼                                    ▼                                    ▼
       ┌──────────────────────┐             ┌──────────────────────┐             ┌──────────────────────┐
       │   Neo4j Ad-Hoc KG    │             │   Neo4j MPAC KG      │             │  Neo4j Ablated KG    │
       │ (Unchecked Race Cond)│             │ (Full Provenance KG) │             │ (Partial Governance) │
       └──────────────────────┘             └──────────────────────┘             └──────────────────────┘
```

---

### 2.2 Module Specifications: Inputs, Outputs & Core Functions

| Module / Class | Component File | Core Technical Function | Inputs | Outputs |
|---|---|---|---|---|
| **`ThreatFoxSource`** | `src/sources/threatfox.py` | Connects to ThreatFox public export feed, normalizes raw JSON into standard schema. | `limit: int` (default 3000) | `List[NormalizedCTIRecord]` |
| **`URLhausSource`** | `src/sources/urlhaus.py` | Ingests URLhaus JSON feeds, parses URL and host IPs into dual records with status. | `limit: int` (default 5000) | `List[NormalizedCTIRecord]` |
| **`MalwareBazaarSource`** | `src/sources/malwarebazaar.py` | Parses MalwareBazaar CSV feeds, extracts binary sample hashes, signatures, and MIME types. | `limit: int` (default 1000) | `List[NormalizedCTIRecord]` |
| **`OTXSource`** | `src/sources/otx.py` | Queries AlienVault OTX pulses, extracts threat actors, pulse campaigns, and MITRE technique IDs. | `limit: int` (default 50 pulses) | `List[NormalizedCTIRecord]` |
| **`SemanticLockManager`** | `src/coordination/lock_manager.py` | Redis distributed locking mechanism (`SETNX` with TTL, plus async in-memory test fallback) on entity keys (`ip:<val>`, `malware:<val>`). | `entity_keys: List[str]`, `timeout_ms: int = 5000` | `LockToken` or `TimeoutException` |
| **`ConflictDetector`** | `src/coordination/detector.py` | Scans current Neo4j state and active intents to detect attribution contradictions or confidence divergence. | `operation: GraphOperation`, `neo4j_session` | `ConflictEvaluationResult` (`has_conflict: bool`, details) |
| **`ArbitrationEngine`** | `src/coordination/arbitrator.py` | Applies mathematical weighting ($W = \alpha \cdot \text{Auth} + \beta \cdot \text{Conf}$) to resolve disputes. | `existing_claim: Claim`, `new_claim: Claim` | `ArbitrationDecision` (`winner_claim`, `status`, rationale) |
| **`OntologyValidator`** | `src/ontology/validator.py` | Guards the Two-Tier Hybrid Ontology (Section 3.4). Checks LLM-proposed entity/relationship types against Tier 1 anchor types via exact match, then semantic similarity (cosine threshold ≥ 0.85 → MERGE). If genuinely new and ≥ 2 agents confirm → APPROVE; else → REJECT. | `proposed_term: str`, `term_type: str`, `peer_confirmations: int` | `OntologyValidationResult` (`decision: MERGE/APPROVE/REJECT`, `target_type`, `term_id`) |
| **`AdHocCoordinator`** | `src/coordination/adhoc.py` | Implements Protocol 1. Executes parallel async Cypher writes directly to Neo4j without locking. | `operation: GraphOperation` | `CoordinationResult` (`status: "COMMITTED"`, latency) |
| **`MPACCoordinator`** | `src/coordination/mpac.py` | Implements Protocol 2. Full MPAC protocol engine with session lifecycle, locking, arbitration, and provenance. | `operation: GraphOperation` | `CoordinationResult` (`status: "ACCEPTED" | "RESOLVED"`, provenance_ids) |
| **`MPACAblationCoordinator`** | `src/coordination/ablation.py` | Implements Protocol 3. Executes parameterized ablation runs (`no_a2a`, `no_locks`, `no_weighting`). | `operation: GraphOperation`, `ablation_mode: str` | `CoordinationResult` with ablation telemetry |
| **`G2CPPeerHub`** | `src/agents/a2a.py` | Facilitates structured graph-grounded peer inquiries and consensus evidence exchange between agents. | `query: A2AQuery` (`target_ioc`, `subject`) | `A2AResponse` (`subgraph_evidence`, `confidence_vote`) |
| **`LangGraphAgent`** | `src/agents/workflow.py` | State machine governing agent execution loop: Receive $\rightarrow$ Retrieve $\rightarrow$ Extract $\rightarrow$ **OntologyValidate** $\rightarrow$ A2A Peer Check $\rightarrow$ Submit. | `task_package: TaskPackage` | `List[CoordinationResult]` |
| **`Neo4jClient`** | `src/db/neo4j_client.py` | Connection pool manager, schema index initialization, Cypher query executor for domain and meta-nodes. | Cypher query string, parameters | Query results / Graph records |
| **`GraphRAGRetriever`** | `src/rag/retriever.py` | Extracts query entities, expands 2-hop graph neighborhood in Neo4j, formats LLM evidence-backed answers. | `natural_language_query: str` | `AnalystAnswer` (`answer_text`, `evidence_subgraph`, `conflicts`) |
| **`BenchmarkRunner`** | `benchmark/runner.py` | Orchestrates head-to-head evaluation across Protocols 1, 2, and 3 under identical concurrent workloads. | `dataset_path: str`, `concurrency_level: int` | `BenchmarkReport` ($GIR$, $CRA$, $PTC$, latency, token metrics) |

---

### 2.3 Detailed Request-Response Sequence Diagram (MPAC Execution Loop)

The following sequence details the operational lifecycle of a CTI write transaction through the full MPAC protocol:

```text
Worker Agent        G²CP Peer Hub      MPAC Coordinator     Lock Manager     Neo4j Database     Conflict Detector    Arbitrator
     │                     │                  │                  │                  │                   │                 │
     │ 1. Extract Claim    │                  │                  │                  │                   │                 │
     │    (185.x, RedLine) │                  │                  │                  │                   │                 │
     ├────────────────────►│                  │                  │                  │                   │                 │
     │                     │ 2. Query Peers   │                  │                  │                   │                 │
     │                     │    for IOC 185.x │                  │                  │                   │                 │
     │                     │◄─────────────────┤                  │                  │                   │                 │
     │ 3. A2A Response:    │                  │                  │                  │                   │                 │
     │    Vote=CONFIRM     │                  │                  │                  │                   │                 │
     │◄────────────────────┤                  │                  │                  │                   │                 │
     │                     │                  │                  │                  │                   │                 │
     │ 4. Submit GraphOperation               │                  │                  │                   │                 │
     ├───────────────────────────────────────►│                  │                  │                   │                 │
     │                                        │ 5. Acquire Lock  │                  │                   │                 │
     │                                        │    ("ip:185.x")  │                  │                   │                 │
     │                                        ├─────────────────►│                  │                   │                 │
     │                                        │◄─────────────────┤                  │                   │                 │
     │                                        │ Lock Granted     │                  │                   │                 │
     │                                        │                  │                  │                   │                 │
     │                                        │ 6. Query Existing State             │                   │                 │
     │                                        ├────────────────────────────────────►│                   │                 │
     │                                        │◄────────────────────────────────────┤                   │                 │
     │                                        │ Existing: (185.x, AgentTesla, C=70) │                   │                 │
     │                                        │                                     │                   │                 │
     │                                        │ 7. Check for Semantic Conflict      │                   │                 │
     │                                        ├────────────────────────────────────────────────────────►│                 │
     │                                        │                                                         │ 8. Divergence   │
     │                                        │                                                         │    Detected!    │
     │                                        │◄────────────────────────────────────────────────────────┤                 │
     │                                        │ Conflict Flagged: Attribution Mismatch                  │                 │
     │                                        │                                                                           │
     │                                        │ 9. Invoke Formal Arbitration                                              │
     │                                        ├──────────────────────────────────────────────────────────────────────────►│
     │                                        │                                                                           │ 10. Compute:
     │                                        │                                                                           │ W1 vs W2
     │                                        │◄──────────────────────────────────────────────────────────────────────────┤
     │                                        │ Decision: Accept RedLine; Quarantine AgentTesla                           │
     │                                        │                                                                           │
     │                                        │ 11. Atomic Commit: Domain Nodes + Claim + Decision + Conflict             │
     │                                        ├────────────────────────────────────►│                                     │
     │                                        │◄────────────────────────────────────┤                                     │
     │                                        │ Transaction Committed               │                                     │
     │                                        │                                     │                                     │
     │                                        │ 12. Release Lock                    │                                     │
     │                                        ├─────────────────►│                  │                                     │
     │                                        │◄─────────────────┤                  │                                     │
     │ 13. Coordination Result                │                  │                  │                                     │
     │     (Status: ACCEPTED, Provenance IDs) │                  │                  │                                     │
     │◄───────────────────────────────────────┤                  │                  │                                     │
```

---

### 2.4 Memory-Bounded Streaming Ingestion Pipeline (Phase 1 Optimization)

ThreatFox's live bulk export (`https://threatfox.abuse.ch/export/json/recent/`) contains 20,000+ indicators of compromise. Loading the raw uncompressed JSON payload into memory using standard `resp.json()` creates a severe memory bottleneck:
1. **Memory Inflation:** In CPython, small dictionary objects and nested lists incur 4x to 8x memory inflation. A 40 MB raw JSON export bloats into 300 MB–600 MB of heap memory.
2. **Worker Crashes:** When multi-agent worker processes run concurrently or within memory-constrained containers (e.g., 512 MB – 1 GB RAM limits), full JSON deserialization triggers the Linux Out-Of-Memory (OOM) killer.

To guarantee bounded $O(1)$ memory overhead and zero worker crashes, `ThreatFoxSource` implements an incremental streaming ingestion pipeline:

```text
  [ ThreatFox Live Endpoint: /export/json/recent/ ]
                         │
                         ▼  (HTTP Chunked Socket Stream)
          [ httpx.stream("GET", ...) / aiter_bytes() ]
                         │
                         ▼  (Incremental Token-by-Token Parsing)
          [ ijson.kvitems() Streaming Parser ]
                         │
        ┌────────────────┴────────────────┐
        ▼ (Yield single (ioc_id, item))   ▼ (Limit Reached: count >= 3000)
  [ Inline Normalization ]          [ Short-Circuit Socket ]
  NormalizedCTIRecord yielded       Stream connection closed early.
  Peak RAM: < 15 MB                 Remaining 80% payload unread.
```

```python
# Streaming ingestion pattern for ThreatFoxSource
import httpx
import ijson
from typing import Iterator
from schemas.cti import NormalizedCTIRecord

class ThreatFoxStreamSource:
    def stream_fetch_and_normalize(self, limit: int = 3000) -> Iterator[NormalizedCTIRecord]:
        export_url = "https://threatfox.abuse.ch/export/json/recent/"
        headers = {"User-Agent": "ProGRESS-CTI-Research/1.0"}
        count = 0

        with httpx.Client(timeout=60.0) as client:
            with client.stream("GET", export_url, headers=headers) as response:
                response.raise_for_status()
                # ijson.kvitems parses top-level dictionary key-value pairs incrementally
                for ioc_id, items in ijson.kvitems(response.iter_bytes(), ""):
                    item_list = items if isinstance(items, list) else [items]
                    for item in item_list:
                        item["id"] = ioc_id
                        normalized_records = self.normalize_record(item)
                        for record in normalized_records:
                            yield record
                            count += 1
                            if limit > 0 and count >= limit:
                                return  # Immediately closes socket and terminates stream
```

**Key Performance Benefits:**
- **Constant Memory Footprint:** RAM consumption remains strictly bounded under **15 MB** regardless of whether the feed has 3,000 or 100,000 records.
- **Early Socket Termination:** The moment the record limit (e.g., 3,000) is reached, the connection is closed immediately, eliminating the need to download the remaining 80% of unused network data.
- **Chunked Persistence:** Downstream normalization writes to disk or Neo4j in fixed-size batches (e.g., 500 records) with explicit garbage collection, eliminating intermediate object accumulation.

---

## 3. Data & Graph Design

### 3.1 Neo4j Dual-Layer Graph Topology

The database enforces a strict separation between **Domain Entities** (the actual malware intelligence) and the **Provenance Meta-Layer** (the governance records of who asserted what, when, and how disputes were arbitrated).

> **Forward Compatibility:** Every node carries a `node_schema_version` string property (default `"1.0"`) and every relationship carries a `relationship_schema_version` string property. When the Two-Tier Dynamic Ontology (Section 3.4) promotes a new LLM-proposed type into the stable core, it is stamped `"2.0"` or higher. This allows Cypher queries to differentiate between original core types and future extended types without breaking existing traversals.

```cypher
// ==========================================
// LAYER 1: DOMAIN ENTITIES & RELATIONSHIPS (Tier 1 — Stable Core Ontology, schema_version="1.0")
// ==========================================
(:ThreatActor {id: STRING, name: STRING, aliases: LIST<STRING>, node_schema_version: STRING})
(:Campaign {id: STRING, name: STRING, node_schema_version: STRING})        // e.g., Twitch OAuth Campaign
(:Malware {id: STRING, name: STRING, aliases: LIST<STRING>, first_seen: STRING, node_schema_version: STRING})
(:IP {value: STRING, is_ipv4: BOOLEAN, node_schema_version: STRING})
(:Domain {value: STRING, node_schema_version: STRING})
(:URL {value: STRING, status: STRING, node_schema_version: STRING})
(:FileHash {sha256: STRING, md5: STRING, mime_type: STRING, node_schema_version: STRING})
(:AttackTechnique {id: STRING, name: STRING, node_schema_version: STRING}) // e.g., T1071.001

// Domain Edges with Temporal Lifecycles (all carry relationship_schema_version: STRING)
(:ThreatActor)-[:OPERATES_CAMPAIGN {valid_from: STRING, valid_until: STRING, relationship_schema_version: STRING}]->(:Campaign)
(:ThreatActor)-[:USES_MALWARE {confidence: INT, relationship_schema_version: STRING}]->(:Malware)
(:Campaign)-[:DEPLOYS_MALWARE {valid_from: STRING, valid_until: STRING, relationship_schema_version: STRING}]->(:Malware)
(:Malware)-[:USES_C2 {confidence: INT, status: STRING, valid_from: STRING, valid_until: STRING, is_active: BOOLEAN, relationship_schema_version: STRING}]->(:IP)
(:Malware)-[:USES_C2 {confidence: INT, valid_from: STRING, valid_until: STRING, relationship_schema_version: STRING}]->(:Domain)
(:Malware)-[:DISTRIBUTED_VIA {valid_from: STRING, valid_until: STRING, relationship_schema_version: STRING}]->(:URL)
(:URL)-[:HOSTED_ON {valid_from: STRING, valid_until: STRING, relationship_schema_version: STRING}]->(:IP)
(:Malware)-[:HAS_SAMPLE {relationship_schema_version: STRING}]->(:FileHash)
(:Malware)-[:USES_TECHNIQUE {relationship_schema_version: STRING}]->(:AttackTechnique)

// ==========================================
// LAYER 2: PROVENANCE & GOVERNANCE META-LAYER
// ==========================================
(:Principal {id: STRING, name: STRING, authority_weight: FLOAT})
(:Agent {id: STRING, principal_id: STRING})
(:Evidence {id: STRING, source: STRING, record_id: STRING, reference_url: STRING, raw_hash: STRING, timestamp: STRING})
(:Claim {id: STRING, subject: STRING, predicate: STRING, object: STRING, confidence: INT, asserted_at: STRING})
(:Conflict {id: STRING, conflict_type: STRING, detected_at: STRING, resolved: BOOLEAN})
(:Decision {id: STRING, winning_claim_id: STRING, rationale: STRING, arbitrated_at: STRING})

// Ontology Extension Governance Node (added to Layer 2 — see Section 3.4)
(:OntologyTerm {
    term_id: STRING,           // "term-cryptowallet-001"
    term_name: STRING,         // "CryptoWallet" or "ACCEPTS_PAYMENT_VIA"
    term_type: STRING,         // "NODE_LABEL" or "RELATIONSHIP_TYPE"
    proposed_by: STRING,       // "Agent-OTX"
    proposed_at: STRING,       // ISO timestamp
    status: STRING,            // "PROPOSED" | "PENDING" | "APPROVED" | "REJECTED" | "MERGED_INTO"
    merged_into: STRING,       // e.g., "Domain" if rejected and merged
    example_usage: STRING,     // Natural language description of the new concept
    approval_count: INT,       // Number of agents that confirmed this pattern
    schema_version_assigned: STRING  // Version stamped on nodes/edges using this term
})

// Meta-Layer Relationships
(:Agent)-[:REPRESENTS]->(:Principal)
(:Agent)-[:ASSERTS]->(:Claim)
(:Claim)-[:GROUNDED_IN]->(:Evidence)
(:Claim)-[:GOVERNS]->(:Malware)
(:Claim)-[:CONFLICTS_WITH]->(:Claim)
(:Decision)-[:RESOLVED_CONFLICT]->(:Conflict)
(:Decision)-[:VALIDATES_CLAIM]->(:Claim)
(:Agent)-[:PROPOSED_TERM]->(:OntologyTerm)
(:OntologyTerm)-[:APPROVED_BY]->(:Agent)
```

---

### 3.2 Concrete Cypher Node Constraints & Indexes

To ensure sub-millisecond retrieval and prevent duplicate nodes under concurrency, Neo4j indexes must be created upon system initialization:

```cypher
// Unique Constraints — All 8 Tier 1 Core Entity Types
CREATE CONSTRAINT cst_malware_name IF NOT EXISTS FOR (m:Malware) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT cst_threat_actor_name IF NOT EXISTS FOR (a:ThreatActor) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT cst_campaign_id IF NOT EXISTS FOR (c:Campaign) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT cst_ip_value IF NOT EXISTS FOR (i:IP) REQUIRE i.value IS UNIQUE;
CREATE CONSTRAINT cst_domain_value IF NOT EXISTS FOR (d:Domain) REQUIRE d.value IS UNIQUE;
CREATE CONSTRAINT cst_url_value IF NOT EXISTS FOR (u:URL) REQUIRE u.value IS UNIQUE;
CREATE CONSTRAINT cst_hash_sha256 IF NOT EXISTS FOR (h:FileHash) REQUIRE h.sha256 IS UNIQUE;
CREATE CONSTRAINT cst_technique_id IF NOT EXISTS FOR (t:AttackTechnique) REQUIRE t.id IS UNIQUE;

// Unique Constraints — Provenance & Governance Meta-Layer
CREATE CONSTRAINT cst_claim_id IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT cst_evidence_id IF NOT EXISTS FOR (e:Evidence) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT cst_principal_id IF NOT EXISTS FOR (p:Principal) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT cst_conflict_id IF NOT EXISTS FOR (cf:Conflict) REQUIRE cf.id IS UNIQUE;
CREATE CONSTRAINT cst_decision_id IF NOT EXISTS FOR (dc:Decision) REQUIRE dc.id IS UNIQUE;

// Unique Constraint — Ontology Extension Registry (Section 3.4)
CREATE CONSTRAINT cst_ontology_term_id IF NOT EXISTS FOR (o:OntologyTerm) REQUIRE o.term_id IS UNIQUE;

// Composite Query Indexes
CREATE INDEX idx_claim_subject_predicate IF NOT EXISTS FOR (c:Claim) ON (c.subject, c.predicate);
CREATE INDEX idx_evidence_source_record IF NOT EXISTS FOR (e:Evidence) ON (e.source, e.record_id);
// Ontology term lookup index (for fast semantic similarity checks)
CREATE INDEX idx_ontology_term_name IF NOT EXISTS FOR (o:OntologyTerm) ON (o.term_name, o.status);
```

---

### 3.3 Core Pydantic Data Contracts

All data flowing between agents, coordinators, and databases adheres to strict Pydantic v2 schemas:

```python
# src/schemas/models.py
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Claim(BaseModel):
    claim_id: str = Field(..., description="Unique deterministic hash of subject+predicate+object+principal+evidence_id+timestamp")
    subject: str = Field(..., description="Subject entity (e.g. RedLine, 185.x.x.x)")
    predicate: str = Field(..., description="Predicate relationship (USES_C2, DISTRIBUTED_VIA, HOSTED_ON)")
    object: str = Field(..., description="Target entity value")
    confidence: int = Field(..., ge=0, le=100, description="Confidence score standardized to 0-100")
    evidence_id: str = Field(..., description="Reference ID to the originating CTI record")
    timestamp: str = Field(..., description="ISO 8601 assertion timestamp (e.g. 2026-10-12T10:00:00Z)")
    timestamp_epoch: int = Field(..., description="Unix epoch timestamp in seconds for numeric temporal analysis")

    @classmethod
    def generate_id(cls, subject: str, predicate: str, obj: str, principal: str, evidence_id: str, timestamp_iso: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(f"{subject}:{predicate}:{obj}:{principal}:{evidence_id}:{timestamp_iso}".encode("utf-8"))
        return f"clm-{hasher.hexdigest()[:16]}"

class GraphOperation(BaseModel):
    operation_id: str
    principal_id: str              # "Principal-ThreatFox", "Principal-URLhaus", etc.
    agent_id: str                  # "Agent-01", etc.
    intent_type: str               # "ADD_RELATION", "UPDATE_CONFIDENCE", "QUARANTINE"
    target_claim: Claim
    lock_keys: List[str]           # Enforced dual-entity sorted lock keys (e.g. ["ip:185.x", "malware:redline"])
    evidence_payload: Dict[str, Any]

    @field_validator('lock_keys')
    @classmethod
    def enforce_deterministic_lock_sorting(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("lock_keys cannot be empty")
        # Enforces unique, strictly sorted keys at schema boundary to eliminate circular deadlocks
        return sorted(list(set(v)))

class ArbitrationDecision(BaseModel):
    decision_id: str
    conflict_id: str
    winning_claim_id: str
    losing_claim_id: str
    status: str                    # "RESOLVED", "SPLIT_ATTRIBUTION", "REJECTED"
    rationale: str
    arbitrated_at: str

class CoordinationResult(BaseModel):
    operation_id: str
    protocol: str                  # "AD_HOC", "MPAC", "MPAC_ABLATION"
    status: str                    # "COMMITTED", "ACCEPTED", "CONFLICT_DETECTED", "REJECTED"
    latency_ms: float
    lock_wait_ms: float = 0.0
    conflict_detected: bool = False
    decision: Optional[ArbitrationDecision] = None
    affected_nodes: List[str] = []
```

---

### 3.4 Two-Tier Dynamic Ontology Architecture

The schema is designed to be **stable at the core but extensible at the edges**. This eliminates both the brittleness of a fully-fixed schema (breaks when new data types arrive) and the chaos of fully-dynamic LLM-generated types (causes ontology fragmentation and broken Cypher queries).

#### The Core Problem

CTI data evolves. Threat actors start using **cryptocurrency wallets**, **Telegram channels**, **cloud storage buckets (AWS S3)**, or **new MITRE ATT&CK sub-techniques** that did not exist when the schema was first written. If agents are forced to always use the existing 8 Tier 1 node types, real intelligence is lost. But if the LLM freely invents new types, this happens:

```text
  Agent-ThreatFox creates:  (Malware)-[:USES_C2]->(IP)           ← Tier 1 type
  Agent-OTX       creates:  (Malware)-[:CONNECTS_TO_C2_SERVER]->(IP)  ← Hallucinated duplicate
  Agent-URLhaus   creates:  (Malware)-[:uses_c2_infrastructure]->(IP) ← Another duplicate
  Agent-Bazaar    creates:  (Malware)-[:C2_CONNECTION]->(IPAddress)    ← Wrong node label too
```

Four agents, four representations of the same fact. Cypher queries break. GIR metric cannot count corrupted edges. GraphRAG cannot traverse reliably. This is called **ontology fragmentation**.

#### The Two-Tier Solution

```text
╔══════════════════════════════════════════════════════════════════════════╗
║  TIER 1: STABLE CORE ONTOLOGY  (node_schema_version = "1.0")            ║
║  Fixed. Schema-enforced. All 4 agents always use these exact labels.     ║
║                                                                          ║
║  NODE TYPES:         Malware, IP, Domain, URL, FileHash,                 ║
║                      ThreatActor, Campaign, AttackTechnique              ║
║  RELATIONSHIP TYPES: USES_C2, DISTRIBUTED_VIA, HOSTED_ON,               ║
║                      USES_TECHNIQUE, HAS_SAMPLE, OPERATES_CAMPAIGN      ║
╚══════════════════════════════════════════════════════════════════════════╝
                              │
              When LLM encounters a concept that does NOT fit any Tier 1 type:
                              ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  TIER 2: DYNAMIC EXTENSION LAYER  (LLM-Proposed, Registry-Gated)        ║
║                                                                          ║
║  Step 1 — LLM Extraction:                                                ║
║    Agent-OTX extracts: "RedLine uses BTC wallet 1A2B3C... for ransom"   ║
║    No Tier 1 type matches "CryptoWallet"                                  ║
║                                                                          ║
║  Step 2 — OntologyValidator Check (src/ontology/validator.py):           ║
║    Query OntologyRegistry: Does "CryptoWallet" already exist? → NO       ║
║    Run semantic similarity against known terms (cosine similarity):       ║
║      "CryptoWallet" vs "Domain"  → similarity: 0.12  (too different)     ║
║      "CryptoWallet" vs "FileHash" → similarity: 0.21 (too different)     ║
║    Decision: GENUINELY NEW TYPE — initiate approval flow                  ║
║                                                                          ║
║  Step 3 — Multi-Agent Consensus Vote:                                    ║
║    All 4 agents queried: "Have you seen CryptoWallet-like entities?"     ║
║    Votes: OTX=YES, ThreatFox=YES, Bazaar=NO_DATA, URLhaus=NO_DATA        ║
║    approval_count = 2 ≥ threshold (2) → STATUS: APPROVED                 ║
║                                                                          ║
║  Step 4 — Write to OntologyRegistry + Create Node:                      ║
║    New (:OntologyTerm {term_name: "CryptoWallet", status: "APPROVED",   ║
║         schema_version_assigned: "2.0"}) created                         ║
║    New (:CryptoWallet {address: "1A2B3C...", node_schema_version: "2.0"})║
║    New (:Malware)-[:ACCEPTS_PAYMENT_VIA {relationship_schema_version:    ║
║         "2.0"}]->(:CryptoWallet)                                         ║
╚══════════════════════════════════════════════════════════════════════════╝
```

#### Four Decision Paths in the OntologyValidator

> **Category-Aware Similarity:** Similarity comparison is always performed within the same category — entity types are compared against Tier 1 entity types, and relationship types are compared against Tier 1 relationship types. A proposed entity type is never merged into a relationship type regardless of cosine score.

| Scenario | Condition | Action | Example |
|---|---|---|---|
| **MERGE** | Semantic similarity ≥ 0.85 to existing Tier 1 type **of the same category** | Map to existing type; no new term created | "CONNECTS_TO_C2_SERVER" → `USES_C2` |
| **APPROVE** | Genuinely new concept, ≥ 2 distinct agents confirm the pattern | Create `(:OntologyTerm {status: "APPROVED"})` + new node/relationship type with `schema_version="2.0"` | `CryptoWallet`, `CloudStorage`, `TelegramChannel` |
| **PENDING** | Genuinely new concept but only 1 agent has confirmed so far | Create `(:OntologyTerm {status: "PENDING"})` as a provisional record; no domain node created yet; stays open for more confirmations | A new C2 channel type seen in only one feed |
| **REJECT** | Semantically malformed, provably duplicate, or zero agent confirmations | Create `(:OntologyTerm {status: "REJECTED"})` as audit record; claim dropped | Pure hallucination with no evidence |

#### OntologyValidator Implementation

```python
# src/ontology/validator.py
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class OntologyDecision(str, Enum):
    MERGE = "MERGE"        # Map to existing Tier 1 type — use it directly
    APPROVE = "APPROVE"    # New genuine concept — register and create
    REJECT = "REJECT"      # Hallucination or insufficient evidence — discard

@dataclass
class OntologyValidationResult:
    decision: OntologyDecision
    target_type: str                  # For MERGE: the existing Tier 1 type to use
    term_id: Optional[str] = None    # For APPROVE: the new OntologyTerm ID
    similarity_score: float = 0.0    # Cosine similarity against nearest Tier 1 type
    approval_count: int = 0          # Number of agents that confirmed the pattern
    rationale: str = ""

class OntologyValidator:
    # Tier 1 anchor types — NEVER dynamically modified
    TIER1_NODE_TYPES = {
        "Malware", "IP", "Domain", "URL", "FileHash",
        "ThreatActor", "Campaign", "AttackTechnique"
    }
    TIER1_RELATIONSHIP_TYPES = {
        "USES_C2", "DISTRIBUTED_VIA", "HOSTED_ON", "USES_TECHNIQUE",
        "HAS_SAMPLE", "OPERATES_CAMPAIGN", "DEPLOYS_MALWARE", "USES_MALWARE"
    }
    SIMILARITY_MERGE_THRESHOLD = 0.85  # Above this → MERGE into existing type
    APPROVAL_COUNT_THRESHOLD = 2       # Min agents confirming → APPROVE new type

    async def validate(
        self,
        proposed_term: str,
        term_type: str,           # "NODE_LABEL" or "RELATIONSHIP_TYPE"
        proposing_agent: str,
        peer_confirmations: int
    ) -> OntologyValidationResult:
        # Step 1: Direct match against Tier 1 anchor types
        if term_type == "NODE_LABEL" and proposed_term in self.TIER1_NODE_TYPES:
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                target_type=proposed_term,
                similarity_score=1.0,
                rationale="Exact match with existing Tier 1 node type."
            )

        # Step 2: Semantic similarity check against Tier 1 types
        nearest_type, similarity = await self._compute_nearest_similarity(proposed_term, term_type)
        if similarity >= self.SIMILARITY_MERGE_THRESHOLD:
            return OntologyValidationResult(
                decision=OntologyDecision.MERGE,
                target_type=nearest_type,
                similarity_score=similarity,
                rationale=f"Semantically equivalent to existing Tier 1 type '{nearest_type}' (score={similarity:.2f})."
            )

        # Step 3: Multi-agent approval threshold
        if peer_confirmations >= self.APPROVAL_COUNT_THRESHOLD:
            term_id = await self._register_in_ontology_registry(proposed_term, term_type, proposing_agent)
            return OntologyValidationResult(
                decision=OntologyDecision.APPROVE,
                target_type=proposed_term,
                term_id=term_id,
                similarity_score=similarity,
                approval_count=peer_confirmations,
                rationale=f"Genuinely new concept confirmed by {peer_confirmations} agents."
            )

        # Step 4: Insufficient evidence — reject as potential hallucination
        return OntologyValidationResult(
            decision=OntologyDecision.REJECT,
            target_type="",
            similarity_score=similarity,
            approval_count=peer_confirmations,
            rationale=f"Only {peer_confirmations} agent(s) confirmed this pattern (threshold={self.APPROVAL_COUNT_THRESHOLD})."
        )
```

#### Where OntologyValidator Sits in the Agent Workflow

The validator is inserted into the LangGraph `Extract Claim` node (STORY-010), immediately after the LLM extracts a raw triple but **before** `GraphOperation` is assembled. The agent only proceeds to the A2A peer check and coordinator submission if the ontology validation resolves to `MERGE` or `APPROVE`:

```text
  [LLM extracts raw triple: subject, predicate, object, proposed_entity_types]
                         │
                         ▼
         [OntologyValidator.validate(proposed_node_type, proposed_rel_type)]
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       MERGE          APPROVE        REJECT
  Use Tier 1 type   Register new  Drop claim —
  directly. No      OntologyTerm  log to audit
  new nodes.        + proceed.    trail only.
          │              │
          └──────┬───────┘
                 ▼
     [Build GraphOperation with validated types]
                 │
                 ▼
     [A2A Peer Check → Submit to Coordinator]
```

#### Current Scope vs Future Extension

| Phase | What Is Built | When |
|---|---|---|
| **Current (Phase 2-5)** | Tier 1 fixed schema only. `node_schema_version="1.0"` stamped on all nodes. `OntologyTerm` constraint created. | Immediately |
| **Post-Benchmark Extension** | `OntologyValidator` class, semantic similarity embeddings, multi-agent approval flow, dynamic Tier 2 node creation | After research results are published |

This means: the architecture is designed for extensibility **now**, but the dynamic creation of new types is deliberately deferred until Phase 2-5 benchmarks are complete. Building the validator in the current phase would add 3-4 weeks of engineering that is not required to validate the core MPAC vs Ad-Hoc research hypothesis.

---

## 4. Backend & API Design

### 4.1 Principal Authority Matrix

Each CTI feed is granted a baseline authority weight based on empirical verification and peer reputation:

| Principal ID | Data Provider | Assigned Agent | Base Authority Weight ($\text{Auth}$) | Primary Domain Specialization |
|---|---|---|---|---|
| `Principal-ThreatFox` | ThreatFox (Abuse.ch) | `Agent-ThreatFox` | **0.90** | Active C2 infrastructure, malware attribution, and IP:port combinations. |
| `Principal-URLhaus` | URLhaus (Abuse.ch) | `Agent-URLhaus` | **0.85** | Payload distribution URLs, online/offline host status, and payload dropper paths. |
| `Principal-MalwareBazaar`| MalwareBazaar (Abuse.ch)| `Agent-MalwareBazaar`| **0.88** | Binary sample hashes (SHA256, MD5), file types, and signature classifications. |
| `Principal-OTX` | AlienVault OTX (LevelBlue)| `Agent-OTX` | **0.80** | Multi-indicator pulses, adversary campaigns, and MITRE ATT&CK techniques. |

---

### 4.2 FastAPI REST Endpoints

**Base URL:** `/api/v1`

#### 1. Query Analyst Knowledge Graph
- **Endpoint:** `POST /api/v1/query`
- **Request Body:**
  ```json
  {
    "query": "What active C2 infrastructure is associated with Cobalt Strike?",
    "include_provenance": true,
    "max_hops": 2
  }
  ```
- **Response Payload:**
  ```json
  {
    "query": "What active C2 infrastructure is associated with Cobalt Strike?",
    "answer": "Cobalt Strike is associated with C2 IP 101.35.247.212 (active) and beacon host 45.154.255.87. Provenance verified across ThreatFox and AlienVault OTX with zero active attribution disputes.",
    "subgraph": {
      "nodes": [{"id": "Cobalt Strike", "label": "Malware"}, {"id": "101.35.247.212", "label": "IP"}],
      "edges": [{"from": "Cobalt Strike", "to": "101.35.247.212", "type": "USES_C2", "confidence": 100}]
    },
    "provenance_trail": [
      {"claim_id": "clm-101", "source": "ThreatFox", "record_id": "1960611", "reporter": "anonymous"}
    ],
    "conflicts": []
  }
  ```

#### 2. Get Entity Neighborhood
- **Endpoint:** `GET /api/v1/graph/{entity_type}/{entity_value}`
- **Parameters:** `entity_type` (e.g., `ip`, `malware`, `domain`), `entity_value` (e.g., `185.220.101.4`).
- **Response:** Complete JSON graph of connected nodes, relationships, and metadata claims.

#### 3. View Active & Arbitrated Conflicts
- **Endpoint:** `GET /api/v1/conflicts`
- **Query Params:** `status=all|resolved|active`, `limit=50`
- **Response:** List of all detected conflicts, the competing claims, and the formal arbitration decision justification.

#### 4. Run Comparative Benchmark Harness
- **Endpoint:** `POST /api/v1/benchmark/run`
- **Request Body:**
  ```json
  {
    "workload_size": 1000,
    "concurrency_workers": 4,
    "protocols": ["AD_HOC", "MPAC", "MPAC_ABLATION_NO_LOCKS", "MPAC_ABLATION_NO_A2A"]
  }
  ```
- **Response:** Real-time job ID. Progress streamed via WebSocket at `/ws/benchmark/{job_id}`.

---

## 5. Implementation Specifications: The Three Coordination Protocols

### 5.1 Protocol 1: Ad-Hoc Coordination (`AdHocCoordinator`)

**Core Mechanics:**
- Represents the status-quo control baseline used by existing multi-agent systems.
- Agents formulate Cypher `MERGE` queries and execute them immediately over asynchronous connection pools.
- **No Intent Registration:** Other agents have zero visibility into in-flight mutations.
- **No Semantic Locking:** Parallel transactions targeting the same IP or Malware node execute concurrently.
- **No Conflict Quarantine:** When two transactions write conflicting malware attributions, the database executes Last-Write-Wins (LWW) or creates duplicate parallel edges.
- **Expected Benchmark Failure:** High rate of corrupted node properties, unlinked claims, and 0% conflict resolution tracking.

```python
# src/coordination/adhoc.py (Conceptual Implementation)
class AdHocCoordinator(BaseCoordinator):
    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        start_time = time.perf_counter()
        # Direct Cypher mutation without locks or arbitration
        cypher = """
        MERGE (m:Malware {name: $subject})
        MERGE (i:IP {value: $object})
        MERGE (m)-[r:USES_C2]->(i)
        SET r.confidence = $confidence, r.last_updated = $timestamp
        RETURN id(r) as edge_id
        """
        async with self.neo4j.session() as session:
            result = await session.run(cypher, {
                "subject": operation.target_claim.subject,
                "object": operation.target_claim.object,
                "confidence": operation.target_claim.confidence,
                "timestamp": operation.target_claim.timestamp
            })
            record = await result.single()
        latency = (time.perf_counter() - start_time) * 1000
        return CoordinationResult(
            operation_id=operation.operation_id,
            protocol="AD_HOC",
            status="COMMITTED",
            latency_ms=latency
        )
```

---

### 5.2 Protocol 2: Full MPAC Protocol (`MPACCoordinator`)

**Core Mechanics:**
1. **Session Lifecycle:** Worker agent registers an explicit session with the coordinator (`Session-ID`).
2. **Intent Declaration:** Agent registers its write intent with target dual-entity lock keys (e.g. `sorted(['malware:redline', 'ip:185.220.101.4'])`).
3. **Semantic Distributed Locking (Redis):** Acquires atomic distributed locks via Redis (`SETNX` with 5,000 ms TTL and Lua-script release). Locking both subject and object in deterministic alphabetical order guarantees zero circular-wait deadlocks across concurrent worker processes and prevents Neo4j native write lock collisions on high-volume malware nodes.
4. **Pre-Commit Conflict Detection:** Queries active graph state for existing claims on `(185.220.101.4)`. Differentiates temporal infrastructure churn from active attribution conflict:
   - **If $|t_{\text{new}} - t_{\text{existing}}| > 30\text{ days}$:** Classified as **Temporal Infrastructure Churn** (`INFRASTRUCTURE_REASSIGNED`). Both relationships are preserved with `valid_from` / `valid_until` timestamps.
   - **If $|t_{\text{new}} - t_{\text{existing}}| \le 30\text{ days}$ and attribution diverges:** Classified as **Active Concurrent Conflict**. Invokes Arbitration Engine.
5. **Multi-Principal Arbitration:** Evaluates the dispute using the strictly bounded formula:
   $$Score = \alpha \cdot \text{Auth}_{principal} + \beta \cdot \frac{\text{Conf}_{claim}}{100} + \gamma \cdot \text{Consensus}_{vote}$$
   where $\alpha = 0.40$, $\beta = 0.35$, $\gamma = 0.25$ ($\alpha + \beta + \gamma = 1.0$), and the consensus vote is normalized over participating non-abstaining peers:
   $$\text{Consensus}_{vote} = \frac{V_{\text{support}} - V_{\text{contradict}} + N_{\text{peers}}}{2 \cdot N_{\text{peers}}} \quad \in [0, 1]$$
   - **Dynamic Authority Feedback Loop (EMA Quality Decay):** Feed authority is dynamically updated to prevent feed-poisoning:
     $$\text{Auth}_t = (1 - \lambda) \cdot \text{Auth}_{t-1} + \lambda \cdot R_{\text{batch}}$$
     where $\lambda = 0.05$ and $R_{\text{batch}}$ is the principal's rolling peer-agreement rate over the last 100 assertions.
6. **Atomic Provenance Write:** In a single Neo4j transaction:
   - Commits domain nodes and winning relationship with `valid_from: $timestamp`.
   - Creates `(:Claim)` nodes for BOTH assertions (incorporating timestamp and evidence ID in `claim_id` to prevent collisions).
   - Creates a `(:Conflict)` node linking Claim 1 and Claim 2.
   - Creates a `(:Decision)` node documenting the winning score, authority parameters, and justification.
7. **Lock Release:** Releases distributed lock via atomic Lua token script and closes session.

```python
# src/coordination/mpac.py (Conceptual Implementation)
class MPACCoordinator(BaseCoordinator):
    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        start_time = time.perf_counter()
        # operation.lock_keys is guaranteed sorted & deduplicated by Pydantic schema validator
        lock_token = await self.lock_manager.acquire(operation.lock_keys, timeout_ms=5000)
        
        try:
            async with self.neo4j.session() as session:
                # 1. Detect existing claims / conflicts with temporal churn threshold
                conflict_check = await self.detector.check(session, operation.target_claim)
                
                decision = None
                if conflict_check.is_active_conflict:
                    # 2. Formal Weighted Arbitration
                    decision = self.arbitrator.resolve(
                        existing_claim=conflict_check.existing_claim,
                        new_claim=operation.target_claim,
                        new_principal=operation.principal_id,
                        peer_votes=operation.peer_consensus_votes
                    )
                
                # 3. Atomic Provenance-Grounded Write
                await self._write_with_provenance(session, operation, decision, is_churn=conflict_check.is_churn)
                
        finally:
            await self.lock_manager.release(lock_token)
            
        latency = (time.perf_counter() - start_time) * 1000
        return CoordinationResult(
            operation_id=operation.operation_id,
            protocol="MPAC",
            status="ACCEPTED" if not decision else "RESOLVED",
            latency_ms=latency,
            conflict_detected=conflict_check.has_conflict,
            decision=decision
        )
```

---

### 5.3 Protocol 3: MPAC Ablation Suite (`MPACAblationCoordinator`)

To empirically prove **why** MPAC works, Protocol 3 runs three controlled ablation variants:

1. **Ablation Mode A (`NO_A2A`):**
   - Disables Agent-to-Agent consensus voting. Agents coordinate through locks and arbitration, but cannot query peer agents for supporting evidence prior to assertion ($\gamma = 0.0$ in the arbitration formula).
   - *Target Research Hypothesis:* Proves that peer consensus significantly enhances attribution accuracy before transactions reach database locks.
2. **Ablation Mode B (`NO_SEMANTIC_LOCKS`):**
   - Disables pre-commit entity locking. Agents detect conflicts post-hoc after writing directly to Neo4j.
   - *Target Research Hypothesis:* Proves that semantic entity locking is mandatory to prevent transaction deadlocks and race-condition collisions during concurrent multi-agent ingestion.
3. **Ablation Mode C (`TIMESTAMP_ORDERED`):**
   - Retains sessions and locks, but replaces authority/confidence arbitration with **Deterministic Timestamp-Ordered Resolution** (the claim with the earliest authentic CTI discovery timestamp wins: $t_{\text{claim}_1} < t_{\text{claim}_2}$ based on original ISO-8601 feed records).
   - *Target Research Hypothesis:* Completely decouples arbitration from asynchronous event-loop network jitter, isolating whether authority and consensus weighting outperform naive temporal priority.

---

## 6. GraphRAG Retrieval Architecture

The GraphRAG retriever turns the constructed Knowledge Graph into an interactive intelligence engine for security analysts:

```text
[ Analyst Question: "What C2 IPs does RedLine Stealer use?" ]
                           │
                           ▼
             [ Entity Extraction (LLM / Regex) ]
             Target: Malware = "RedLine Stealer"
                           │
                           ▼
       [ Neo4j Pattern-Comprehension Cypher Retrieval ]
       MATCH (m:Malware {name: $malware_name})-[r:USES_C2]->(i:IP)
       RETURN m.name AS malware, i.value AS ip, r.confidence AS conf,
              [(c:Claim {subject: m.name, object: i.value}) | {
                  claim_id: c.id, principal: c.principal,
                  conflicts: [(c)-[:CONFLICTS_WITH]->(c2) | c2.id],
                  decisions: [(d:Decision)-[:RESOLVED_CONFLICT]->(cf)-[:INVOLVES_CLAIM]->(c) | d]
              }] AS provenance_meta
                           │
                           ▼
            [ Evidence & Provenance Assembly ]
            - Discovered IPs: 185.220.101.4 (Confidence: 95%)
            - Provenance: Asserted by Agent-ThreatFox from ThreatFox:1001
            - Disputed Attribution: OTX pulse asserted AgentTesla
            - Arbitration: Arbitrated in favor of RedLine (Score: 0.91 vs 0.65)
                           │
                           ▼
              [ LLM Response Synthesis Prompt ]
              System: Ground answer strictly in graph provenance context.
              Cite specific record IDs. Flag all resolved conflicts.
                           │
                           ▼
               [ Evidence-Backed Analyst Answer ]
```

### 6.1 Optimized Cypher Pattern Comprehension Query

To avoid catastrophic Cartesian products ($N_{\text{claims}} \times M_{\text{conflicts}} \times K_{\text{decisions}}$) caused by sequential `OPTIONAL MATCH` clauses across 2-hop neighborhoods, the retriever aggregates meta-nodes into nested list collections at the database layer before returning results to FastAPI:

```cypher
// Production GraphRAG Neighborhood Retrieval Query
MATCH (m:Malware {name: $malware_name})-[r:USES_C2]->(i:IP)
RETURN m.name AS malware_name,
       i.value AS c2_ip,
       r.confidence AS edge_confidence,
       r.source AS primary_source,
       [ (c:Claim {subject: m.name, object: i.value}) | {
           claim_id: c.id,
           principal: c.principal,
           confidence: c.confidence,
           evidence_id: c.evidence_id,
           timestamp: c.timestamp,
           conflicts: [ (c)-[:CONFLICTS_WITH]->(c2:Claim) | {
               conflicting_claim_id: c2.id,
               conflicting_principal: c2.principal,
               conflicting_subject: c2.subject
           }],
           decisions: [ (d:Decision)-[:RESOLVED_CONFLICT]->(cf:Conflict)-[:INVOLVES_CLAIM]->(c) | {
               decision_id: d.id,
               winning_claim_id: d.winning_claim_id,
               rationale: d.rationale,
               arbitrated_at: d.arbitrated_at
           }]
       }] AS provenance_claims;
```

---

## 7. Comparative Benchmarking & Evaluation Methodology

### 7.1 Experimental Workflow

The comparative benchmark runs automatically via `benchmark/runner.py`:

```text
                  Authentic CTI Dataset (16,270 Records)
                                    │
                                    ▼
                Task Package Generator (Partitioned Workload)
                                    │
           ┌────────────────────────┼────────────────────────┐
           ▼                        ▼                        ▼
      PROTOCOL 1               PROTOCOL 2               PROTOCOL 3
     Ad-Hoc System            Full MPAC System         Ablation Suite
           │                        │                        │
     4 Worker Threads         4 Worker Threads         4 Worker Threads
     Identical Prompts        Identical Prompts        Identical Prompts
     Simulated Concurrency    Simulated Concurrency    Simulated Concurrency
           │                        │                        │
           ▼                        ▼                        ▼
     Neo4j KG (Ad-Hoc)        Neo4j KG (MPAC)          Neo4j KG (Ablated)
           │                        │                        │
           └────────────────────────┼────────────────────────┘
                                    ▼
                      Automated Evaluation Engine
       ├── Graph Integrity Rate (GIR)
       ├── Conflict Resolution Accuracy (CRA)
       ├── Provenance Traceability Completeness (PTC)
       ├── Coordination Latency & Token Overhead
       └── Downstream GraphRAG Precision@K
```

---

### 7.2 Mathematical Evaluation Formulas

1. **Graph Integrity Rate ($GIR$) & Corruption Ratio ($CR$):**
   $$GIR = \left(\frac{N_{valid\_edges}}{N_{total\_edges}}\right) \times 100$$
   $$CR = \left(\frac{N_{corrupted\_edges}}{N_{total\_edges}}\right) \times 100$$
   *Standardized absolute integrity rate strictly bounded in $[0, 100]\%$. In severely degraded ad-hoc runs where corrupted edges exceed valid edges, the previous subtracting formula yielded negative values (e.g., -15%), breaking downstream metric visualizers. Decoupling into normalized $GIR$ and Corruption Ratio ($CR$) preserves mathematical validity across all comparative benchmarks.*

2. **Conflict Resolution Accuracy ($CRA$):**
   $$CRA = \frac{\sum_{i=1}^{K} \mathbb{I}(\text{Decision}_i == \text{GroundTruth}_i)}{K_{total\_conflicts}} \times 100$$
   *Evaluated against the 63 verified conflicts in `data/analysis/conflicts.json`.*

3. **Provenance Traceability Completeness ($PTC$):**
   $$PTC = \frac{|V_{grounded}| + |E_{grounded}|}{|V_{domain}| + |E_{domain}|} \times 100$$
   *Calculates the percentage of domain nodes and relationships having unbroken paths to `(:Evidence)` and `(:Principal)` nodes.*

---

## 8. Beginner-Friendly Step-by-Step Implementation Guide

If you are new to multi-agent architectures or graph databases, follow these exact progressive milestones:

### Step 1: Initialize Neo4j Docker & Schema Setup
- **Goal:** Run Neo4j locally in Docker and apply graph constraints.
- **Commands:**
  ```bash
  docker run -d --name neo4j-cti -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/[configure NEO4J_PASSWORD locally] neo4j:5.20.0
  ```
- **Code to Build:** Create `src/db/neo4j_client.py` connecting via the official `neo4j` Python driver and executing the constraints in Section 3.2.

### Step 2: Implement the `SemanticLockManager` (Redis Distributed Locking with Fallback)
- **Goal:** Prevent multi-agent worker processes and concurrent FastAPI instances from colliding on identical IP or Malware nodes during distributed execution.
- **Architecture:** Implement Redis distributed locks via `redis-py` using atomic `SETNX` key acquisition with TTL (Redlock pattern) to ensure safety across multiple OS processes and Uvicorn workers. Maintain an async in-memory fallback using `asyncio.Lock` for isolated local unit testing without Redis dependencies.
- **Code to Build:** In `src/coordination/lock_manager.py`, implement `acquire(keys: List[str], timeout_s: float)` and `release(token: str)`. Always acquire keys in lexicographical order (enforced upstream by `GraphOperation.enforce_deterministic_lock_sorting`) to guarantee zero circular deadlocks.

### Step 3: Implement Protocol 1 (`AdHocCoordinator`)
- **Goal:** Establish the control baseline.
- **Code to Build:** In `src/coordination/adhoc.py`, write direct Cypher statements that insert triples without checking for locks or existing claims.

### Step 4: Implement Protocol 2 (`MPACCoordinator`)
- **Goal:** Build the full multi-principal coordination layer.
- **Code to Build:**
  - `src/coordination/detector.py`: Scans Neo4j for conflicting claims on the locked entity.
  - `src/coordination/arbitrator.py`: Applies the weighted authority formula.
  - `src/coordination/mpac.py`: Combines locking, conflict detection, arbitration, and provenance node generation into one atomic transaction.

### Step 5: Implement Protocol 3 (`MPACAblationCoordinator`)
- **Goal:** Implement the ablation toggles.
- **Code to Build:** In `src/coordination/ablation.py`, allow passing flags (`ablate_locks=True`, `ablate_a2a=True`) to skip specific coordination sub-modules.

### Step 6: Connect LangGraph Agents & A2A Peer Hub
- **Goal:** Wire the 4 principal agents to dispatch claims into the coordinators.
- **Code to Build:** In `src/agents/workflow.py`, build a 5-step LangGraph state machine:
  `Receive Task` $\rightarrow$ `Retrieve Evidence via MCP` $\rightarrow$ `Extract Claim` $\rightarrow$ `A2A Peer Check` $\rightarrow$ `Submit to Coordinator`.

### Step 7: Build FastAPI Backend & Run Benchmarks
- **Goal:** Expose endpoints and execute the comparative evaluation.
- **Code to Build:** Create `src/api/main.py` and `benchmark/runner.py`. Run the benchmark over the 16,270 records and generate LaTeX tables comparing Ad-Hoc vs. MPAC vs. Ablation!

---

## 9. Integration & Dependencies

### 9.1 Environment & Software Stack

| Dependency | Purpose | Target Version |
|---|---|---|
| **Python** | Core backend language | `>= 3.10` |
| **FastAPI** | REST API & WebSocket server | `>= 0.110.0` |
| **Uvicorn** | High-performance ASGI server | `>= 0.28.0` |
| **Neo4j** | Graph database engine | `>= 5.18.0` (Community or Enterprise) |
| **neo4j (Python Driver)** | Async Cypher client | `>= 5.18.0` |
| **LangGraph / LangChain** | Agent workflow state machine | `>= 0.0.30` |
| **Pydantic** | Data validation & schema contracts | `>= 2.6.0` |
| **httpx** | Async HTTP client for MCP connectors | `>= 0.27.0` |
| **pytest / pytest-asyncio** | Test & validation framework | `>= 8.1.0` |

---

## 10. Operational Risks & Mitigation Matrix

| Risk | Impact | Probability | Mitigation Strategy | Owner |
|---|---|---|---|---|
| **Neo4j Transaction Deadlocks under Heavy Agent Concurrency** | High | Medium | Enforce alphabetical key sorting during multi-entity locking in `SemanticLockManager` to prevent circular wait deadlocks. | Database Architect |
| **Semantic Lock Starvation on Hot Entities (e.g. Popular C2 IP)** | Medium | High | Implement FIFO queuing with a hard 5,000 ms lock timeout. If timeout is exceeded, agent retries with exponential jitter. | Distributed Systems Lead |
| **LLM Hallucinations during Claim Extraction** | High | Low | Enforce strict Pydantic JSON validation schemas via LangGraph output parsers; reject invalid triples before coordination. | AI Engineer |
| **API Throttling during Live Demonstrations** | High | Low | Dual-Mode design seamlessly falls back to pre-saved bulk dumps in `data/raw/` with zero network dependency. | Backend Lead |

---

## 11. Appendix & Academic References

1. **MPAC:** *MPAC: A Multi-Principal Agent Coordination Protocol.* arXiv preprint arXiv:2604.09744, 2026.
2. **G²CP:** *G²CP: A Graph-Grounded Communication Protocol for Verifiable and Efficient Multi-Agent Reasoning.* arXiv preprint arXiv:2602.13370, 2026.
3. **Trust-Aware Traceability:** *Trust-Aware Multi-Agent Traceability and Provenance in Decentralized Systems.* arXiv preprint arXiv:2606.17203, 2026.
4. **Agentic-KGR:** *Agentic-KGR: Co-evolutionary Knowledge Graph Construction through Multi-Agent Reinforcement Learning.* arXiv preprint arXiv:2510.09156, 2025.
5. **GraphWorld:** *GraphWorld: Enabling Multi-Agent Collaboration in Knowledge Graph Environments.* OpenReview, 2026.
6. **Decentralized State Governance:** *Multi-Principal Agent Governance and Verifiable Distributed Coordination.* SSRN Electronic Journal, 2026.

---

## Document Sign-Off

**Stakeholder Review:**
- [ ] Principal AI Systems Architect: **Approved**
- [ ] Distributed Systems Lead: **Approved**
- [ ] CTI Research Lead: **Approved**
- [ ] Academic Research Advisor: **Pending Final Sign-Off**
