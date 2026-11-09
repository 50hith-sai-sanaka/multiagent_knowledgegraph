# ProGRESS: Provenance-Grounded Multi-Agent Knowledge Graph Construction & Coordination System - Product Requirements Document

## Document Information

| Field | Details |
|---|---|
| Product / Module | ProGRESS Core / Multi-Agent CTI Knowledge Graph Engine |
| Date Created | 2026-10-12 |
| Last Updated | 2026-10-12 |
| Prepared By | Principal AI Research Architect & CTI Systems Engineer |
| Stakeholders | Research Advisors, Security Analysts, Threat Hunters, Multi-Agent Systems Researchers |
| Status | In Review (Ready for Benchmark Implementation) |

> **Implementation status notice (2026-11-04):** This PRD is a dated requirements baseline, not a live status board. Its milestone counts, unchecked scope items, and proposed components have not all been reconciled with current code. See [RUNTIME.md](RUNTIME.md) for on-disk data counts, verified test status, implemented runtime routes, and known blockers.

---

## 1. Overview

### 1.1 Problem Statement

**What problem are we solving?**
Cyber Threat Intelligence (CTI) is inherently distributed, high-volume, and frequently contradictory. Modern Security Operations Centers (SOCs) and Threat Intelligence teams ingest feeds from multiple heterogeneous providers (e.g., ThreatFox, URLhaus, MalwareBazaar, AlienVault OTX). When independent AI agents ingest these sources concurrently to construct a unified Knowledge Graph (KG), severe state inconsistencies occur:
1. **Attribution & Infrastructure Conflicts:** Different feeds disagree on malware family attributions, threat actor associations, and confidence scores for identical Indicators of Compromise (IOCs) (e.g., ThreatFox reports IP `185.220.101.4` as `RedLine Stealer` with 95% confidence, while URLhaus classifies it as `AgentTesla` with 75% confidence).
2. **Race Conditions in Shared Memory:** Without formal coordination, concurrent agent writes overwrite relationship weights, corrupt node properties, or create disconnected duplicate subgraphs (the "last-write-wins" or "ad-hoc" failure mode).
3. **Loss of Cryptographic & Epistemic Provenance:** Once an entity edge is merged into a graph, downstream security analysts lose traceability back to the specific originating raw API report, the agent that extracted it, and the decision justification that resolved any underlying conflict.

**Current State:**
- Existing Multi-Agent Knowledge Graph systems (e.g., standard LangGraph / AutoGen / CrewAI pipelines) rely on ad-hoc Cypher `MERGE` statements or centralized single-agent extractors.
- Centralized extractors create massive throughput bottlenecks and fail to model multi-principal governance where independent vendors possess distinct write authorities and trust reputations.
- Ad-hoc parallel agent writes produce corrupted graph topology and unrecorded epistemic contradictions.

**Who is affected?**
- **CTI Analysts & Threat Hunters:** Querying the graph for incident response receive hallucinated or ungrounded attribution trails without evidence verification.
- **Security Incident Responders:** Act on conflicting IOCs (blocking false positive infrastructure or missing critical C2 links).
- **Academic & Multi-Agent Researchers:** Lack a reproducible, scientifically isolated benchmark comparing multi-principal coordination protocols over shared graph state.

### 1.2 Solution Overview

**What are we building?**
**ProGRESS** is a Provenance-Grounded Multi-Principal Multi-Agent Knowledge Graph Construction System with a formal Coordination Layer, high-performance FastAPI backend, and comparative benchmarking harness.

The system assigns each real-world CTI data provider to a dedicated, principal-isolated agent:
- **Agent A (Principal: Abuse.ch ThreatFox):** Specializes in IoC extraction (C2 IPs, domains, hashes, malware family confidence).
- **Agent B (Principal: Abuse.ch URLhaus):** Specializes in payload delivery URLs, distribution host IPs, and online payload statuses.
- **Agent C (Principal: Abuse.ch MalwareBazaar):** Specializes in malware binaries, SHA256/MD5 sample hashes, and file signatures.
- **Agent D (Principal: LevelBlue AlienVault OTX):** Specializes in threat pulses, adversary campaigns, and complex indicator sets.

These agents interface with external feeds via the **Model Context Protocol (MCP)**, communicate with peers for consensus verification using **Graph-Grounded Agent-to-Agent (A2A)** protocols, and write into a shared **Neo4j Knowledge Graph** through a modular **`CoordinationAdapter`**.

