# STORY-010 – LangGraph Agent State Machine

> **Prerequisites — BOTH must pass before starting:**
> 1. `PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_tools.py -q` → **9 passed** (Story 008)
> 2. `PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_hub.py -q` → **5 passed** (Story 009)
> Full suite: `PYTHONPATH=. ./venv/bin/pytest -q` → **61 passed**

---

## 🎯 What You Are Building

This story **brings everything together**. You are building the **agent brain** — a 5-step state machine (using LangGraph) that each of the 4 principal agents runs when it processes one IOC.

The complete lifecycle, in order:

```
┌──────────────────────────────────────────────────────────────────┐
│  IOC arrives (e.g. "https://bok.6666k.org")                      │
│                                                                  │
│  Step 1: receive              — log receipt, no state change     │
│  Step 2: fetch_evidence       — call MCP tool → get records      │
│  Step 3: extract_claim        — validate ontology, build claim   │
│  Step 4: a2a_peer_check       — ask 3 peers for votes            │
│  Step 5: submit_to_coordinator — write GraphOperation to Neo4j   │
│                                                                  │
│  Result → CoordinationResult (status: ACCEPTED / RESOLVED / failure)│
└──────────────────────────────────────────────────────────────────┘
```

All 4 agents (ThreatFox, URLhaus, MalwareBazaar, OTX) use the **same graph** — just started with different `principal_id` values.

---

## 📂 Files You Will Create

```
src/
└── agents/
    ├── __init__.py       ← already exists from Story 009
    ├── a2a.py            ← already exists from Story 009
    ├── state.py          ← NEW  (AgentState TypedDict)
    └── workflow.py       ← NEW  (5-node LangGraph + helpers)
tests/
└── test_agent_workflow.py ← NEW
```

**No existing files are modified.**

---

## 🧠 Key Concepts (Read First)

### What is LangGraph?
LangGraph lets you build agent logic as a **graph**:
- **Nodes** — Python functions (sync or async) that do work
- **Edges** — wires that connect nodes in order
- **State** — a shared dict (`AgentState`) that all nodes can read and update

Each node receives the **full current state** and returns a **partial dict** (only the fields it changed). LangGraph automatically merges the partial update into the running state.

### What is AgentState?
A `TypedDict` — a typed Python dict. It holds everything the agent knows during one IOC processing cycle:

```
principal_id         →  "Principal-ThreatFox"
ioc_value            →  "https://bok.6666k.org"
protocol             →  "mpac"
neo4j_client         →  <connected Neo4j client>
evidence             →  []         ← filled by fetch_evidence
claim_malware_family →  None       ← filled by fetch_evidence
node_label           →  "Malware"  ← filled by fetch_evidence
claim                →  None       ← filled by extract_claim  (a GraphOperation object)
peer_votes           →  []         ← filled by a2a_peer_check
consensus_score      →  0.5        ← filled by a2a_peer_check
result               →  None       ← filled by submit_to_coordinator
error                →  None       ← set if any step fails
```

### IOC type → Neo4j Node Label Mapping

| `ioc_type` field in JSON record | Neo4j label to use |
|---|---|
| `"ip"` | `"IP"` |
| `"domain"` | `"Domain"` |
| `"url"` | `"URL"` |
| `"hash_sha256"` | `"FileHash"` |
| `"hash_md5"` | `"FileHash"` |
| anything else (e.g. `"botnet_cc"`) | `"Malware"` (safe fallback) |

### Protocol → Coordinator Mapping

| `protocol` value in state | Coordinator class to use |
|---|---|
| `"adhoc"` | `AdHocCoordinator(client)` |
| `"mpac"` | `MPACCoordinator(client)` |
| `"ablation_no_a2a"` | `MPACAblationCoordinator(client, "no_a2a")` |
| `"ablation_no_locks"` | `MPACAblationCoordinator(client, "no_semantic_locks")` |
| `"ablation_timestamp"` | `MPACAblationCoordinator(client, "timestamp_ordered")` |

> Note: `MPACAblationCoordinator.__init__` signature is `(self, client, ablation_mode)` — both positional.

