# Upgrade Plan: Natural Language to Knowledge Graph Interactor for Analysts (NL-GraphRAG Copilot)

**Target Document:** `upgrade.md`  
**Author:** DeepMind Agentic Assistant (ProGRESS Project)  
**System Target:** ProGRESS Multi-Agent CTI Knowledge Graph  
**Status:** Architecture & Implementation Plan *(Do Not Implement Yet)*  

---

## 1. Executive Summary & Vision

While the current ProGRESS system allows Cypher execution via the Neo4j Browser and structured API lookups, security analysts (SOC Tier-1/2, Incident Responders, and Threat Hunters) require a **conversational Natural Language interface** to investigate cyber threats.

The goal of this upgrade is to develop the **NL-GraphRAG Analyst Copilot**:
- An analyst asks in plain English:  
  * *"Why was Cobalt Strike rejected on IP 185.220.101.5, and what is currently running there?"*  
  * *"Show me all high-confidence botnet C2 servers associated with Jackskid and their resolving fast-flux domains."*
- The system:
  1. Translates the natural language question into **read-only, schema-validated Cypher** using few-shot LLM guidance.
  2. Executes **Stratified Top-K GraphRAG** across both the **Hot Domain Layer** (entities) and **Cold Provenance Layer** (claims, conflicts, decisions).
  3. Synthesizes a **source-grounded, citation-backed natural language response** where every factual statement is linked to a cryptographic claim ID, source feed, and Bayesian log-odds margin.
  4. Returns a **dynamic subgraph payload** that automatically focuses and highlights the exact nodes in the interactive visualizer (`graph_explorer.html`).

---

## 2. Core Architectural Pillars

```
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                              ANALYST INTERACTION LAYER                                  │
 │   • Floating Copilot Drawer inside graph_explorer.html                                 │
 │   • Streaming Markdown Responses with Clickable Citation Pills                         │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │ HTTP POST /api/v1/analyst/chat
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                           NLU INTENT & QUERY ROUTER                                    │
 │   Classifies input into 4 Specialized Investigation Modes:                             │
 │   [Mode 1: Entity Deep Dive]  [Mode 2: Path & Multi-Hop]                               │
 │   [Mode 3: Dispute Audit]     [Mode 4: Global Threat Landscape]                        │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                    TEXT-TO-CYPHER GENERATOR WITH "SCHEMA SHIELD"                       │
 │   • Injects Tier-1 Ontology (IP, Domain, Malware, USES_C2, etc.)                       │
 │   • Enforces AST Read-Only Validation (Rejects CREATE, MERGE, DELETE, DROP, SET)       │
 │   • Subquery Cartesian Defense (Strict LIMIT 25 on traversals)                         │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │ Safe Read-Only Cypher
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                      DUAL-LAYER GRAPH EXECUTION & HYDRATION                            │
 │   • Neo4j executes Cypher on Hot Domain (Operational Topology)                         │
 │   • MPAC Provenance Hydration: Attaches linked (Claim), (Evidence), and (Conflict)      │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │ Subgraph Context + Conflict Records
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                    PROVENANCE-GROUNDED SYNTHESIS ENGINE (LLM)                          │
 │   • Powered by Google Gemini 2.5 Flash (via llm_factory.py)                            │
 │   • Zero-Hallucination Prompt: Must cite [Claim-ID], [Source-Feed], [Margin]           │
 │   • Outputs Markdown text + Highlight Node IDs for Visualizer Camera Sync              │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Design

### 3.1. Intent Classification & Routing
The router uses `llm_factory.invoke_structured_llm` to categorize analyst queries into one of four schemas:

1. **`EntityDeepDive`** (Single IOC / Entity investigation):
   - Example: *"What is 139.59.33.238?"*
   - Strategy: Direct 1-to-2 hop neighborhood retrieval + provenance summary.
2. **`MultiHopTraversal`** (Relationship exploration across threat infrastructure):
   - Example: *"Find all domains resolving to IPs that host Vidar stealer binaries."*
   - Strategy: Dynamic Cypher path generation matching `(Domain)-[:HOSTED_ON|RESOLVES_TO]->(IP)-[:USES_C2]->(Malware)`.
3. **`DisputeAudit`** (Forensic arbitration & disagreement explanation):
   - Example: *"Why is this IP marked Vidar instead of Cobalt Strike?"*
   - Strategy: Targeted query on `(Conflict)<-[:INVOLVED_IN]-(Claim)-[:HAS_DECISION]->(Decision)`.
4. **`AggregatedLandscape`** (Statistical / Metric / Macro questions):
   - Example: *"Which malware families have the highest number of active C2 IPs?"*
   - Strategy: Aggregating Cypher queries (`count(DISTINCT ip) ORDER BY count DESC LIMIT 10`).

### 3.2. Text-to-Cypher Engine with "Schema Shield"
To prevent prompt injection, hallucinations, and accidental database mutation:
- **Ontology Injection:** The LLM system prompt is provided with the frozen Tier-1 types from `src/db/neo4j_client.py`:
  - Nodes: `IP`, `Domain`, `URL`, `Malware`, `FileHash`, `ThreatActor`, `Campaign`, `Claim`, `Evidence`, `Conflict`, `Decision`.
  - Edges: `USES_C2`, `HOSTED_ON`, `RESOLVES_TO`, `HAS_SAMPLE`, `ASSERTED`, `GROUNDED_IN`, `INVOLVED_IN`, `HAS_DECISION`, `RESOLVED_BY`.
- **AST Security Guardrail:** The generated Cypher query is parsed using regex and Cypher AST validation before execution:
  - Allowed operations: `MATCH`, `WHERE`, `WITH`, `RETURN`, `ORDER BY`, `LIMIT`, `OPTIONAL MATCH`.
  - Disallowed tokens: `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `CALL`, `LOAD CSV`.
  - Automated Safety Cap: If the LLM generates a query without `LIMIT`, the engine automatically appends `LIMIT 25` to prevent memory exhaustion.

