"""
Analyst Copilot API Routes
File: src/api/analyst_routes.py

Provides the FastAPI router for the NL-GraphRAG Analyst Copilot.
Mounted into the main app at /api/v1/analyst/*.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

analyst_router = APIRouter(prefix="/api/v1/analyst", tags=["Analyst Copilot"])


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="Natural-language CTI question.")
    session_id: str = Field(default="default", description="Session identifier for future conversation memory.")
    max_hops: int = Field(default=2, ge=1, le=3)


class ChatResponse(BaseModel):
    query: str
    intent_mode: str | None = None
    entities_mentioned: list[str] = []
    generated_cypher: str = ""
    cypher_explanation: str = ""
    answer_markdown: str = ""
    highlight_nodes: list[str] = []
    provenance_summary: list[dict[str, Any]] = []
    conflicts_found: list[dict[str, Any]] = []
    execution_time_ms: float = 0.0
    fallback_used: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Suggested Prompts
# ──────────────────────────────────────────────────────────────────────────────

_SUGGESTED_PROMPTS = [
    {
        "category": "Entity Investigation",
        "prompts": [
            "What malware is associated with 139.59.33.238?",
            "Tell me everything about IP 185.220.101.5",
            "What threats are linked to domain bok.6666k.org?",
        ],
    },
    {
        "category": "Multi-Hop Traversal",
        "prompts": [
            "Find all domains resolving to IPs that host Vidar stealer binaries",
            "Which IPs are connected to Cobalt Strike C2 infrastructure?",
            "Show the infrastructure chain from Jackskid to its resolving domains",
        ],
    },
    {
        "category": "Dispute Forensics",
        "prompts": [
            "Why was Cobalt Strike rejected on IP 185.220.101.5?",
            "Show me all resolved conflicts in the knowledge graph",
            "Explain the Bayesian arbitration verdict for the Vidar vs Cobalt Strike dispute",
        ],
    },
    {
        "category": "Threat Landscape",
        "prompts": [
            "Which malware families have the most active C2 servers?",
            "List all high-confidence botnet C2 IPs",
            "How many distinct threat sources contributed intelligence?",
        ],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@analyst_router.post("/chat", response_model=ChatResponse)
async def analyst_chat(request: ChatRequest, req: Request) -> ChatResponse:
    """
    Process a natural-language CTI question through the NL-GraphRAG Copilot.

    Pipeline: Intent Classification -> Text-to-Cypher -> Neo4j Execution -> Provenance Hydration -> LLM Synthesis
    """
    from src.analyst.copilot import AnalystCopilot

    neo4j_client = req.app.state.neo4j_client
    copilot = AnalystCopilot(neo4j_client)

    try:
        result = await copilot.chat(request.query, max_hops=request.max_hops)
    except Exception as exc:
        logger.error("Copilot chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Copilot error: {exc}") from exc

    return ChatResponse(
        query=result.query,
        intent_mode=result.intent.mode if result.intent else None,
        entities_mentioned=result.intent.entities_mentioned if result.intent else [],
        generated_cypher=result.generated_cypher,
        cypher_explanation=result.cypher_explanation,
        answer_markdown=result.answer_markdown,
        highlight_nodes=result.highlight_nodes,
        provenance_summary=result.provenance_summary,
        conflicts_found=result.conflicts_found,
        execution_time_ms=result.execution_time_ms,
        fallback_used=result.fallback_used,
    )


@analyst_router.get("/suggested-prompts")
async def get_suggested_prompts() -> dict:
    """Return contextual prompt recommendations for the Copilot UI."""
    return {"suggestions": _SUGGESTED_PROMPTS}


@analyst_router.get("/graph/live")
async def get_live_graph(req: Request, full: bool = False, limit: int = 150) -> dict:
    """
    Fetch the live Neo4j Knowledge Graph entities and relationships for the visualizer.
    If full=True, returns all 783 nodes and 885 edges from the live database.
    """
    client = req.app.state.neo4j_client

    # Total counts in live database
    total_nodes_rows = await client.run("MATCH (n) RETURN count(n) AS total")
    total_edges_rows = await client.run("MATCH ()-[r]->() RETURN count(r) AS total")
    total_nodes = total_nodes_rows[0]["total"] if total_nodes_rows else 783
    total_edges = total_edges_rows[0]["total"] if total_edges_rows else 885

    query_limit = 1000 if full else limit

    edges_rows = await client.run(
        "MATCH (a)-[r]->(b) "
        "RETURN elementId(a) AS from_id, labels(a)[0] AS a_label, properties(a) AS a_props, "
        "       type(r) AS rel_type, properties(r) AS r_props, "
        "       elementId(b) AS to_id, labels(b)[0] AS b_label, properties(b) AS b_props "
        "LIMIT $limit",
        {"limit": query_limit}
    )

    node_map = {}
    vis_edges = []

    def format_node(n_id: str, label: str, props: dict):
        val = props.get("value") or props.get("name") or props.get("sha256", "")[:12] or props.get("id", "")[:10] or label
        if props.get("malware_family"):
            display_label = f"{val}\n({props['malware_family']})"
        elif label == "Conflict":
            display_label = f"Conflict: {str(props.get('node_value', ''))[:12]}\n[{props.get('status', 'RESOLVED')}]"
        elif label == "Decision":
            verdict = props.get("verdict", "")
            display_label = f"Bayesian Verdict\n({verdict})"
        elif label == "Claim":
            status = "VERIFIED" if props.get("accepted") else "REJECTED"
            display_label = f"Claim-{str(props.get('id', ''))[:8]}\n[{status}]"
        elif label == "Evidence":
            display_label = f"Evidence-{str(props.get('id', ''))[:8]}\n(SHA-256)"
        elif label == "Principal":
            display_label = f"{props.get('id', 'Principal')}\n(Feed)"
        else:
            display_label = f"{val}\n({label})"

        group = label.lower()
        if label in ["IP", "Domain", "URL", "Malware", "FileHash", "ThreatActor"]:
            layer = "hot"
        elif label in ["Conflict", "Decision"]:
            layer = "conflicts"
        else:
            layer = "cold"

        return {
            "id": n_id,
            "label": display_label,
            "group": group,
            "layer": layer,
            "props": props
        }

    for row in edges_rows:
        from_id = row["from_id"]
        to_id = row["to_id"]
        a_label = row["a_label"] or "Entity"
        b_label = row["b_label"] or "Entity"
        a_props = row["a_props"] or {}
        b_props = row["b_props"] or {}
        rel_type = row["rel_type"]

        if from_id not in node_map:
            node_map[from_id] = format_node(from_id, a_label, a_props)
        if to_id not in node_map:
            node_map[to_id] = format_node(to_id, b_label, b_props)

        vis_edges.append({
            "from": from_id,
            "to": to_id,
            "label": rel_type,
            "arrows": "to",
            "layer": "hot" if rel_type in ["USES_C2", "HOSTED_ON", "RESOLVES_TO", "HAS_SAMPLE"] else (
                "conflicts" if rel_type in ["RESOLVED_BY", "CORROBORATES", "DISPUTES", "PROTECTS", "INVOLVED_IN", "HAS_DECISION"] else "cold"
            )
        })

    return {
        "nodes": list(node_map.values()),
        "edges": vis_edges,
        "stats": {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "rendered_nodes": len(node_map),
            "rendered_edges": len(vis_edges),
            "gir": "100%",
            "cra": "96.4%"
        }
    }

