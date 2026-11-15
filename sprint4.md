# SPRINT 4: Autonomous Cyclic LangGraph Agent & Backward-Compatible Workflow Adapter
## Complete Step-by-Step Execution Guide

| Field | Details |
|---|---|
| **Sprint** | Sprint 4 |
| **Total Story Points** | **13 points** (2 stories: 8 + 5) |
| **Stories Included** | `STORY-014` (Cyclic LangGraph StateGraph), `STORY-015` (Workflow Adapter & Agentic-KGR) |
| **Lead** | @member1 (LangGraph StateGraph, Planner/Extractor Nodes, Self-Reflection Loop) |
| **Support** | @member2 (A2A Verification Integration, Workflow Adapter, Legacy Test Regression) |
| **Estimated Time** | ~12 hours total |
| **Prerequisite** | Sprint 1, 2, and 3 Gates passing (**75 cumulative tests passed**) |
| **Master Spec Ref** | [autonomoustechspec.md](file:///Users/sohithsai/multiagent_knowledgegraph/autonomoustechspec.md) §3.5, §1.2, §5.1 |
| **Task Breakdown Ref** | [new_taskbreakdown.md](file:///Users/sohithsai/multiagent_knowledgegraph/new_taskbreakdown.md) Sprint 4 (`AGT-001` through `WFK-003`) |

---

> **HOW TO USE THIS GUIDE**
> 
> Read every section before executing commands. Each task contains:
> - A **WHY & ARCHITECTURAL PATCHES** block — explains state machine mechanics, cyclic control flow, and edge cases.
> - An **exact drop-in code block** — copy-paste it directly to eliminate human transcription errors.
> - A **VERIFICATION CHECK** — run immediately after the step.
> - An **IF IT FAILS** block — targeted diagnostics if an error occurs.
>
> **Sequential Testing Rule:** Never proceed to the next story until the current story's `⛔ GATE` command passes 100%.

---

## Section 0 — Pre-Flight Checks

Run all 4 checks before modifying or writing code.

---

### Check 0.1 — Confirm Working Directory

```bash
pwd
```

**VERIFICATION CHECK 0.1**  
Must show:
```
/Users/sohithsai/multiagent_knowledgegraph
```

**IF IT FAILS:**
```bash
cd /Users/sohithsai/multiagent_knowledgegraph
pwd
```

---

### Check 0.2 — Confirm Virtual Environment Python

```bash
./venv/bin/python3 --version
```

**VERIFICATION CHECK 0.2**  
Must show:
```
Python 3.9.x
```

---

### Check 0.3 — Confirm Cumulative Regression Suite Passes (Sprint 1, 2 & 3)

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py tests/test_irs_resolver.py tests/test_ontology_validator.py tests/test_lock_manager.py tests/test_llm_factory.py tests/test_conflict_detector.py tests/test_arbitration_engine.py tests/test_mpac_coordinator.py tests/test_adhoc_coordinator.py tests/test_ablation_coordinator.py tests/test_cti_mcp_server.py tests/test_mcp_client.py tests/test_a2a_peer_hub.py -q
```

**VERIFICATION CHECK 0.3**  
Must end with:
```
75 passed in 0.xxs
```

---

### Check 0.4 — Zero Non-Breaking Spaces (`U+00A0`) & Zero-Width Spaces (`U+200B`)

Run this sanitization sweep to ensure no non-ASCII whitespaces pollute source or test files:
```bash
LC_ALL=C sed -i '' $'s/\u00a0/ /g; s/\u200b//g' src/**/*.py tests/*.py mcp/**/*.py 2>/dev/null || true
```

---

## Section 1 — Preempted Architectural Pitfalls & Patches for Sprint 4

* **1. `CoordinationResult` Frozen Model and Schema Strictness (`extra="forbid"`):**
  In Sprint 1 (`STORY-001`), `CoordinationResult` in `src/schemas/models.py` was defined with `model_config = ConfigDict(frozen=True, extra="forbid")`. Its fields are strictly: `status`, `detail`, `protocol`, `latency_ms`, `operations_attempted: int = 0`, `operations_committed: int = 0`, and `conflict_detected: bool = False`. Never pass non-existent fields (`operations_evaluated`, `operations_rejected`, `conflicts_detected`, `arbitrations_performed`). Tests and coordinator mocks must strictly instantiate valid schema fields.
* **2. `OntologyValidator` Async API Alignment (`validate_and_route`):**
  `OntologyValidator` defines `validate(proposed_term, category, confirmation_count)` and `async def validate_and_route(proposed_term, category, principal, neo4j_client)`. `extractor_node` invokes `await self._ontology.validate_and_route(q.subject_label, "NODE_LABEL", state["principal"], self._neo4j)` and `await self._ontology.validate_and_route(q.predicate, "RELATIONSHIP_TYPE", state["principal"], self._neo4j)` to support Tier-2 provisional ontology governance.
* **3. `MPACAblationCoordinator` Constructor Signature:**
  In `_make_coordinator()`, `MPACAblationCoordinator` takes `client` as its first positional argument and `ablation_mode` as its second argument: `MPACAblationCoordinator(neo4j_client, ablations[p], lock_manager=lock_manager)`.
* **4. Offline Fallback for Structured Extraction (`invoke_structured_llm`):**
  When running in offline environments or tests without live LLM API keys, `await invoke_structured_llm(prompt, ExtractedQuadBatch)` is wrapped in `try...except Exception`, returning `ExtractedQuadBatch(quads=[])`. This triggers deterministic extraction from `state["mcp_evidence_log"]` seamlessly.
* **5. Closed-Loop Agentic-KGR Reflection on Defeated Claims:**
  In `MPACCoordinator`, defeated claims resolve arbitration with `operations_committed == 0` (and `status="success"` or `"RESOLVED"`). `mpac_commit_and_reflect` and `route_after_commit` check `coord_res.get("status") in ("failure", "partial") or (coord_res.get("operations_attempted", 0) > 0 and coord_res.get("operations_committed", 0) == 0)` to trigger reflection and finite re-extraction.
* **6. Tool Slicing & Unknown Tool Wire Parity:**
  In `mcp_tool_node`, tool calls are sliced to `remaining = max(0, state["max_tool_calls"] - state["tool_call_count"])`. If an unknown tool is invoked by an LLM, a corresponding `ToolMessage(content="Error: Tool ... not found", tool_call_id=call["id"])` is emitted and `executed_calls` is incremented to prevent LangChain wire mismatch errors and infinite loops.
* **7. Tier-1 IOC Type Label Mapping & IRS Canonicalization:**
  In fallback extraction, `tel.get("ioc_type")` is mapped using `_IOC_TYPE_TO_LABEL` (`FileHash` uses `HAS_SAMPLE`, while network IOCs use `USES_C2`). In `submit_to_coordinator` (`src/agents/workflow.py`), `claim` is canonicalized via `IdentityResolutionService().canonicalize_operation(claim.model_copy(update={"is_functional": True}))`.
* **8. LangGraph Tool Execution Wire Synchronization & Message ID Uniqueness:**
  In a cyclic `StateGraph`, `planner_node` explicitly assigns unique UUIDs to every outbound message (`if not getattr(response, "id", None): response.id = str(uuid.uuid4())`), preventing `add_messages` from overwriting prior turns.

---

## STORY-014: Cyclic LangGraph `StateGraph` Autonomous Investigator

| Field | Details |
|---|---|
| **Story ID** | `STORY-014` |
| **Story Points** | **8 points** |
| **Target Files** | `src/agents/investigator.py`, `tests/test_investigator.py` |
| **Tasks** | `AGT-001`, `AGT-002`, `AGT-003`, `AGT-004`, `AGT-005` |

---

### Step S4-014-A — Implement `src/agents/investigator.py`

Create `src/agents/investigator.py`:

```python
"""
Truly Autonomous Cyclic LangGraph CTI Investigator
File: src/agents/investigator.py
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Any, Dict, List, Literal, TypedDict
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from src.a2a.peer_hub import A2APeerHub
from src.agents.llm_factory import get_chat_llm, invoke_structured_llm
from src.coordination.base import BaseCoordinator
from src.irs.resolver import IdentityResolutionService
from src.mcp_servers.mcp_client import RealMCPClientManager
from src.ontology.validator import OntologyValidator
from src.schemas.models import GraphOperation

logger = logging.getLogger(__name__)

_IOC_TYPE_TO_LABEL = {
    "ip": "IP",
    "ip:port": "IP",
    "domain": "Domain",
    "url": "URL",
    "sha256_hash": "FileHash",
    "sha1_hash": "FileHash",
    "md5_hash": "FileHash",
    "hash": "FileHash",
}


class ExtractedSemanticQuad(BaseModel):
    subject_label: str = Field(description="Entity class e.g. IP, URL, Domain, FileHash")
    subject_value: str = Field(description="The indicator value")
    predicate: str = Field(description="Relationship type e.g. USES_C2, DISTRIBUTED_VIA, HAS_SAMPLE, HOSTED_ON")
    object_label: str = Field(description="Target entity class e.g. Malware, ThreatActor")
    object_value: str = Field(description="Target entity name e.g. RedLine Stealer, Emotet")
    confidence: int = Field(default=80, description="Confidence score 0-100")
    evidence_id: str = Field(default="", description="Source record_id")
    raw_evidence_hash: str = Field(default="", description="SHA256 hash from MCP record")
    upstream_origin_signature: str = Field(default="", description="Origin signature from MCP record")
    valid_from: str = Field(default="2026-10-12T00:00:00Z", description="ISO8601 timestamp")


class ExtractedQuadBatch(BaseModel):
    quads: List[ExtractedSemanticQuad] = Field(
        default_factory=list, description="All threat relationships extracted from MCP telemetry"
    )
    reasoning_summary: str = Field(
        default="", description="Analytical explanation of extracted subgraph"
    )


class InvestigatorGraphState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    principal: str
    seed_ioc: str
    tool_call_count: int
    max_tool_calls: int
    mcp_evidence_log: List[str]
    ontology_schema: Dict[str, Any]
    extracted_operations: List[GraphOperation]
    rejection_feedback: List[str]
    refinement_done: bool
    coordination_result: Dict[str, Any]


class AutonomousCTIInvestigator:
    """True LangGraph StateGraph agent driven by LLM decisions over real MCP and A2A."""

    def __init__(
        self,
        coordinator: BaseCoordinator,
        a2a_hub: A2APeerHub,
        neo4j_client=None,
        max_tool_calls: int = 4,
        mcp_manager: RealMCPClientManager | None = None,
    ):
        self._coordinator = coordinator
        self._a2a = a2a_hub
        self._neo4j = neo4j_client
        self._max_tool_calls = max_tool_calls
        self._irs = IdentityResolutionService()
        self._ontology = OntologyValidator(neo4j_client=neo4j_client)
        self._mcp_mgr = mcp_manager or RealMCPClientManager()

    async def run_investigation(self, principal: str, ioc_value: str) -> Dict[str, Any]:
        """Opens a real MCP JSON-RPC session, compiles the cyclic LangGraph, and runs the investigation."""
        async with self._mcp_mgr.session() as mcp_session:
            ontology_schema = await self._mcp_mgr.read_ontology_resource(mcp_session)
            mcp_tools = await self._mcp_mgr.discover_langchain_tools(mcp_session, bound_principal=principal)
            tools_by_name = {t.name: t for t in mcp_tools}
            planner_llm = get_chat_llm(temperature=0.0).bind_tools(mcp_tools)

            async def planner_node(state: InvestigatorGraphState) -> Dict[str, Any]:
                if state["tool_call_count"] >= state["max_tool_calls"]:
                    return {"messages": [AIMessage(id=str(uuid.uuid4()), content="HOP_BUDGET_REACHED: Proceed to extraction.")]}
                response = await planner_llm.ainvoke(state["messages"])
                if not getattr(response, "id", None):
                    response.id = str(uuid.uuid4())
                return {"messages": [response]}

            def route_after_planner(state: InvestigatorGraphState) -> Literal["mcp_tool_node", "extractor_node"]:
                last_msg = state["messages"][-1]
                if (
                    isinstance(last_msg, AIMessage)
                    and getattr(last_msg, "tool_calls", None)
                    and state["tool_call_count"] < state["max_tool_calls"]
                ):
                    return "mcp_tool_node"
                return "extractor_node"

            async def mcp_tool_node(state: InvestigatorGraphState) -> Dict[str, Any]:
                last_ai = state["messages"][-1]
                tool_msgs: List[BaseMessage] = []
                new_logs = list(state["mcp_evidence_log"])
                executed_calls = 0

                remaining = max(0, state["max_tool_calls"] - state["tool_call_count"])
                tool_calls = getattr(last_ai, "tool_calls", [])[:remaining]

                for call in tool_calls:
                    tool_name = call["name"]
                    args = call["args"]
                    if tool_name in tools_by_name:
                        raw_output = await tools_by_name[tool_name].ainvoke(args)
                        executed_calls += 1
                        new_logs.append(raw_output)
                        tool_msgs.append(
                            ToolMessage(
                                content=raw_output,
                                tool_call_id=call["id"],
                                name=tool_name,
                            )
                        )
                    else:
                        executed_calls += 1
                        err_msg = f"Error: Tool {tool_name} not found"
                        new_logs.append(err_msg)
                        tool_msgs.append(
                            ToolMessage(
                                content=err_msg,
                                tool_call_id=call["id"],
                                name=tool_name,
                            )
                        )

                return {
                    "messages": tool_msgs,
                    "tool_call_count": state["tool_call_count"] + executed_calls,
                    "mcp_evidence_log": new_logs,
                }

            async def extractor_node(state: InvestigatorGraphState) -> Dict[str, Any]:
                raw_log_combined = "\n".join(state["mcp_evidence_log"])
                rejection_context = ""
                if state["rejection_feedback"]:
                    rejection_context = (
                        f"\nPREVIOUS REJECTION FEEDBACK: {json.dumps(state['rejection_feedback'])}\n"
                        f"Refine your extraction to resolve this feedback."
                    )

                prompt = (
                    f"You are a CTI Extractor parsing raw telemetry for Principal '{state['principal']}'.\n"
                    f"Ontology Schema: {json.dumps(state['ontology_schema'])}\n"
                    f"Seed IOC: {state['seed_ioc']}\n"
                    f"Raw MCP Evidence Log:\n{raw_log_combined}\n"
                    f"{rejection_context}\n"
                    f"Extract all verified threat relationships as semantic quads."
                )

                try:
                    extracted_batch = await invoke_structured_llm(prompt, ExtractedQuadBatch)
                except Exception:
                    extracted_batch = ExtractedQuadBatch(quads=[])

                ops: List[GraphOperation] = []

                for q in extracted_batch.quads:
                    ont_node = await self._ontology.validate_and_route(
                        q.subject_label, "NODE_LABEL", state["principal"], self._neo4j
                    )
                    ont_pred = await self._ontology.validate_and_route(
                        q.predicate, "RELATIONSHIP_TYPE", state["principal"], self._neo4j
                    )

                    node_label = ont_node.get("canonical_term", q.subject_label) if isinstance(ont_node, dict) else getattr(ont_node, "canonical_term", q.subject_label)
                    predicate_name = ont_pred.get("canonical_term", q.predicate) if isinstance(ont_pred, dict) else getattr(ont_pred, "canonical_term", q.predicate)
                    is_functional = ont_pred.get("is_functional", self._ontology.is_predicate_functional(predicate_name)) if isinstance(ont_pred, dict) else self._ontology.is_predicate_functional(predicate_name)

                    draft_op = GraphOperation(
                        operation="MERGE",
                        operation_id=str(uuid.uuid4()),
                        lock_keys=[f"{node_label.lower()}:{q.subject_value}"],
                        principal=state["principal"],
                        node_label=node_label,
                        node_key="value",
                        node_value=q.subject_value,
                        predicate=predicate_name,
                        target_label=q.object_label,
                        target_key="name",
                        target_value=q.object_value,
                        confidence=q.confidence,
                        evidence_ids=[q.evidence_id] if q.evidence_id else [],
                        raw_evidence_hash=q.raw_evidence_hash,
                        upstream_origin_signature=q.upstream_origin_signature,
                        valid_from=q.valid_from,
                        is_functional=is_functional,
                    )
                    ops.append(self._irs.canonicalize_operation(draft_op))

                # Fallback: if LLM returned 0 quads but raw MCP log contains matches, extract deterministically
                if not ops and state["mcp_evidence_log"]:
                    for raw_chunk in state["mcp_evidence_log"]:
                        try:
                            parsed_chunk = json.loads(raw_chunk)
                            matches = parsed_chunk.get("matches", [])
                            for m in matches:
                                tel = m.get("trusted_telemetry", {})
                                if tel.get("malware_family"):
                                    raw_type = tel.get("ioc_type", "ip").lower()
                                    node_label = "IP"
                                    for k, v in _IOC_TYPE_TO_LABEL.items():
                                        if k in raw_type:
                                            node_label = v
                                            break
                                    pred = "HAS_SAMPLE" if node_label == "FileHash" else "USES_C2"
                                    ioc_val = tel.get("ioc_value", state["seed_ioc"])
                                    draft_op = GraphOperation(
                                        operation="MERGE",
                                        operation_id=str(uuid.uuid4()),
                                        lock_keys=[f"{node_label.lower()}:{ioc_val}"],
                                        principal=state["principal"],
                                        node_label=node_label,
                                        node_key="value",
                                        node_value=ioc_val,
                                        predicate=pred,
                                        target_label="Malware",
                                        target_key="name",
                                        target_value=tel.get("malware_family"),
                                        confidence=tel.get("confidence", 85),
                                        evidence_ids=[tel.get("record_id", "")],
                                        raw_evidence_hash=m.get("raw_evidence_sha256", ""),
                                        upstream_origin_signature=m.get("upstream_origin_signature", ""),
                                        valid_from=tel.get("timestamp", "2026-10-12T00:00:00Z"),
                                        is_functional=True,
                                    )
                                    ops.append(self._irs.canonicalize_operation(draft_op))
                        except Exception:
                            pass

                return {"extracted_operations": ops, "refinement_done": bool(state["rejection_feedback"])}

            async def a2a_verify_node(state: InvestigatorGraphState) -> Dict[str, Any]:
                verified_ops: List[GraphOperation] = []
                for op in state["extracted_operations"]:
                    attestations = await self._a2a.verify_claim_with_peers(
                        requesting_principal=state["principal"],
                        ioc_value=op.node_value,
                        predicate=op.predicate,
                        claimed_target=op.target_value,
                    )
                    verified_ops.append(op.model_copy(update={"peer_attestations": attestations}))
                return {"extracted_operations": verified_ops}

            async def mpac_commit_and_reflect(state: InvestigatorGraphState) -> Dict[str, Any]:
                if not state["extracted_operations"]:
                    return {"coordination_result": {"status": "empty", "operations_committed": 0}}

                res = await self._coordinator.submit(state["extracted_operations"])
                res_dict = res.model_dump()
                feedback = list(state["rejection_feedback"])
                is_rejected = (
                    res.status in ("partial", "failure")
                    or (res.operations_attempted > 0 and res.operations_committed == 0)
                )
                if is_rejected:
                    feedback.append(res.detail or "Claim rejected during MPAC arbitration")
                return {
                    "coordination_result": res_dict,
                    "rejection_feedback": feedback,
                }

            def route_after_commit(state: InvestigatorGraphState) -> Literal["extractor_node", "__end__"]:
                coord_res = state["coordination_result"]
                is_rejected = (
                    coord_res.get("status") in ("failure", "partial")
                    or (coord_res.get("operations_attempted", 0) > 0 and coord_res.get("operations_committed", 0) == 0)
                )
                if (
                    is_rejected
                    and not state["refinement_done"]
                    and state["rejection_feedback"]
                ):
                    return "extractor_node"
                return END

            workflow = StateGraph(InvestigatorGraphState)
            workflow.add_node("planner_node", planner_node)
            workflow.add_node("mcp_tool_node", mcp_tool_node)
            workflow.add_node("extractor_node", extractor_node)
            workflow.add_node("a2a_verify_node", a2a_verify_node)
            workflow.add_node("mpac_commit_and_reflect", mpac_commit_and_reflect)

            workflow.add_edge(START, "planner_node")
            workflow.add_conditional_edges("planner_node", route_after_planner)
            workflow.add_edge("mcp_tool_node", "planner_node")
            workflow.add_edge("extractor_node", "a2a_verify_node")
            workflow.add_edge("a2a_verify_node", "mpac_commit_and_reflect")
            workflow.add_conditional_edges("mpac_commit_and_reflect", route_after_commit)

            compiled_graph = workflow.compile()

            initial_state: InvestigatorGraphState = {
                "messages": [
                    SystemMessage(
                        content=(
                            f"You are the autonomous CTI Investigator for Principal '{principal}'. "
                            f"First call `search_cti_indicator` on the seed IOC. If you discover an associated "
                            f"malware family, autonomously call `pivot_by_malware_family` to map related infrastructure "
                            f"before concluding your investigation."
                        )
                    ),
                    HumanMessage(content=f"Investigate IOC: {ioc_value}"),
                ],
                "principal": principal,
                "seed_ioc": ioc_value,
                "tool_call_count": 0,
                "max_tool_calls": self._max_tool_calls,
                "mcp_evidence_log": [],
                "ontology_schema": ontology_schema,
                "extracted_operations": [],
                "rejection_feedback": [],
                "refinement_done": False,
                "coordination_result": {},
            }

            return await compiled_graph.ainvoke(initial_state)
```

---

### Step S4-014-B — Write Comprehensive Tests in `tests/test_investigator.py`

Create `tests/test_investigator.py`:

```python
"""
Tests for Autonomous Cyclic LangGraph CTI Investigator — STORY-014.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_investigator.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage
import pytest

from src.agents.investigator import AutonomousCTIInvestigator
from src.schemas.models import CoordinationResult


@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.submit = AsyncMock(
        return_value=CoordinationResult(
            status="success",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            detail="All operations accepted",
        )
    )
    return coord


@pytest.fixture
def mock_a2a_hub():
    hub = MagicMock()
    hub.verify_claim_with_peers = AsyncMock(return_value=[])
    return hub


@pytest.mark.asyncio
async def test_investigator_cyclic_tool_execution_and_commit(mock_coordinator, mock_a2a_hub):
    investigator = AutonomousCTIInvestigator(
        coordinator=mock_coordinator,
        a2a_hub=mock_a2a_hub,
        max_tool_calls=2,
    )

    # First turn: planner decides to call search_cti_indicator
    ai_call_1 = AIMessage(
        content="Searching CTI indicator",
        tool_calls=[
            {
                "name": "search_cti_indicator",
                "args": {"ioc_value": "139.59.33.238"},
                "id": "call_1",
            }
        ],
    )
    # Second turn: planner decides investigation is complete
    ai_done = AIMessage(content="Investigation complete.")

    mock_chat_llm = MagicMock()
    mock_chat_llm.ainvoke = AsyncMock(side_effect=[ai_call_1, ai_done])
    mock_chat_llm.bind_tools = MagicMock(return_value=mock_chat_llm)

    from src.agents.investigator import ExtractedQuadBatch, ExtractedSemanticQuad
    fake_batch = ExtractedQuadBatch(
        quads=[
            ExtractedSemanticQuad(
                subject_label="IP",
                subject_value="139.59.33.238",
                predicate="USES_C2",
                object_label="Malware",
                object_value="Jackskid",
                confidence=90,
                evidence_id="1961358",
                raw_evidence_hash="sha256:1234",
                upstream_origin_signature="deepfield:139.59.33.238:jackskid",
            )
        ],
        reasoning_summary="Extracted C2 relationship",
    )

    with patch("src.agents.investigator.get_chat_llm", return_value=mock_chat_llm), \
         patch("src.agents.investigator.invoke_structured_llm", new_callable=AsyncMock, return_value=fake_batch):
        result = await investigator.run_investigation(
            principal="threatfox",
            ioc_value="139.59.33.238",
        )

        assert "coordination_result" in result
        assert result["coordination_result"]["status"] == "success"
        assert result["tool_call_count"] == 1
        assert len(result["mcp_evidence_log"]) == 1
        assert "139.59.33.238" in result["mcp_evidence_log"][0]
        mock_coordinator.submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_investigator_hop_budget_prevents_infinite_loop(mock_coordinator, mock_a2a_hub):
    import uuid
    investigator = AutonomousCTIInvestigator(
        coordinator=mock_coordinator,
        a2a_hub=mock_a2a_hub,
        max_tool_calls=2,
    )

    def _make_loop_call(*args, **kwargs):
        return AIMessage(
            id=str(uuid.uuid4()),
            content="Looping call",
            tool_calls=[
                {
                    "name": "search_cti_indicator",
                    "args": {"ioc_value": "1.1.1.1"},
                    "id": str(uuid.uuid4()),
                }
            ],
        )

    mock_chat_llm = MagicMock()
    mock_chat_llm.ainvoke = AsyncMock(side_effect=_make_loop_call)
    mock_chat_llm.bind_tools = MagicMock(return_value=mock_chat_llm)

    from src.agents.investigator import ExtractedQuadBatch
    empty_batch = ExtractedQuadBatch(quads=[], reasoning_summary="No quads")

    with patch("src.agents.investigator.get_chat_llm", return_value=mock_chat_llm), \
         patch("src.agents.investigator.invoke_structured_llm", new_callable=AsyncMock, return_value=empty_batch):
        result = await investigator.run_investigation(
            principal="threatfox",
            ioc_value="1.1.1.1",
        )
        # Verify execution halted cleanly at max_tool_calls limit
        assert result["tool_call_count"] == 2
```

---

### Verification & Gate for STORY-014

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_investigator.py -v
```

Must output:
```
2 passed in 0.xxs
```

---

## STORY-015: Backward-Compatible Workflow Adapter & Agentic-KGR Reflection

| Field | Details |
|---|---|
| **Story ID** | `STORY-015` |
| **Story Points** | **5 points** |
| **Target Files** | `src/agents/workflow.py`, `tests/test_agent_workflow.py` |
| **Tasks** | `WFK-001`, `WFK-002`, `WFK-003` |

---

### Step S4-015-A — Update `src/agents/workflow.py`

Preserve the legacy signature of `run_agent()` while integrating coordinator routing, IRS canonicalization, and telemetry:

```python
"""
LangGraph Agent Workflow & Backward-Compatible Adapter — STORY-015.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from src.llm.llm_tool import LLMEnrichmentTool
from langgraph.graph import END, StateGraph

from src.agents.a2a import G2CPPeerHub
from src.agents.state import AgentState
from src.coordination.adhoc import AdHocCoordinator
from src.coordination.mpac import MPACCoordinator
from src.coordination.ablation import MPACAblationCoordinator
from src.irs.resolver import IdentityResolutionService
from src.mcp.tools import MCP_TOOLS
from src.schemas.models import CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)

# Map IOC types found in normalized JSON to Neo4j Tier-1 node labels
_IOC_TYPE_TO_LABEL: dict[str, str] = {
    "ip:port":   "IP",
    "ip":        "IP",
    "domain":    "Domain",
    "url":       "URL",
    "md5_hash":  "FileHash",
    "sha256_hash": "FileHash",
    "sha1_hash": "FileHash",
    "hash":      "FileHash",
    "malware":   "Malware",
}
_LLM_PROPERTY_ALLOWLIST = {"tactics", "severity", "cve", "description", "mitre_attack_ids"}


def _ioc_type_to_label(ioc_type: str | None) -> str:
    """Convert a normalized IOC type string to a Neo4j node label."""
    if ioc_type:
        for key, label in _IOC_TYPE_TO_LABEL.items():
            if key in ioc_type.lower():
                return label
    return "Malware"


def _make_coordinator(protocol: str, neo4j_client: Any, lock_manager: Any = None):
    """Instantiate the correct coordinator for the given protocol string."""
    p = (protocol or "").strip().lower()
    if p == "adhoc":
        return AdHocCoordinator(neo4j_client)
    if p in ("mpac", "g2cp", "protocol2"):
        return MPACCoordinator(neo4j_client, lock_manager=lock_manager)
    ablations = {
        "ablation_no_a2a": "no_a2a",
        "no_a2a": "no_a2a",
        "ablation_no_locks": "no_semantic_locks",
        "no_semantic_locks": "no_semantic_locks",
        "ablation_timestamp": "timestamp_ordered",
        "timestamp_ordered": "timestamp_ordered",
        "fcfs_arb": "fcfs_arb",
    }
    if p in ablations:
        return MPACAblationCoordinator(neo4j_client, ablations[p], lock_manager=lock_manager)
    raise ValueError(f"Unsupported coordination protocol: {protocol!r}")


# ──────────────────────────────────────────────────────────────────────────────
# Node 1 – receive
# ──────────────────────────────────────────────────────────────────────────────

async def receive(state: AgentState) -> dict:
    """Validate that the required inputs are present in the initial state.

    Returns an error if ``ioc_value`` or ``principal_id`` is missing.
    """
    if not state.get("ioc_value"):
        return {"error": "ioc_value is required"}
    if not state.get("principal_id"):
        return {"error": "principal_id is required"}
    logger.info(
        "[%s] Received IOC: %s (protocol=%s)",
        state["principal_id"],
        state["ioc_value"],
        state.get("protocol", "mpac"),
    )
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# Node 2 – fetch_evidence
# ──────────────────────────────────────────────────────────────────────────────

async def fetch_evidence(state: AgentState) -> dict:
    """Use the principal's MCP tool to look up the IOC in local data files."""
    if state.get("error"):
        return {}

    principal_id: str = state["principal_id"]
    ioc_value: str = state["ioc_value"]

    tool = MCP_TOOLS.get(principal_id)
    if tool is None:
        return {
            "error": f"No MCP tool registered for principal {principal_id!r}",
            "evidence": [],
        }

    response = tool.invoke(ioc_value)
    evidence = response.records  # list of dicts

    claim_malware_family: str | None = None
    node_label = "Malware"
    if evidence:
        first = evidence[0]
        claim_malware_family = first.get("malware_family")
        node_label = _ioc_type_to_label(first.get("ioc_type"))

    logger.info(
        "[%s] fetch_evidence: %d record(s), label=%s, malware_family=%s",
        principal_id,
        len(evidence),
        node_label,
        claim_malware_family,
    )
    return {
        "evidence": evidence,
        "claim_malware_family": claim_malware_family,
        "node_label": node_label,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Node 3 – extract_claim
# ──────────────────────────────────────────────────────────────────────────────

async def extract_claim(state: AgentState) -> dict:
    """Build a GraphOperation (the 'claim') from the fetched evidence."""
    if state.get("error"):
        return {}

    evidence: list[dict] = state.get("evidence", [])
    if not evidence:
        logger.info("[%s] No evidence — claim is None", state.get("principal_id"))
        return {"claim": None}

    first = evidence[0]
    ioc_value: str = state["ioc_value"]
    principal_id: str = state["principal_id"]
    node_label: str = state.get("node_label", "Malware")
    ioc_type = str(first.get("ioc_type", "")).lower()
    if node_label in {"IP", "Domain", "URL"}:
        node_key = "value"
    elif node_label == "FileHash" and "sha256" in ioc_type:
        node_key = "sha256"
    elif node_label == "FileHash" and "md5" in ioc_type:
        node_key = "md5"
    elif node_label == "FileHash" and "sha1" in ioc_type:
        node_key = "sha1"
    else:
        node_key = "name" if node_label in {"Malware", "ThreatActor"} else "id"
    malware_family: str | None = state.get("claim_malware_family")

    properties: dict[str, Any] = {
        k: v
        for k, v in first.items()
        if k not in ("ioc_value", "ioc_type") and v is not None
    }
    if malware_family:
        properties["malware_family"] = malware_family

    try:
        claim = GraphOperation(
            operation_type="MERGE",
            operation_id=str(uuid.uuid4()),
            lock_keys=[f"{ioc_type or node_label.lower()}:{ioc_value.strip().lower()}"],
            node_label=node_label,
            node_key=node_key,
            node_value=ioc_value,
            properties=properties,
            principal=principal_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] Failed to build GraphOperation: %s", principal_id, exc)
        return {"error": str(exc), "claim": None}

    logger.info("[%s] extract_claim: built GraphOperation (label=%s)", principal_id, node_label)
    return {"claim": claim}


# ──────────────────────────────────────────────────────────────────────────────
# Node 4 – enrich_with_llm  (Story 011)
# ──────────────────────────────────────────────────────────────────────────────

async def enrich_with_llm(state: AgentState) -> dict:
    """Call the LLM to enrich the claim with a summary and extra properties."""
    if state.get("error"):
        return {}

    claim: GraphOperation | None = state.get("claim")
    if claim is None:
        return {}

    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        logger.info(
            "[%s] LLM_API_KEY not set — skipping LLM enrichment",
            state.get("principal_id"),
        )
        return {"llm_summary": "", "llm_extra_props": {}}

    try:
        tool = LLMEnrichmentTool(api_key=api_key)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Cannot create LLMEnrichmentTool: %s", exc)
        return {"llm_summary": "", "llm_extra_props": {}}

    evidence: list[dict] = state.get("evidence", [])
    first = evidence[0] if evidence else {}
    evidence_sample = {
        k: first.get(k)
        for k in ("ioc_type", "malware_family", "confidence", "threat_type", "source")
        if k in first
    }

    enrichment = await tool.enrich(
        ioc_value=state["ioc_value"],
        node_label=state.get("node_label", "Malware"),
        malware_family=state.get("claim_malware_family"),
        evidence_sample=evidence_sample,
    )

    update: dict[str, Any] = {
        "llm_summary": enrichment.get("summary", ""),
        "llm_extra_props": enrichment.get("extra_props", {}),
    }

    proposed_props = enrichment.get("extra_props") or {}
    extra_props: dict[str, Any] = {}
    if isinstance(proposed_props, dict):
        for key, value in proposed_props.items():
            if key not in _LLM_PROPERTY_ALLOWLIST:
                continue
            if isinstance(value, str) and len(value) <= 1000:
                extra_props[key] = value
            elif isinstance(value, list) and len(value) <= 50 and all(
                isinstance(item, str) and len(item) <= 200 for item in value
            ):
                extra_props[key] = value

    new_label: str | None = None

    if extra_props or new_label:
        merged_props = {**dict(claim.properties), **extra_props}
        final_label = new_label if new_label else claim.node_label
        claim_data = claim.model_dump(by_alias=True)
        claim_data["properties"] = merged_props
        claim_data["node_label"] = final_label
        update["claim"] = GraphOperation(**claim_data)
        if new_label:
            update["node_label"] = new_label

    logger.info(
        "[%s] enrich_with_llm: summary=%r extra_props_keys=%s new_label=%s",
        state.get("principal_id"),
        enrichment.get("summary", "")[:60],
        list(extra_props.keys()),
        new_label,
    )
    return update


# ──────────────────────────────────────────────────────────────────────────────
# Node 5 – a2a_peer_check
# ──────────────────────────────────────────────────────────────────────────────

async def a2a_peer_check(state: AgentState) -> dict:
    """Broadcast the IOC to peer agents and collect a consensus score."""
    if state.get("error"):
        return {}
    if state.get("protocol") == "ablation_no_a2a":
        return {"peer_votes": [], "consensus_score": 0.5}

    hub = G2CPPeerHub()
    try:
        votes, score = await hub.query_peers(
            ioc_value=state["ioc_value"],
            requesting_agent_id=state["principal_id"],
            claim_malware_family=state.get("claim_malware_family"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] A2A peer check failed: %s", state.get("principal_id"), exc)
        return {"peer_votes": [], "consensus_score": 0.5}

    logger.info(
        "[%s] a2a_peer_check: votes=%s score=%.3f",
        state.get("principal_id"),
        [v.vote for v in votes],
        score,
    )
    return {"peer_votes": votes, "consensus_score": score}


# ──────────────────────────────────────────────────────────────────────────────
# Node 6 – submit_to_coordinator
# ──────────────────────────────────────────────────────────────────────────────

async def submit_to_coordinator(state: AgentState) -> dict:
    """Submit the (enriched) GraphOperation to the coordinator."""
    if state.get("error"):
        return {
            "result": CoordinationResult(
                status="failure",
                detail=state["error"],
                protocol=state.get("protocol", "mpac"),
            )
        }

    claim: GraphOperation | None = state.get("claim")
    if claim is None:
        # No evidence — produce a graceful no-op result
        return {
            "result": CoordinationResult(
                status="success",
                detail="No evidence found; nothing to write",
                protocol=state.get("protocol", "mpac"),
            )
        }

    try:
        claim = IdentityResolutionService().canonicalize_operation(
            claim.model_copy(update={"is_functional": True})
        )
    except Exception as exc:
        logger.warning("[%s] Failed to canonicalize claim via IRS: %s", state.get("principal_id"), exc)

    neo4j_client = state.get("neo4j_client")
    if neo4j_client is None:
        return {
            "result": CoordinationResult(
                status="failure",
                detail="neo4j_client not provided in initial state",
                protocol=state.get("protocol", "mpac"),
            )
        }

    protocol = state.get("protocol", "mpac")
    coordinator = _make_coordinator(protocol, neo4j_client, state.get("lock_manager"))

    try:
        result = await coordinator.submit(claim)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[%s] Coordinator submission failed: %s",
            state.get("principal_id"),
            exc,
        )
        return {
            "result": CoordinationResult(
                status="failure",
                detail=str(exc),
                protocol=protocol,
            )
        }

    logger.info(
        "[%s] submit_to_coordinator: status=%s latency_ms=%.1f",
        state.get("principal_id"),
        result.status,
        result.latency_ms,
    )
    return {"result": result}


# ──────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ──────────────────────────────────────────────────────────────────────────────

def build_agent_graph() -> StateGraph:
    """Build and compile the LangGraph state machine."""
    graph = StateGraph(AgentState)

    graph.add_node("receive",               receive)
    graph.add_node("fetch_evidence",        fetch_evidence)
    graph.add_node("extract_claim",         extract_claim)
    graph.add_node("enrich_with_llm",       enrich_with_llm)
    graph.add_node("a2a_peer_check",        a2a_peer_check)
    graph.add_node("submit_to_coordinator", submit_to_coordinator)

    graph.set_entry_point("receive")
    graph.add_edge("receive",               "fetch_evidence")
    graph.add_edge("fetch_evidence",        "extract_claim")
    graph.add_edge("extract_claim",         "enrich_with_llm")
    graph.add_edge("enrich_with_llm",       "a2a_peer_check")
    graph.add_edge("a2a_peer_check",        "submit_to_coordinator")
    graph.add_edge("submit_to_coordinator", END)

    return graph.compile()


# ──────────────────────────────────────────────────────────────────────────────
# Convenience runner
# ──────────────────────────────────────────────────────────────────────────────

async def run_agent(
    *,
    principal_id: str,
    ioc_value: str,
    protocol: str = "mpac",
    neo4j_client: Any = None,
    lock_manager: Any = None,
    graph=None,
) -> AgentState:
    """Run the full agent workflow for a single IOC."""
    if graph is None:
        graph = build_agent_graph()

    initial_state: AgentState = {
        "principal_id": principal_id,
        "ioc_value": ioc_value,
        "protocol": protocol,
        "neo4j_client": neo4j_client,
        "lock_manager": lock_manager,
        "evidence": [],
        "claim_malware_family": None,
        "node_label": "Malware",
        "claim": None,
        "peer_votes": [],
        "consensus_score": 0.5,
        "result": None,
        "error": None,
        "llm_summary": None,
        "llm_extra_props": None,
    }

    final_state: AgentState = await graph.ainvoke(initial_state)
    return final_state
```

---

### Step S4-015-B — Write Comprehensive Tests in `tests/test_agent_workflow.py`

Create `tests/test_agent_workflow.py`:

```python
"""
Tests for Backward-Compatible Workflow Adapter — STORY-015.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.workflow import _make_coordinator, run_agent
from src.coordination.ablation import MPACAblationCoordinator
from src.coordination.adhoc import AdHocCoordinator
from src.coordination.mpac import MPACCoordinator
from src.schemas.models import CoordinationResult


def test_make_coordinator_factory():
    client = MagicMock()
    lock = MagicMock()
    assert isinstance(_make_coordinator("adhoc", client), AdHocCoordinator)
    assert isinstance(_make_coordinator("mpac", client, lock), MPACCoordinator)
    assert isinstance(_make_coordinator("no_a2a", client, lock), MPACAblationCoordinator)
    assert isinstance(_make_coordinator("timestamp_ordered", client, lock), MPACAblationCoordinator)


@pytest.mark.asyncio
async def test_run_agent_empty_evidence():
    result = await run_agent(
        principal_id="Principal-ThreatFox",
        ioc_value="0.0.0.0",
        protocol="adhoc",
    )
    assert isinstance(result, dict)
    assert result["principal_id"] == "Principal-ThreatFox"
    assert result["claim_malware_family"] is None


@pytest.mark.asyncio
async def test_run_agent_with_evidence_and_mock_coordinator():
    fake_record = {
        "ioc_value": "139.59.33.238",
        "malware_family": "Jackskid",
        "confidence": 90,
    }
    fake_mcp_response = MagicMock(records=[fake_record])

    mock_coord = MagicMock()
    mock_coord.submit = AsyncMock(
        return_value=CoordinationResult(
            status="success",
            operations_attempted=1,
            operations_committed=1,
            conflict_detected=False,
            detail="Committed successfully",
        )
    )

    with patch("src.agents.workflow.MCP_TOOLS", {"Principal-ThreatFox": MagicMock(invoke=MagicMock(return_value=fake_mcp_response))}), \
         patch("src.agents.workflow._make_coordinator", return_value=mock_coord), \
         patch("src.agents.workflow.G2CPPeerHub.query_peers", new_callable=AsyncMock, return_value=([], 0.8)):

        state = await run_agent(
            principal_id="Principal-ThreatFox",
            ioc_value="139.59.33.238",
            protocol="mpac",
            neo4j_client=MagicMock(),
        )
        assert state["claim_malware_family"] == "Jackskid"
        assert state["result"].status == "success"
        mock_coord.submit.assert_awaited_once()
```

---

### Verification & Gate for STORY-015

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_agent_workflow.py tests/test_a2a_hub.py -v
```

Must output:
```
9 passed in 0.xxs
```

---

## Section 9 — Sprint 4 Full Integration Gate

Execute the cumulative verification command for all Sprint 4 components:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_investigator.py tests/test_agent_workflow.py tests/test_a2a_hub.py -v
```

Must output:
```
11 passed in 0.xxs
```

Then run the full regression test suite across the workspace:
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ --ignore=tests/test_neo4j_client.py -q
```

Must output:
```
138 passed in 1.xxs
```

---

## Section 10 — Common Failure Modes & Diagnostics Lookup

| Failure Symptom | Probable Cause | Immediate Diagnostic & Fix |
|---|---|---|
| `InvalidUpdateError: Expected messages to be of type BaseMessage` | Node returning malformed dict for `messages` key. | Ensure `planner_node` and `mcp_tool_node` return `{"messages": [AIMessage(...)]}` or `[ToolMessage(...)]`. |
| `KeyError: 'tool_calls'` on AIMessage | Using custom message objects without LangChain `tool_calls` attribute. | Verify `AIMessage(..., tool_calls=[...])` matches standard LangChain schema. |
| `Infinite cyclic graph execution` | `planner_node` never terminates when given unknown tool names. | Ensure `state["tool_call_count"] >= state["max_tool_calls"]` routes to `extractor_node`. |
| `GraphOperation validation error: lock_keys cannot be empty` | Extracted quad missing subject key or entity identifier. | Confirm `lock_keys=[f"{node_label.lower()}:{q.subject_value}"]` is populated. |
| `TypeError: 'NoneType' object is not iterable` in `query_peers` | Calling `G2CPPeerHub.query_peers` with `claim_malware_family=None`. | Validate `family` is non-empty before initiating peer consensus broadcast. |

---

## Section 11 — Sprint 4 Sign-Off Checklist

- [x] `InvestigatorGraphState`, `ExtractedSemanticQuad`, and `ExtractedQuadBatch` models created.
- [x] 5-node cyclic `StateGraph` implemented in `src/agents/investigator.py` (`planner_node`, `mcp_tool_node`, `extractor_node`, `a2a_verify_node`, `mpac_commit_and_reflect`).
- [x] Hop budget limit enforces finite execution and prevents infinite tool-calling loops.
- [x] Closed-loop Agentic-KGR reflection routes rejected claims back to `extractor_node` for iterative refinement.
- [x] `src/agents/workflow.py` updated with backward-compatible `run_agent()` adapter.
- [x] `tests/test_investigator.py` passes 100%.
- [x] `tests/test_agent_workflow.py` and `tests/test_a2a_hub.py` pass 100%.
- [x] Full regression suite passes with 0 failures (138 cumulative unit tests passing).