### What does each coordinator's `submit()` do to Neo4j?

| Coordinator | How it writes |
|---|---|
| `AdHocCoordinator` | Calls `client.run(cypher, params)` directly — **no session, no transaction** |
| `MPACCoordinator` | Uses `async with client.session() as session, session.begin_transaction() as tx:` |
| `MPACAblationCoordinator` | Same as MPAC (inherits from it) |

This distinction matters for writing correct mocks in tests.

---

## 🛠️ Step-by-Step Implementation

### Step 1 — Install LangGraph

```bash
./venv/bin/pip install langgraph typing_extensions
```

Verify:
```bash
./venv/bin/python -c "import langgraph; print('OK')"
```

---

### Step 2 — Create `src/agents/state.py`

```python
# src/agents/state.py
"""
AgentState TypedDict — Story 010.

This is the shared state dict that flows through all 5 nodes
of the LangGraph state machine.

Every node receives the full state and returns a PARTIAL update
(only the fields it changed). LangGraph merges the updates automatically.
"""
from __future__ import annotations

from typing import Any
from typing_extensions import TypedDict

from src.schemas.models import CoordinationResult, GraphOperation


class AgentState(TypedDict, total=False):
    """Shared state for the agent workflow.

    All fields are optional (total=False) because each node only sets
    the fields it is responsible for. Fields not yet set return None
    when accessed with state.get("field_name").

    Fields
    ------
    principal_id:
        Which agent this is. One of:
        "Principal-ThreatFox", "Principal-URLhaus",
        "Principal-MalwareBazaar", "Principal-OTX"
    ioc_value:
        The IOC string being processed (e.g. "https://bok.6666k.org").
    protocol:
        Coordination protocol: "adhoc", "mpac", "ablation_no_a2a",
        "ablation_no_locks", or "ablation_timestamp".
    neo4j_client:
        The connected Neo4j client instance.
    evidence:
        List of matching record dicts returned by the MCP tool.
        Empty list if nothing was found.
    claim_malware_family:
        The malware_family string from the first evidence record.
        None if evidence is empty or has no malware_family.
    node_label:
        The Tier 1 Neo4j node label derived from the IOC type
        (e.g. "IP", "URL", "FileHash"). Defaults to "Malware".
    claim:
        The GraphOperation object built in extract_claim.
        None if evidence was empty or ontology rejected the label.
    peer_votes:
        List of A2AResponse objects from the peer hub.
    consensus_score:
        Float in [0.0, 1.0] — aggregate peer consensus.
    result:
        The CoordinationResult returned by the coordinator.
    error:
        Error message string if a step failed. None normally.
    """
    principal_id:          str
    ioc_value:             str
    protocol:              str
    neo4j_client:          Any
    evidence:              list[dict[str, Any]]
    claim_malware_family:  str | None
    node_label:            str
    claim:                 GraphOperation | None
    peer_votes:            list[Any]
    consensus_score:       float
    result:                CoordinationResult | None
    error:                 str | None
```

---

### Step 3 — Create `src/agents/workflow.py`

