# src/agents/workflow.py
"""LangGraph Agent Workflow — Stories 010 & 011.

Implements the 6-node state machine:
  receive → fetch_evidence → extract_claim
         → enrich_with_llm                 (Story 011 — LLM enrichment)
         → a2a_peer_check → submit_to_coordinator

Each node is a plain async function that receives the full AgentState and
returns a *partial* dict containing only the fields it updates. LangGraph
merges updates automatically.

Story 011 (LLM Enrichment)
---------------------------
The ``enrich_with_llm`` node calls an LLM (Gemini, OpenAI, Groq, or Together AI)
to generate a natural-language summary of the IOC claim and propose additional
Neo4j node properties. The node is configured via environment variables:

    LLM_API_KEY   – Required. Free-tier keys work fine.
    LLM_PROVIDER  – Optional. "gemini" (default), "openai", "groq", "together".
    LLM_MODEL     – Optional. Override the default model.

If LLM_API_KEY is absent or the LLM call fails, the node logs a warning and
returns empty enrichment so the pipeline continues unchanged.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

# LLMEnrichmentTool imported at module level so tests can patch it at
# ``src.agents.workflow.LLMEnrichmentTool``.
from src.llm.llm_tool import LLMEnrichmentTool

from langgraph.graph import END, StateGraph

from src.agents.a2a import G2CPPeerHub
from src.agents.state import AgentState
from src.coordination.adhoc import AdHocCoordinator
from src.coordination.mpac import MPACCoordinator
from src.coordination.ablation import MPACAblationCoordinator
from src.mcp.tools import MCP_TOOLS
from src.schemas.models import CoordinationResult, GraphOperation

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

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
    if protocol == "adhoc":
        return AdHocCoordinator(neo4j_client)
    if protocol == "mpac":
        return MPACCoordinator(neo4j_client, lock_manager=lock_manager)
    ablations = {
        "ablation_no_a2a": "no_a2a",
        "ablation_no_locks": "no_semantic_locks",
        "ablation_timestamp": "timestamp_ordered",
    }
    if protocol in ablations:
        return MPACAblationCoordinator(neo4j_client, ablations[protocol], lock_manager=lock_manager)
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

    # Extract malware_family from the first record if available
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
    """Build a GraphOperation (the 'claim') from the fetched evidence.

    If evidence is empty, the claim is set to None — the workflow still
    runs but the coordinator won't write anything to Neo4j.
    """
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

    # Collect extra properties from the first evidence record
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
    """Call the LLM to enrich the claim with a summary and extra properties.

    Gracefully skips enrichment if:
    - A previous node set ``error``.
    - ``claim`` is None (no evidence was found).
    - ``LLM_API_KEY`` is not set in the environment.
    - The LLM API call fails for any reason.

    When enrichment succeeds:
    - ``llm_summary`` is stored on the state.
    - ``llm_extra_props`` from the LLM are merged into the existing
      GraphOperation's ``properties``, producing an updated ``claim``.
    - If the LLM suggests a ``new_label``, the ``node_label`` and the
      ``claim.node_label`` are updated accordingly.
    """
    if state.get("error"):
        return {}

    claim: GraphOperation | None = state.get("claim")
    if claim is None:
        return {}

    # Skip silently when no API key is configured
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

    # Merge extra properties into the GraphOperation
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
    # The model may suggest a label, but it cannot authorize schema changes.
    # Keep the evidence-derived label until deterministic ontology governance
    # approves a change in a separate, auditable step.
    new_label: str | None = None

    if extra_props or new_label:
        merged_props = {**dict(claim.properties), **extra_props}
        final_label = new_label if new_label else claim.node_label
        # Rebuild a new (frozen) GraphOperation with updated fields
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
    """Build and compile the LangGraph state machine.

    Node order:
        receive → fetch_evidence → extract_claim
               → enrich_with_llm
               → a2a_peer_check → submit_to_coordinator → END
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("receive",               receive)
    graph.add_node("fetch_evidence",        fetch_evidence)
    graph.add_node("extract_claim",         extract_claim)
    graph.add_node("enrich_with_llm",       enrich_with_llm)   # Story 011
    graph.add_node("a2a_peer_check",        a2a_peer_check)
    graph.add_node("submit_to_coordinator", submit_to_coordinator)

    # Wire edges
    graph.set_entry_point("receive")
    graph.add_edge("receive",               "fetch_evidence")
    graph.add_edge("fetch_evidence",        "extract_claim")
    graph.add_edge("extract_claim",         "enrich_with_llm")   # Story 011
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
    """Run the full agent workflow for a single IOC.

    Parameters
    ----------
    principal_id:
        One of "Principal-ThreatFox", "Principal-URLhaus",
        "Principal-MalwareBazaar", "Principal-OTX".
    ioc_value:
        The IOC string to process.
    protocol:
        Coordination protocol: "mpac" (default) or "adhoc".
    neo4j_client:
        Connected Neo4j client. Required for writing to the graph.
    graph:
        Pre-compiled LangGraph. If None, ``build_agent_graph()`` is called.

    Returns
    -------
    The final AgentState dict after all nodes have run.
    """
    if graph is None:
        graph = build_agent_graph()

    initial_state: AgentState = {
        "principal_id": principal_id,
        "ioc_value": ioc_value,
        "protocol": protocol,
        "neo4j_client": neo4j_client,
        "lock_manager": lock_manager,
        # These will be populated by the nodes:
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