### 3.3. Provenance-Grounded Answer Synthesizer
The LLM prompt requires **mandatory forensic attribution**.

**System Prompt Contract:**
> "You are the ProGRESS CTI Analyst Copilot. You must answer the analyst's question strictly using the provided Neo4j subgraph and provenance evidence. For every claim, you must cite:
> 1. The source feed name (e.g. ThreatFox, URLhaus).
> 2. The exact Claim ID (e.g. `[Claim-1961358]`).
> 3. If a conflict occurred, mention the Bayesian log-odds margin and the rejected competing claim.
> If the graph does not contain the answer, state that no corroborating intelligence exists in the verified database. Do not extrapolate."

**Output Format Example:**
```markdown
IP `139.59.33.238` is confirmed as an active Command and Control (C2) server for the **Jackskid** DDoS loader.

### Evidence & Provenance:
- **Primary Assertion:** Verified by ThreatFox [Claim-1961358] with 94% posterior confidence (Evidence SHA-256: `4a5b6c...b0c1`).
- **Resolving Infrastructure:** Domain `bok.6666k.org` resolves to this IP [Claim-1961370].
- **Associated Payload:** Delivers ELF binary sample `jackskid.arm7` (`e3b0c442...98fc`).
- **Dispute History:** No active conflicts recorded; unanimous feed consensus.
```

---

## 4. User Interface Specification (Enhancing `graph_explorer.html`)

Instead of requiring analysts to switch windows, a **Copilot Slide-Over Drawer** will be integrated directly into the existing visualizer:

1. **Floating Toggle Pill:**  
   A button in the top-right HUD: `[ ✨ AI Analyst Copilot ]`.