```python
# src/agents/workflow.py
"""
LangGraph Agent State Machine — Story 010.

5-node workflow:
    receive → fetch_evidence → extract_claim → a2a_peer_check → submit_to_coordinator

Quick usage:
    from src.agents.workflow import build_agent_graph, run_agent

    graph = build_agent_graph()
    result = await run_agent(
        graph=graph,
        principal_id="Principal-ThreatFox",
        ioc_value="https://bok.6666k.org",
        protocol="mpac",
        neo4j_client=client,
    )
    # result is a CoordinationResult object
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.a2a import G2CPPeerHub
from src.agents.state import AgentState
from src.coordination.ablation import MPACAblationCoordinator
from src.coordination.adhoc import AdHocCoordinator
from src.coordination.mpac import MPACCoordinator
from src.mcp.tools import MCP_TOOLS
from src.ontology.validator import OntologyDecision, OntologyValidator
from src.schemas.models import Claim, CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IOC type → Tier 1 Neo4j node label
# ---------------------------------------------------------------------------

_IOC_TYPE_TO_LABEL: dict[str, str] = {
    "ip":          "IP",
    "domain":      "Domain",
    "url":         "URL",
    "hash_sha256": "FileHash",
    "hash_md5":    "FileHash",
}


def _ioc_type_to_label(ioc_type: str) -> str:
    """Convert an ioc_type string (from JSON) to a Tier 1 node label.

    Falls back to "Malware" for unknown types.
    """
    return _IOC_TYPE_TO_LABEL.get(ioc_type.strip().lower(), "Malware")


# ---------------------------------------------------------------------------
# Protocol → Coordinator factory
# ---------------------------------------------------------------------------

def _build_coordinator(protocol: str, neo4j_client: Any):
    """Instantiate and return the correct coordinator for the given protocol.

    Raises ValueError for unknown protocol strings.
    """
    if protocol == "adhoc":
        return AdHocCoordinator(neo4j_client)
    if protocol == "mpac":
        return MPACCoordinator(neo4j_client)
    if protocol == "ablation_no_a2a":
        return MPACAblationCoordinator(neo4j_client, "no_a2a")
    if protocol == "ablation_no_locks":
        return MPACAblationCoordinator(neo4j_client, "no_semantic_locks")
    if protocol == "ablation_timestamp":
        return MPACAblationCoordinator(neo4j_client, "timestamp_ordered")
    raise ValueError(f"Unknown protocol: {protocol!r}")


# ---------------------------------------------------------------------------
# Node 1: receive
# ---------------------------------------------------------------------------

def receive(state: AgentState) -> dict:
    """Step 1 — Log receipt of the IOC task.

    No state fields are changed here. The initial state was already set
    by run_agent(). This node exists so the graph has a named entry point.

    Returns an empty dict (no state update).
    """
    logger.info(
        "[%s] Received IOC '%s' with protocol '%s'",
        state.get("principal_id"),
        state.get("ioc_value"),
        state.get("protocol"),
    )
    return {}


# ---------------------------------------------------------------------------
# Node 2: fetch_evidence
# ---------------------------------------------------------------------------

def fetch_evidence(state: AgentState) -> dict:
    """Step 2 — Query this agent's MCP tool for matching records.

    Calls MCP_TOOLS[principal_id].invoke(ioc_value) and extracts:
    - evidence:             list of matching record dicts (may be empty)
    - claim_malware_family: malware_family from the first record (or None)
    - node_label:           Tier 1 Neo4j label derived from ioc_type

    If no tool is registered for this principal, evidence is set to [].
    """
    principal_id = state["principal_id"]
    ioc_value    = state["ioc_value"]

    tool = MCP_TOOLS.get(principal_id)
    if tool is None:
        logger.warning("No MCP tool registered for principal '%s'", principal_id)
        return {"evidence": [], "claim_malware_family": None, "node_label": "Malware"}

    response = tool.invoke(ioc_value)
    records  = response.records

    malware_family = None
    node_label     = "Malware"  # safe fallback until we know the ioc_type
    if records:
        first          = records[0]
        malware_family = first.get("malware_family")
        node_label     = _ioc_type_to_label(first.get("ioc_type", ""))

    logger.info(
        "[%s] MCP returned %d record(s) for '%s'; node_label=%s",
        principal_id, len(records), ioc_value, node_label,
    )
    return {
        "evidence":             records,
        "claim_malware_family": malware_family,
        "node_label":           node_label,
    }


# ---------------------------------------------------------------------------
# Node 3: extract_claim
# ---------------------------------------------------------------------------

def extract_claim(state: AgentState) -> dict:
    """Step 3 — Validate ontology and build a GraphOperation.

    Flow:
    1. Run OntologyValidator on the node_label from fetch_evidence.
       - MERGE or APPROVE → proceed to build the claim
       - REJECT           → set state['error'], return (no claim built)
    2. Build a Claim (SHA-256 ID is auto-generated in model_post_init).
    3. Build a GraphOperation with a deterministic lock_key.

    The GraphOperation is stored in state['claim'] and passed to
    submit_to_coordinator in Step 5.
    """
    principal_id   = state["principal_id"]
    ioc_value      = state["ioc_value"]
    node_label     = state.get("node_label", "Malware")
    malware_family = state.get("claim_malware_family")
    evidence       = state.get("evidence", [])

    # If fetch_evidence found nothing, there is no claim to build
    if not evidence:
        logger.info("[%s] No evidence found for '%s' — skipping claim", principal_id, ioc_value)
        return {"claim": None, "error": "No evidence found for this IOC"}

    # --- Ontology validation ---
    validator  = OntologyValidator()
    ont_result = validator.validate(proposed_term=node_label, category="NODE_LABEL")

    if ont_result.decision == OntologyDecision.REJECT:
        logger.warning(
            "[%s] Ontology REJECT for label '%s' — dropping claim", principal_id, node_label
        )
        return {"claim": None, "error": f"Ontology rejected node label '{node_label}'"}

    # Use the Tier 1 mapped label if the validator found a merge target
    resolved_label = ont_result.target_type or node_label

    # --- Build Claim (SHA-256 ID auto-set in model_post_init) ---
    ts    = datetime.now(tz=timezone.utc)
    claim = Claim(
        evidence_id=f"{principal_id}:{ioc_value}",
        timestamp=ts,
    )

    # --- Deterministic lock key: entity:<label>:<ioc_value> (lowercase) ---
    lock_key = f"entity:{resolved_label.lower()}:{ioc_value.lower()}"

    # --- Properties to write to Neo4j ---
    props: dict[str, Any] = {
        "ioc_value": ioc_value,
        "source":    principal_id,
    }
    if malware_family:
        props["malware_family"] = malware_family
    first = evidence[0]
    if first.get("confidence") is not None:
        props["confidence"] = first["confidence"]
    if first.get("threat_type"):
        props["threat_type"] = first["threat_type"]

    # --- Build GraphOperation ---
    operation = GraphOperation(
        operation_type="MERGE_NODE",
        operation_id=str(uuid.uuid4()),
        lock_keys=[lock_key],
        node_label=resolved_label,
        node_key="ioc_value",
        node_value=ioc_value,
        principal=principal_id,
        claim_id=claim.id,
        properties=props,
    )

    logger.info(
        "[%s] Claim built — label=%s op_id=%s",
        principal_id, resolved_label, operation.operation_id,
    )
    return {"claim": operation}


# ---------------------------------------------------------------------------
# Node 4: a2a_peer_check
# ---------------------------------------------------------------------------

async def a2a_peer_check(state: AgentState) -> dict:
    """Step 4 — Query the 3 peer agents for consensus votes.

    Calls G2CPPeerHub.query_peers() concurrently on all peers.
    Stores the A2AResponse list and computed consensus_score in state.

    If Step 3 set state['error'] (no evidence / ontology reject),
    this node returns an empty dict and passes the error through.
    """
    if state.get("error"):
        return {}  # propagate the error unchanged

    principal_id   = state["principal_id"]
    ioc_value      = state["ioc_value"]
    malware_family = state.get("claim_malware_family")

    hub = G2CPPeerHub()
    responses, score = await hub.query_peers(
        ioc_value=ioc_value,
        requesting_agent_id=principal_id,
        claim_malware_family=malware_family,
    )

    logger.info(
        "[%s] A2A score=%.3f votes=%s",
        principal_id, score, [r.vote for r in responses],
    )
    return {
        "peer_votes":      responses,
        "consensus_score": score,
    }


# ---------------------------------------------------------------------------
# Node 5: submit_to_coordinator
# ---------------------------------------------------------------------------

async def submit_to_coordinator(state: AgentState) -> dict:
    """Step 5 — Submit the GraphOperation to the chosen coordinator.

    Builds the right coordinator based on state['protocol'] and calls
    coordinator.submit(operation). Returns state['result'].

    If any earlier step set state['error'], this node returns a
    'failure' CoordinationResult without calling the coordinator.
    """
    # Handle error from earlier steps
    if state.get("error"):
        result = CoordinationResult(
            status="failure",
            detail=state["error"],
            operations_attempted=0,
            operations_committed=0,
            conflict_detected=False,
        )
        return {"result": result}

    operation    = state.get("claim")          # GraphOperation or None
    protocol     = state.get("protocol", "mpac")
    neo4j_client = state.get("neo4j_client")
    principal_id = state["principal_id"]

    if operation is None:
        result = CoordinationResult(
            status="failure",
            detail="No claim was built (evidence may be empty)",
            operations_attempted=0,
            operations_committed=0,
            conflict_detected=False,
        )
        return {"result": result}

    coordinator = _build_coordinator(protocol, neo4j_client)
    result      = await coordinator.submit(operation)

    logger.info(
        "[%s] Coordinator result: status=%s latency=%.1f ms",
        principal_id, result.status, result.latency_ms,
    )
    return {"result": result}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_agent_graph():
    """Assemble and compile the 5-node LangGraph state machine.

    Returns a compiled graph. Invoke it with:
        final_state = await graph.ainvoke(initial_state_dict)
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("receive",               receive)
    graph.add_node("fetch_evidence",        fetch_evidence)
    graph.add_node("extract_claim",         extract_claim)
    graph.add_node("a2a_peer_check",        a2a_peer_check)
    graph.add_node("submit_to_coordinator", submit_to_coordinator)

    # Wire the linear pipeline
    graph.add_edge("receive",               "fetch_evidence")
    graph.add_edge("fetch_evidence",        "extract_claim")
    graph.add_edge("extract_claim",         "a2a_peer_check")
    graph.add_edge("a2a_peer_check",        "submit_to_coordinator")
    graph.add_edge("submit_to_coordinator", END)

    # Entry point
    graph.set_entry_point("receive")

    return graph.compile()


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

async def run_agent(
    graph,
    principal_id: str,
    ioc_value: str,
    protocol: str,
    neo4j_client: Any,
) -> CoordinationResult | None:
    """Run one full agent cycle for a single IOC.

    Parameters
    ----------
    graph        : Compiled LangGraph returned by build_agent_graph()
    principal_id : e.g. "Principal-ThreatFox"
    ioc_value    : e.g. "https://bok.6666k.org"
    protocol     : "adhoc", "mpac", "ablation_no_a2a", "ablation_no_locks",
                   or "ablation_timestamp"
    neo4j_client : Connected Neo4j client instance

    Returns
    -------
    CoordinationResult or None if state unexpectedly has no result.
    """
    initial_state: AgentState = {
        "principal_id":       principal_id,
        "ioc_value":          ioc_value,
        "protocol":           protocol,
        "neo4j_client":       neo4j_client,
        "evidence":           [],
        "claim_malware_family": None,
        "node_label":         "Malware",
        "claim":              None,
        "peer_votes":         [],
        "consensus_score":    0.5,
        "result":             None,
        "error":              None,
    }
    final_state = await graph.ainvoke(initial_state)
    return final_state.get("result")
```