To isolate the scientific contribution for publication, the system implements and benchmarks **three distinct operational protocols**:
1. **Protocol 1: Ad-Hoc Protocol (Baseline / Control System):** Agents execute direct parallel Cypher mutations against Neo4j without intent coordination or conflict quarantine (Last-Write-Wins / First-Write-Wins).
2. **Protocol 2: MPAC Protocol (Multi-Principal Agent Coordination System):** Full multi-principal governance implementing Session Lifecycles, Intent Declarations, Semantic Entity Locking, Multi-Principal Conflict Detection, Formal Arbitration (authority weighting, confidence reconciliation), and Atomic Graph Writes with explicit Provenance & Conflict edges.
3. **Protocol 3: MPAC Ablation Protocol (Ablation System):** Systematic sub-protocol variants (e.g., MPAC without A2A cross-verification, MPAC without semantic entity locking, and MPAC with unweighted FIFO arbitration) to prove causal significance of each protocol layer.

**How does this fit into the product?**
The system serves as the foundational data and coordination infrastructure for downstream **GraphRAG analyst query interfaces**, providing evidence-grounded answers backed by unbroken provenance subgraphs.

---

### 1.3 Success Criteria

**How will we know this is successful?**

| Metric | Ad-Hoc Baseline | MPAC Target | MPAC-Ablation Target | Timeline / Milestone | Measurement Method |
|---|---|---|---|---|---|
| **Graph Integrity Rate (%)** | < 68.0% | **> 98.5%** | ~82.0% – 88.0% | Phase 2 Benchmarking | Automated Cypher graph validation query checking for dangling nodes, orphan claims, and attribute overwrites. |
| **Conflict Resolution Accuracy (%)** | 0.0% (Ignored / Overwritten) | **> 92.0%** | ~74.0% – 80.0% | Phase 2 Benchmarking | Evaluation against 120 verified ground-truth CTI conflicts. |
| **Provenance Traceability Completeness (%)** | < 30.0% | **100.0%** | 100.0% | Phase 2 Benchmarking | Graph traversal verifying every entity node/edge links back to an explicit `Claim`, `Agent`, `Principal`, and raw `Evidence` node. |
| **Downstream GraphRAG Precision@K** | < 65.0% | **> 91.0%** | ~78.0% – 84.0% | Phase 4 Evaluation | Analyst CTI benchmark queries evaluated on LLM retrieval precision. |
| **Coordination Latency Overhead** | 0 ms (No coordination) | **< 350 ms/op** | < 180 ms/op | Phase 2 Benchmarking | Wall-clock transaction timing per write operation. |
| **Dataset Scale** | N/A | **> 15,000 records** | > 15,000 records | Milestone 1 (Completed) | Real-world authentic dataset (16,481 records, 12,226 unique IOCs, 371 overlaps, 96–120 conflicts). |

---

### 1.4 Scope & Boundaries

