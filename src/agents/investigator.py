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