---

### Step 4 — Write `tests/test_agent_workflow.py`

```python
# tests/test_agent_workflow.py
"""
Tests for the LangGraph Agent State Machine — STORY-010.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py -v
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.workflow import build_agent_graph, run_agent
from src.mcp.base_tool import MCPResponse
from src.schemas.models import CoordinationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_ioc(json_path: str) -> str:
    with open(json_path, encoding="utf-8") as fh:
        return json.load(fh)[0]["ioc_value"]


THREATFOX_IOC = _first_ioc("data/normalized/threatfox.json")
URLHAUS_IOC   = _first_ioc("data/normalized/urlhaus.json")

EMPTY_PEER_TOOLS = {
    "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=MCPResponse("URLhaus",       []))),
    "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=MCPResponse("MalwareBazaar", []))),
    "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=MCPResponse("OTX",           []))),
    "Principal-ThreatFox":     MagicMock(invoke=MagicMock(return_value=MCPResponse("ThreatFox",     []))),
}


def _make_neo4j_client():
    """Create a mock Neo4j client compatible with BOTH AdHoc and MPAC coordinators.

    AdHocCoordinator  → calls client.run(cypher, params) directly
    MPACCoordinator   → calls async with client.session() as s, s.begin_transaction() as tx: tx.run(...)
    """
    client = MagicMock()

    # For AdHocCoordinator: client.run() must be awaitable
    client.run = AsyncMock()

    # For MPACCoordinator: client.session() must be an async context manager
    session = AsyncMock()
    client.session = MagicMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__  = AsyncMock(return_value=False)

    tx = AsyncMock()
    session.begin_transaction = MagicMock(return_value=tx)
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__  = AsyncMock(return_value=False)
    tx.run        = AsyncMock()

    return client


# ---------------------------------------------------------------------------
# Test 1 — Single agent, MPAC protocol, real ThreatFox IOC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_agent_e2e_mpac():
    """One agent processes a real IOC through all 5 steps under MPAC."""
    graph  = build_agent_graph()
    client = _make_neo4j_client()

    with patch("src.agents.a2a.MCP_TOOLS", EMPTY_PEER_TOOLS):
        result = await run_agent(
            graph=graph,
            principal_id="Principal-ThreatFox",
            ioc_value=THREATFOX_IOC,
            protocol="mpac",
            neo4j_client=client,
        )

    assert isinstance(result, CoordinationResult)
    assert result.status in ("ACCEPTED", "RESOLVED", "failure")


# ---------------------------------------------------------------------------
# Test 2 — Unknown IOC → no evidence → graceful failure result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_with_no_evidence():
    """Agent that finds no evidence returns a failure CoordinationResult, not an exception."""
    graph  = build_agent_graph()
    client = _make_neo4j_client()
    empty  = MCPResponse(source="ThreatFox", records=[])

    with patch("src.mcp.tools.MCP_TOOLS", {"Principal-ThreatFox": MagicMock(invoke=MagicMock(return_value=empty))}), \
         patch("src.agents.a2a.MCP_TOOLS", EMPTY_PEER_TOOLS):
        result = await run_agent(
            graph=graph,
            principal_id="Principal-ThreatFox",
            ioc_value="this-ioc-does-not-exist-xyz.example.com",
            protocol="mpac",
            neo4j_client=client,
        )

    assert isinstance(result, CoordinationResult)
    assert result.status == "failure"
    assert result.operations_committed == 0


# ---------------------------------------------------------------------------
# Test 3 — Ad-Hoc protocol works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_agent_e2e_adhoc():
    """Agent processes a real IOC under the Ad-Hoc coordinator."""
    graph  = build_agent_graph()
    client = _make_neo4j_client()

    with patch("src.agents.a2a.MCP_TOOLS", EMPTY_PEER_TOOLS):
        result = await run_agent(
            graph=graph,
            principal_id="Principal-ThreatFox",
            ioc_value=THREATFOX_IOC,
            protocol="adhoc",
            neo4j_client=client,
        )

    assert isinstance(result, CoordinationResult)
    assert result.status in ("ACCEPTED", "failure")


# ---------------------------------------------------------------------------
# Test 4 — 4 agents process 2 IOCs concurrently (main acceptance criterion)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_4_agents_concurrent():
    """All 4 agents process 2 IOCs concurrently under MPAC without crashing.

    This is the main acceptance test for Story 010.
    8 tasks run simultaneously: 4 agents × 2 IOCs.
    """
    graph  = build_agent_graph()
    client = _make_neo4j_client()

    async def _run_one(principal_id: str, ioc_value: str) -> CoordinationResult | None:
        # Each agent's own tool sees the real IOC; all peer tools return empty
        own_tool  = MagicMock(invoke=MagicMock(return_value=MCPResponse(principal_id, [])))
        peer_mock = {
            p: MagicMock(invoke=MagicMock(return_value=MCPResponse(p, [])))
            for p in [
                "Principal-ThreatFox", "Principal-URLhaus",
                "Principal-MalwareBazaar", "Principal-OTX",
            ]
        }
        with patch("src.agents.a2a.MCP_TOOLS", peer_mock):
            return await run_agent(
                graph=graph,
                principal_id=principal_id,
                ioc_value=ioc_value,
                protocol="mpac",
                neo4j_client=client,
            )

    principals = [
        "Principal-ThreatFox",
        "Principal-URLhaus",
        "Principal-MalwareBazaar",
        "Principal-OTX",
    ]
    tasks = [
        _run_one(p, ioc)
        for p in principals
        for ioc in [THREATFOX_IOC, URLHAUS_IOC]
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, r in enumerate(results):
        assert not isinstance(r, Exception), f"Task {i} raised: {r!r}"
        assert isinstance(r, CoordinationResult),  f"Task {i} returned {type(r).__name__}"
```