#### What's IN Scope (v1.0)
- [x] **Real-World High-Volume Data Layer (Milestone 1 Complete):**
  - Authentic live & bulk feed ingestion for ThreatFox, URLhaus, MalwareBazaar, and AlienVault OTX (16,481 records, 12,226 unique IOCs, 371 overlaps, 96–120 verified conflicts).
  - Dual-mode support (Live API collection + Offline fixture replay for 100% reproducible experiments).
  - Automated daily synchronization pipeline ([sync_daily.py](file:///Users/sohithsai/multiagent_knowledgegraph/sync_daily.py)).
- [ ] **Multi-Agent Architecture:**
  - 4 Principal-bound worker agents (Agent A: ThreatFox, Agent B: URLhaus, Agent C: MalwareBazaar, Agent D: OTX).
  - Standardized tool integration via Model Context Protocol (MCP).
  - Peer consensus querying via Agent-to-Agent (A2A) protocol.
- [ ] **Neo4j Dual-Layer Knowledge Graph Schema:**
  - Domain Layer: `(:Malware)`, `(:IP)`, `(:Domain)`, `(:URL)`, `(:FileHash)` with relationships `[:USES_C2]`, `[:DISTRIBUTED_VIA]`, `[:HOSTED_ON]`, `[:HAS_SAMPLE]`.
  - Provenance & Governance Meta-Layer: `(:Claim)`, `(:Evidence)`, `(:Principal)`, `(:Agent)`, `(:Decision)`, `(:Conflict)` with relationships `[:ASSERTS]`, `[:GROUNDED_IN]`, `[:CONFLICTS_WITH]`, `[:RESOLVED_BY]`.
- [ ] **Coordination Layer Abstraction (`CoordinationAdapter`):**
  - `AdHocCoordinator`: Direct asynchronous Cypher write execution without locking or arbitration.
  - `MPACCoordinator`: Formal multi-principal coordinator with Session Management, Intent Declarations, Semantic Locking, Multi-Principal Conflict Detection, and Arbitration.
  - `MPACAblationCoordinator`: Configurable ablation variants removing A2A, semantic locking, or authority weighting.
- [ ] **FastAPI Backend Service:**
  - REST endpoints for query execution, graph topology inspection, conflict viewing, provenance audit trails, and benchmark execution.
- [ ] **Comparative Benchmarking Harness:**
  - Automated evaluation pipeline running identical workloads across all 3 protocols and generating LaTeX-ready performance tables and charts.

#### What's OUT of Scope
- ❌ Synthetic / manufactured benchmark data (all benchmarks must use 100% authentic, paper-ready real CTI data).
- ❌ Automated network firewall or endpoint mitigation blocking (read/write to KG only; no live infrastructure reconfiguration).
- ❌ Training new foundational LLMs from scratch (system utilizes pre-trained LLMs via LangGraph/LangChain or local Ollama instances).
- ❌ Closed-source proprietary threat intelligence platforms (restricted to open/community CTI: abuse.ch and AlienVault OTX).

#### Future Considerations
- 💡 Automated deployment of MITRE ATT&CK TTP mapping agents in v2.0.
- 💡 Zero-knowledge or cryptographic signature verification on agent claims for untrusted federated consortiums (v2.0).

---

## 2. Users & Personas

- **CTI Security Analyst (`analyst`):**
  - Queries the system via natural language or Cypher to investigate active malware campaigns, C2 infrastructure, and threat actor infrastructure.
  - Requires clear evidence, confidence scores, and conflict flags showing whether vendors disagree.
- **Incident Responder (`responder`):**
  - Requires urgent, verifiable IP and domain IOC blocklists with zero false-positive contamination caused by agent write race conditions.
- **Academic Researcher & Evaluator (`researcher`):**
  - Runs controlled comparative benchmarks across the 3 coordination protocols (Ad-Hoc, MPAC, MPAC-Ablation).
  - Inspects graph integrity metrics, conflict resolution precision, coordination latency, and token overhead to generate publication figures.
- **CTI Source Principal (`principal`):**
  - Represented by an autonomous agent asserting threat claims with distinct authority weights and confidence metrics based on historical feed reliability.

---

## 3. System Architecture & Protocol Comparison

### 3.1 Architectural Macro-Diagram

```text
                                 ┌─────────────────────────────────────────┐
                                 │       ANALYST & EVALUATION CLIENT       │
                                 │   FastAPI REST API / Next.js Workbench   │
                                 └────────────────────┬────────────────────┘
                                                      │ HTTP / WebSocket
                                 ┌────────────────────▼────────────────────┐
                                 │             FASTAPI BACKEND             │
                                 │  /query  /graph  /conflicts  /benchmark │
                                 └────────────────────┬────────────────────┘
                                                      │
                                 ┌────────────────────▼────────────────────┐
                                 │           GRAPHRAG RETRIEVER            │
                                 │ Question → Cypher Context → LLM Answer  │
                                 └────────────────────┬────────────────────┘
                                                      │
                                 ┌────────────────────▼────────────────────┐
                                 │         NEO4J KNOWLEDGE GRAPH           │
                                 │   Domain Graph  +  Provenance Meta-KG   │
                                 └────────────────────▲────────────────────┘
                                                      │ Graph Writer
                                 ┌────────────────────┴────────────────────┐
                                 │          COORDINATION ADAPTER           │
                                 │                                         │
                 ┌───────────────┼─────────────────────────┐               │
                 ▼               ▼                         ▼               │
        ┌────────────────┐ ┌────────────────┐ ┌──────────────────────────┐ │
        │  PROTOCOL 1    │ │  PROTOCOL 2    │ │  PROTOCOL 3              │ │
        │  Ad-Hoc        │ │  Full MPAC     │ │  MPAC Ablation           │ │
        │  Coordinator   │ │  Coordinator   │ │  Coordinator             │ │
        │  (Control)     │ │  (Experimental)│ │  (Ablation Suite)        │ │
        └────────▲───────┘ └────────▲───────┘ └────────────▲─────────────┘ │
                 │                  │                      │               │
                 └──────────────────┼──────────────────────┘               │
                                    │ Structured Operations                │
                                 ┌──┴──────────────────────────────────────┘
                                 │
                         ┌───────┴───────┐
                         │   LANGGRAPH   │  Multi-Agent Orchestrator
                         └───────┬───────┘
                                 │
     ┌───────────────────┬───────┴───────────┬───────────────────┐
     │                   │                   │                   │
┌────▼────────┐     ┌────▼────────┐     ┌────▼────────┐     ┌────▼────────┐
│  AGENT A    │     │  AGENT B    │     │  AGENT C    │     │  AGENT D    │
│ ThreatFox   │     │  URLhaus    │     │MalwareBazaar│     │  OTX Pulse  │
│ Principal-A │     │ Principal-B │     │ Principal-C │     │ Principal-D │
└────┬────────┘     └────┬────────┘     └────┬────────┘     └────┬────────┘
     │                   │                   │                   │
     └──────── A2A ──────┴─────── A2A ───────┴──────── A2A ──────┘
     │                   │                   │                   │
   [MCP]               [MCP]               [MCP]               [MCP]
     │                   │                   │                   │
┌────▼────────┐     ┌────▼────────┐     ┌────▼────────┐     ┌────▼────────┐
│  ThreatFox  │     │   URLhaus   │     │MalwareBazaar│     │  AlienVault │
│ Public Bulk │     │ Public Bulk │     │ Public CSV  │     │ OTX Pulse   │
│ 3,000 IOCs  │     │ 10,000 URLs │     │ 1,700 Smpls │     │ 1,781 IOCs  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

---

### 3.2 Deep Protocol Comparison

The core scientific contribution is isolating performance across the three protocol implementations under **identical workloads, identical LLM prompts, and identical multi-principal agent populations**:

| Feature / Mechanism | Protocol 1: Ad-Hoc Coordination | Protocol 2: Full MPAC Protocol | Protocol 3: MPAC Ablation Protocol |
|---|---|---|---|
| **Underlying Philosophy** | Uncoordinated Concurrent Mutation | Governed Multi-Principal Agreement | Isolated Variable Testing |
| **Session Lifecycle** | None (Immediate async execution) | Explicit Session (`INIT` → `ACTIVE` → `CLOSE`) | Partial Session tracking |
| **Intent Declaration** | None (Direct write execution) | Mandatory Intent registered before write | Varies by ablation mode |
| **Concurrency Control** | Database-level lock (Blind Cypher `MERGE`) | **Semantic Entity Locking** on target IOCs | **Ablation B:** Disabled (Direct mutation) |
| **Conflict Detection** | None (Silent overwrite or duplicate edge) | **Pre-Commit Semantic Conflict Detection** | Active in post-commit only |
| **Peer Cross-Verification** | None | **A2A Consensus Querying (G²CP)** | **Ablation A:** Disabled (Zero peer queries) |
| **Arbitration Mechanism** | Last-Write-Wins (LWW) / FIFO | **Authority & Confidence Weighted Arbitration** | **Ablation C:** Disabled (Unweighted FIFO) |
| **Provenance Tracking** | Domain nodes only; no claim provenance | Full `(:Claim)` + `(:Evidence)` + `(:Decision)` | Full or partial metadata tracking |
| **Target Research Finding** | Baseline failure mode under multi-feed concurrency | Proof of state integrity & verified consensus | Empirical proof of which MPAC components are causal |

---

### 3.3 Theoretical & Literature Foundations

The architecture integrates foundational principles from six premier multi-agent and knowledge graph research papers:

1. **MPAC: A Multi-Principal Agent Coordination Protocol (*arXiv:2604.09744*):**
   - Provides the formal state machine: Intent Registration $\rightarrow$ Semantic Conflict Detection $\rightarrow$ Multi-Principal Arbitration $\rightarrow$ Graph Mutation.
   - Enforces separation between agent identity, principal authority, and shared mutable database state.
2. **G²CP: Graph-Grounded Communication Protocol (*arXiv:2602.13370*):**
   - Governs the **Agent-to-Agent (A2A)** interaction layer.
   - Replaces unstructured natural language agent chatter with **verifiable, graph-grounded communicative acts** (agents exchange structured claim tuples and subgraph neighborhoods).
3. **Trust-Aware Multi-Agent Traceability (*arXiv:2606.17203*):**
   - Defines the epistemic provenance layer. Every asserted edge in Neo4j contains an unbroken SHA256-verified link to raw evidence, the asserting agent, and historical trust scores.
4. **Agentic-KGR: Co-evolutionary KG Construction (*arXiv:2510.09156*):**
   - Implements closed-loop feedback: when a claim is rejected or arbitrated during MPAC coordination, the coordination decision is fed back into the agent's LangGraph state machine to refine subsequent extractions.
5. **GraphWorld: Multi-Agent Collaboration in KG Environments (*OpenReview:xUDGChZsfG*):**
   - Formalizes the collaborative graph environment where multi-principal agents operate concurrently within shared graph boundaries without stepping on state locks.
6. **Decentralized Multi-Agent State Governance (*SSRN:6837300*):**
   - Supplies the arbitration rules for multi-principal disputes, ensuring no single feed possesses unchecked unilateral write authority over disputed threat attributions.

---

## 4. User Experience & System Workflows

### 4.1 Primary User Flows

#### Primary Flow 1: High-Volume Multi-Agent Graph Construction Run
**Entry Point:** CLI (`python run_pipeline.py --protocol mpac`) or REST (`POST /api/benchmark/run`).

**Step-by-Step Execution:**
1. **Task Dispatch:** System loads normalized CTI task packages from `data/normalized/` (partitioned across Principal A: ThreatFox, Principal B: URLhaus, Principal C: MalwareBazaar, Principal D: OTX).
2. **Agent Workflow (LangGraph):**
   - Agent receives evidence package via MCP.
   - Agent extracts structured claims: `(Subject: "185.220.101.4", Predicate: "USES_C2", Object: "RedLine", Confidence: 95)`.
3. **Peer Verification (A2A - G²CP):**
   - Agent A queries Agent B and D: *"Do your evidence feeds support or contradict attribution on 185.220.101.4?"*
   - Peers return grounded evidence subgraphs.
4. **Coordination Submission:**
   - Agent formats a structured `GraphOperation` payload and calls `coordinator.submit(operation)`.
5. **Coordination Layer Processing:**
   - **If Protocol 1 (Ad-Hoc):** Submits directly to Neo4j. Overwrites existing properties; duplicate edges created; conflicts unrecorded.
   - **If Protocol 2 (Full MPAC):**
     1. Coordinator opens session and acquires semantic entity lock on `185.220.101.4`.
     2. Conflict Detector scans active graph and pending intents for property or attribution divergence.
     3. If conflict detected (e.g., `RedLine` vs `AgentTesla`), triggers Arbitration Engine.
     4. Arbitration evaluates principal authority weight and confidence differential.
     5. Atomic Graph Write commits domain entities AND creates `(:Claim)`, `(:Conflict)`, and `(:Decision)` provenance nodes.
     6. Releases entity lock.
   - **If Protocol 3 (MPAC-Ablation):** Runs selected ablation variant (e.g., skips A2A peer verification or skips semantic locking).
6. **Completion & Validation:** Graph validation metrics computed and logged.

```text
[Raw Evidence] → [MCP Tool Layer] → [LangGraph Worker Agent] → [A2A Peer Query (G²CP)]
                                                                         ↓
                                                         [Create GraphOperation]
                                                                         ↓
                                                         [CoordinationAdapter]
                                                                         │
                 ┌───────────────────────────────────────────────────────┼─────────────────────────────────┐
                 ▼                                                       ▼                                 ▼
      [Protocol 1: Ad-Hoc]                                    [Protocol 2: Full MPAC]             [Protocol 3: MPAC Ablation]
                 ↓                                                       ↓                                 ↓
      [Direct Async Cypher]                                   [Acquire Semantic Lock]             [Run Selected Ablation]
                 ↓                                                       ↓                                 ↓
      [Race Conditions / Collisions]                          [Detect Semantic Conflicts]         [Partial Coordination]
                 ↓                                                       ↓                                 ↓
      [Corrupted Graph Topo]                                  [Arbitrate & Resolve]               [Benchmark Divergence]
                 ↓                                                       ↓                                 ↓
         [Neo4j (Ad-Hoc KG)]                                     [Atomic Write with Provenance]    [Neo4j (Ablated KG)]
                                                                         ↓
                                                                [Neo4j (MPAC Provenance KG)]
```

---

#### Primary Flow 2: Security Analyst Evidence-Backed Query
**Entry Point:** `POST /api/query` or Analyst Web UI.

**Step-by-Step Execution:**
1. Analyst submits question: *"What C2 infrastructure is associated with RedLine Stealer, and are there any conflicting attributions?"*
2. **GraphRAG Engine:**
   - Extracts entity `RedLine Stealer`.
   - Queries Neo4j for 2-hop neighborhood: connected IPs, domains, and associated `(:Claim)` / `(:Conflict)` nodes.
3. **LLM Synthesis:** Generates answer citing specific ThreatFox and URLhaus record IDs and explicitly flags: *"Warning: One conflicting attribution detected from OTX Pulse 3001 associating IP 185.220.101.4 with AgentTesla (arbitrated in favor of RedLine due to 95% vs 50% confidence differential)."*
4. Client visualizes the domain subgraph alongside the provenance dispute trail.

---

### 4.2 Functional Requirements

| Requirement ID | Feature | Priority | User Story | Acceptance Criteria |
|---|---|---|---|---|
| **FR-CORE-01** | High-Volume CTI Ingestion | Must Have | As an agent, I need standardized access to thousands of real CTI records. | Ingests ThreatFox, URLhaus, MalwareBazaar, and OTX with >15,000 normalized records. *(Completed)* |
| **FR-CORE-02** | Dual-Mode Replay Support | Must Have | As a researcher, I need identical offline replay fixtures. | Fixture mode replays exact JSON dumps deterministically with zero network calls. *(Completed)* |
| **FR-AGENT-01** | Principal-Isolated Agents | Must Have | As a system, each agent must strictly represent one data source principal. | 4 distinct agents instantiated with isolated write credentials and distinct principal IDs. |
| **FR-AGENT-02** | MCP Tool Layer | Must Have | As an agent, I query feeds via standardized tool protocols. | Tools exposed via MCP standard for querying IOCs, payloads, and pulse records. |
| **FR-A2A-01** | Graph-Grounded Peer Verification | Must Have | As an agent, I verify claims with peers before asserting them. | A2A protocol implements G²CP structured query and evidence subgraph responses. |
| **FR-COORD-01** | Abstract Coordination Adapter | Must Have | As an evaluator, I need a single switch to toggle coordination protocols. | `CoordinationAdapter.submit(operation)` transparently routes to Ad-Hoc, MPAC, or Ablation. |
| **FR-COORD-02** | Ad-Hoc Baseline Coordinator | Must Have | As a benchmark baseline, I need uncoordinated parallel writes. | Direct Cypher execution with simulated concurrency; measures natural race conditions. |
| **FR-COORD-03** | Full MPAC Coordinator | Must Have | As a system, I need formal multi-principal governance over shared state. | Implements Session lifecycle, Intent registration, Semantic locking, and Conflict arbitration. |
| **FR-COORD-04** | MPAC Ablation Coordinator | Must Have | As a researcher, I need to ablate specific MPAC sub-components. | Supports flags: `--ablate-a2a`, `--ablate-locking`, `--ablate-arbitration`. |
| **FR-GRAPH-01** | Dual-Layer Neo4j Knowledge Graph | Must Have | As an analyst, I need domain knowledge linked to provenance metadata. | Graph contains both domain nodes (`Malware`, `IP`) and meta-nodes (`Claim`, `Evidence`, `Conflict`). |
| **FR-BENCH-01** | Automated Comparative Benchmarking | Must Have | As an evaluator, I need automated metric computation across all 3 protocols. | Evaluates Graph Integrity, Conflict Resolution Accuracy, Provenance Completeness, and Token Cost. |
| **FR-API-01** | FastAPI Gateway | Must Have | As a client, I need REST endpoints to query and benchmark the system. | Endpoints for `/query`, `/graph`, `/conflicts`, `/provenance`, and `/benchmark`. |

---

### 4.3 Business & Protocol Invariants

| Rule ID | Protocol Invariant | Rationale | Impact if Violated |
|---|---|---|---|
| **BR-PROT-01** | Complete Component Isolation | Only the coordination adapter changes between benchmark runs. Workload, agents, and prompts remain identical. | Evaluation results lose scientific validity and fail peer review. |
| **BR-PROT-02** | Zero Synthetic Evidence in Evaluation | All benchmark inputs must originate from authentic CTI feeds. | Disqualifies paper from top-tier security venues (IEEE S&P, USENIX, ACM CCS). |
| **BR-PROT-03** | Unbroken Provenance Chain | In MPAC, no domain node or relationship can exist without a direct link to a `Claim` and `Evidence` record. | Compromises auditability and violates trust-aware traceability. |
| **BR-PROT-04** | Conflict Preservation Over Silent Deletion | When two claims conflict, MPAC must never silently delete the loser; it must record a `(:Conflict)` node linking both claims. | Downstream analysts lose critical context regarding vendor disagreements. |
| **BR-PROT-05** | Atomic Lock Release | Semantic entity locks must be released upon transaction commit or abort with strict timeouts (max 5,000 ms). | Agent deadlocks stall the ingestion pipeline under heavy concurrency. |

---

## 5. Data Requirements & Schemas

### 5.1 Standardized CTI Record Schema (`schemas/cti.py`) *(Completed)*
```python
class NormalizedCTIRecord(BaseModel):
    source: str                    # ThreatFox, URLhaus, MalwareBazaar, OTX
    record_id: str                 # Unique source ID
    timestamp: str                 # ISO 8601 UTC
    ioc_type: str                  # ip, domain, url, hash_sha256, hash_md5
    ioc_value: str                 # Standardized indicator value
    malware_family: Optional[str]  # e.g., RedLine, AgentTesla, Mozi
    threat_actor: Optional[str]    # e.g., APT28, Lazarus
    confidence: Optional[int]      # Standardized 0-100 scale
    reporter: Optional[str]        # Contributor or pulse author identity
    tags: List[str]                # Classification tags
    raw_data: Dict[str, Any]       # Complete untouched raw API JSON
```

### 5.2 Structured Claim & Operation Schemas (`schemas/operation.py`)
```python
class Claim(BaseModel):
    claim_id: str
    subject: str                   # e.g., "RedLine"
    predicate: str                 # USES_C2, DISTRIBUTED_VIA, HOSTED_ON, HAS_SAMPLE
    object: str                    # e.g., "185.220.101.4"
    confidence: int                # 0-100
    evidence_ids: List[str]        # References to raw CTI records

class GraphOperation(BaseModel):
    operation_id: str
    principal_id: str              # e.g., "Principal-ThreatFox"
    agent_id: str                  # e.g., "Agent-01"
    intent_type: str               # ADD_RELATION, UPDATE_CONFIDENCE, QUARANTINE_CLAIM
    target_claim: Claim
    timestamp: str
```

### 5.3 Neo4j Graph Topology Schema

```cypher
// Domain Entity Nodes
(:Malware {id: STRING, name: STRING, aliases: LIST<STRING>})
(:IP {value: STRING, is_ipv4: BOOLEAN})
(:Domain {value: STRING})
(:URL {value: STRING})
(:FileHash {sha256: STRING, md5: STRING})

// Domain Relationships
(:Malware)-[:USES_C2 {confidence: FLOAT, status: STRING}]->(:IP)
(:Malware)-[:DISTRIBUTED_VIA]->(:URL)
(:URL)-[:HOSTED_ON]->(:IP)
(:Malware)-[:HAS_SAMPLE]->(:FileHash)

// Provenance & Governance Meta-Nodes
(:Principal {id: STRING, name: STRING, base_authority_weight: FLOAT})
(:Agent {id: STRING, principal_id: STRING})
(:Evidence {source: STRING, record_id: STRING, raw_hash: STRING, timestamp: STRING})
(:Claim {id: STRING, confidence: INT, timestamp: STRING})
(:Conflict {id: STRING, conflict_type: STRING, detected_at: STRING, resolved: BOOLEAN})
(:Decision {id: STRING, status: STRING, rationale: STRING, arbitrated_at: STRING})

// Provenance Relationships
(:Agent)-[:REPRESENTS]->(:Principal)
(:Agent)-[:ASSERTS]->(:Claim)
(:Claim)-[:GROUNDED_IN]->(:Evidence)
(:Claim)-[:GOVERNS]->(:Malware)
(:Claim)-[:CONFLICTS_WITH]->(:Claim)
(:Decision)-[:RESOLVED_CONFLICT]->(:Conflict)
```

---

## 6. Benchmarking & Evaluation Methodology

### 6.1 Benchmark Workload Formulation
The evaluation benchmark executes against the **16,481 real-world records** collected in Milestone 1:
- **Phase A (Baseline Ingestion):** 10,000 independent, non-overlapping claims establishing baseline graph topology.
- **Phase B (Concurrent Overlap & Conflict Stress-Test):** Concurrent dispatch of the **371 overlapping IOCs** and **120 verified conflicting claims** across 4 parallel agent threads.

### 6.2 Evaluation Metrics & Formulas

1. **Graph Integrity Rate ($GIR$):**
   $$GIR = \frac{N_{valid\_edges} - N_{corrupted\_edges}}{N_{total\_edges}} \times 100$$
   *Measures the percentage of graph edges free from duplicate relationships, overwritten confidence scores, and unlinked attributes.*

2. **Conflict Resolution Accuracy ($CRA$):**
   $$CRA = \frac{C_{correctly\_arbitrated}}{C_{total\_conflicts}} \times 100$$
   *Measures whether detected conflicts were arbitrated in accordance with ground-truth authority and confidence differential rules rather than arbitrary race condition overwrite.*

3. **Provenance Traceability Completeness ($PTC$):**
   $$PTC = \frac{E_{provenance\_grounded}}{E_{total\_domain\_entities}} \times 100$$
   *Percentage of domain nodes and relationships maintaining unbroken 3-hop traversal paths back to authentic raw evidence.*

4. **Coordination Overhead Latency ($\Delta T$):**
   $$\Delta T = T_{protocol} - T_{adhoc}$$
   *Wall-clock execution time and LLM token consumption incurred by coordination.*

---

## 7. Edge Cases & Resilience

| Scenario | Protocol 1 (Ad-Hoc) Behavior | Protocol 2 (MPAC) Expected Behavior | Impact on Graph |
|---|---|---|---|
| **Simultaneous write to same IP with conflicting malware** | Last transaction overwrites first; first claim deleted. | Semantic lock queues second write; conflict detected; `(:Conflict)` node created; arbitration invoked. | Ad-Hoc loses evidence; MPAC preserves both claims with verified decision. |
| **Identical claim asserted by two agents** | Creates duplicate edge or blindly updates timestamp. | Detects agreement overlap; reinforces confidence score $(C = 1 - (1-C_1)(1-C_2))$; links both evidence items. | MPAC increases confidence mathematically; Ad-Hoc creates data bloat. |
| **Network timeout on external CTI API** | Agent crashes or hangs pipeline. | Dual-mode connector seamlessly fails over to bundled fixture in `data/fixtures/`. | Ingestion pipeline never halts. |
| **Agent deadlock on circular entity locks** | N/A (No locking). | Coordinator enforces 5,000 ms lock timeout; aborts transaction with retry backoff. | Prevents pipeline lockup. |
| **Out-of-order pulse ingestion** | New C2 status overwritten by older historical pulse. | MPAC checks ISO 8601 timestamps; assigns temporal decay weighting during arbitration. | Preserves active infrastructure state. |

---

## 8. Risks & Mitigation

| Risk | Probability | Impact | Mitigation Strategy | Owner |
|---|---|---|---|---|
| **Neo4j Transaction Deadlocks under High Concurrency** | Medium | High | Implement retry loops with exponential jitter and fine-grained node-level lock keys. | Database Architect |
| **API Rate-Limiting During Live Demos** | High | Medium | Dual-Mode design allows instant switching between live API endpoints and `data/raw/` pre-fetched caches. | Backend Lead |
| **LLM Inference Latency During A2A Consensus** | Medium | Medium | Use small, fast reasoning models (e.g., GPT-4o-mini / Gemini Flash) for claim validation and structured schema output. | AI Engineer |
| **Lack of Ground-Truth Consensus on Disputed IOCs** | Medium | High | Rely on the 120 verified conflicts in `data/analysis/conflicts.json` where ground-truth source confidence is empirically recorded. | CTI Researcher |

---

## 9. Appendix & Academic References

### 9.1 Academic Literature Citations
1. **MPAC:** *MPAC: A Multi-Principal Agent Coordination Protocol.* arXiv preprint arXiv:2604.09744, 2026.
2. **G²CP:** *G²CP: A Graph-Grounded Communication Protocol for Verifiable and Efficient Multi-Agent Reasoning.* arXiv preprint arXiv:2602.13370, 2026.
3. **Trust-Aware Traceability:** *Trust-Aware Multi-Agent Traceability and Provenance in Decentralized Systems.* arXiv preprint arXiv:2606.17203, 2026.
4. **Agentic-KGR:** *Agentic-KGR: Co-evolutionary Knowledge Graph Construction through Multi-Agent Reinforcement Learning.* arXiv preprint arXiv:2510.09156, 2025.
5. **GraphWorld:** *GraphWorld: Enabling Multi-Agent Collaboration in Knowledge Graph Environments.* OpenReview, 2026.
6. **Decentralized State Governance:** *Multi-Principal Agent Governance and Verifiable Distributed Coordination.* SSRN Electronic Journal, 2026.

### 9.2 Change Log
| Version | Date | Author | Description of Changes |
|---|---|---|---|
| **1.0** | 2026-10-12 | Principal AI Architect | Comprehensive Product Requirements Document for ProGRESS, establishing 3-protocol comparison, full research paper integration, and benchmark evaluation methodology. |

---

## Document Sign-Off

**Stakeholder Review:**
- [ ] Principal AI Research Architect: **Approved**
- [ ] CTI Engineering Lead: **Approved**
- [ ] Academic Research Advisor: **Pending Review**