2. **Interactive Chat Drawer:**  
   A right-side sliding panel (380px) with:
   - Chat history stream.
   - Recommended prompt chips:
     - *"Explain conflict on 185.220.101.5"*
     - *"What malware is active on port 443?"*
     - *"Trace provenance for Jackskid"*
   - Natural language input bar with mic and send buttons.
3. **Bi-Directional Camera Sync (The "Show Me" Feature):**  
   - When the LLM outputs an answer citing `139.59.33.238` and `Jackskid`, the citation appears as a clickable pill: `[Focus Node: 139.59.33.238]`.
   - Clicking the pill automatically flies the Vis.js camera to the node, highlights its edges, and selects it in the **Telemetry Inspector**.

---

## 5. API Endpoints to Add

### `POST /api/v1/analyst/chat`
**Request Payload:**
```json
{
  "query": "Why was Cobalt Strike rejected on 185.220.101.5?",
  "session_id": "soc-analyst-session-01",
  "temperature": 0.0,
  "max_hops": 2
}
```

**Response Payload:**
```json
{
  "answer_markdown": "IP `185.220.101.5` was subject to an attribute conflict between URLhaus and AlienVault OTX...",
  "generated_cypher": "MATCH (i:IP {value: '185.220.101.5'})<-[:ASSERTED]-(c:Claim)... RETURN i, c, x, d",
  "highlight_nodes": ["ip_2", "conf_1", "dec_1", "mal_2", "cl_2", "cl_3"],
  "evidence_summary": {
    "winning_claim": "cl-1961371",
    "winning_family": "Vidar",
    "losing_family": "Cobalt Strike",
    "bayesian_margin": "+3.42",
    "fencing_token_used": 10428
  },
  "execution_time_ms": 142.5
}
```

### `GET /api/v1/analyst/suggested-prompts`
Returns contextual prompt recommendations based on the currently selected node in the UI.

---

## 6. Phased Implementation Roadmap

| Phase | Milestone | Deliverables | Verification Criteria |
|---|---|---|---|
| **Phase 1** | **Text-to-Cypher & Schema Shield** | • `src/analyst/cypher_generator.py`<br>• `src/analyst/ast_validator.py` | 100% of generated Cypher queries must pass AST read-only validation; 0 mutations allowed. |
| **Phase 2** | **Provenance Grounding & Synthesizer** | • `src/analyst/copilot.py`<br>• Zero-hallucination prompt template | Every generated answer includes at least one valid `[Claim-ID]` and `[Evidence-Hash]`. |
| **Phase 3** | **FastAPI Gateway Endpoints** | • `src/api/routes/analyst.py`<br>• Mounted to `src/api/main.py` | Endpoint responds in $< 350\text{ms}$ (cached) / $< 1.5\text{s}$ (live LLM). |
| **Phase 4** | **UI Copilot Drawer Integration** | • Update `graph_explorer.html` with sliding copilot panel & camera sync | Clicking citation pills zooms the Vis.js canvas to the cited entities. |
| **Phase 5** | **Evaluation & Benchmark** | • `tests/test_analyst_copilot.py`<br>• Add Question-Answering Accuracy (QAA) metric | Evaluated across 50 gold-standard CTI analyst questions with 0 hallucinations. |

---

## 7. Safety, Fallback & Hallucination Guardrails

1. **Fallback on Malformed Cypher:**  
   If the LLM generates syntactically invalid Cypher, the system automatically falls back to the deterministic `StratifiedGraphRetriever.answer()` method created in Sprint 5, guaranteeing the analyst never receives an empty screen or error code.
2. **Prompt Injection Protection:**  
   Analyst inputs containing Cypher injection attempts (e.g., `'; DROP DATABASE;--`) are intercepted and stripped by the `ast_validator` before reaching Neo4j.
3. **Token & Cache Optimization:**  
   All repeated analyst questions are hashed via SHA-256 into `data/cache/llm_structured_cache.json`, ensuring sub-millisecond retrieval and zero token waste for frequent SOC queries.