---

## ✅ Gate — Run and Verify

### 1. Install LangGraph first (one-time)
```bash
./venv/bin/pip install langgraph typing_extensions
```

### 2. Run the new tests
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py -v
```

Expected:
```
tests/test_agent_workflow.py::test_single_agent_e2e_mpac    PASSED
tests/test_agent_workflow.py::test_agent_with_no_evidence   PASSED
tests/test_agent_workflow.py::test_single_agent_e2e_adhoc   PASSED
tests/test_agent_workflow.py::test_4_agents_concurrent      PASSED

4 passed
```

### 3. Full suite gate (Sprint 3 complete)
```bash
PYTHONPATH=. ./venv/bin/pytest -q
# → 65 passed  (61 existing + 4 new)
```

---

## 🔎 Checklist Before Sprint 4

- [ ] `langgraph` and `typing_extensions` installed in venv
- [ ] `src/agents/state.py` — `AgentState` TypedDict with all fields including `claim`
- [ ] `src/agents/workflow.py` — 5 node functions + `_build_coordinator()` + `build_agent_graph()` + `run_agent()`
- [ ] `tests/test_agent_workflow.py` — 4 tests, all PASS
- [ ] Full suite: **65 passed**

---

## ⚠️ Common Mistakes

| Mistake | Fix |
|---|---|
| `ImportError: No module named 'langgraph'` | Run `./venv/bin/pip install langgraph` |
| `run_agent()` returns `None` | Check that `submit_to_coordinator` always returns `{"result": ...}` |
| `GraphOperation` raises `lock_keys must contain at least one key` | Always pass at least one string in `lock_keys=[...]` |
| `ModuleNotFoundError: src.agents.workflow` | Run from project root with `PYTHONPATH=.` |
| `MPACAblationCoordinator` TypeError | Its constructor is `(self, client, ablation_mode)` — do NOT use keyword args: `MPACAblationCoordinator(client, "no_a2a")` |
| Test 2 mock has no effect | Patch `"src.mcp.tools.MCP_TOOLS"` (not `"src.agents.workflow.MCP_TOOLS"`) for the agent's own tool |
| Peers still see the IOC in tests | Patch `"src.agents.a2a.MCP_TOOLS"` separately for the peer hub |
| AdHoc coordinator fails with `AttributeError: session` | `AdHocCoordinator` calls `client.run()` directly — ensure `client.run = AsyncMock()` in your mock |

---

## 🗺️ Architecture Diagram

```
┌────────────────────── LangGraph State Machine ─────────────────────────┐
│                                                                        │
│  [receive] ──▶ [fetch_evidence] ──▶ [extract_claim]                   │
│                      │                     │                           │
│               MCP_TOOLS[principal_id]  OntologyValidator              │
│               .invoke(ioc_value)       + GraphOperation               │
│                                             │                          │
│                                     [a2a_peer_check]                  │
│                                             │                          │
│                                      G2CPPeerHub                      │
│                                      .query_peers()                   │
│                                             │                          │
│                                  [submit_to_coordinator] ──▶ END      │
│                                             │                          │
│                                   AdHocCoordinator / MPACCoordinator  │
│                                   / MPACAblationCoordinator           │
└────────────────────────────────────────────────────────────────────────┘
```
