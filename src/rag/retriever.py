"""Evidence-grounded neighborhood retrieval.

Queries use pattern comprehensions so claim, evidence, conflict, and decision
collections stay nested in Neo4j instead of being joined with chained
OPTIONAL MATCH clauses.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

_ENTITY_SPECS: dict[str, tuple[str, str]] = {
    "ip": ("IP", "value"),
    "malware": ("Malware", "name"),
    "domain": ("Domain", "value"),
    "url": ("URL", "value"),
    "filehash": ("FileHash", "sha256"),
    "hash": ("FileHash", "sha256"),
    "threatactor": ("ThreatActor", "name"),
    "actor": ("ThreatActor", "name"),
    "campaign": ("Campaign", "id"),
    "technique": ("AttackTechnique", "id"),
    "attacktechnique": ("AttackTechnique", "id"),
}

_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SHA256 = re.compile(r"\b[a-fA-F0-9]{64}\b")
_SHA1 = re.compile(r"\b[a-fA-F0-9]{40}\b")
_MD5 = re.compile(r"\b[a-fA-F0-9]{32}\b")
_DOMAIN = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")
_QUOTED = re.compile(r"[\"']([^\"']{2,120})[\"']")
_NAMED = re.compile(
    r"\b(?:malware|family|actor|campaign|technique)\s+([A-Za-z0-9][\w .+-]{1,80})",
    re.IGNORECASE,
)
_TITLE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})\b")
_STOP = {
    "What", "Which", "Who", "Where", "When", "How", "The", "This", "That",
    "Active", "Associated", "Infrastructure", "With", "Does", "Use", "Using",
}


class AnalystAnswer(BaseModel):
    """Provenance-grounded answer assembled from a graph neighborhood."""

    answer_text: str
    evidence_subgraph: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    provenance_claims: list[dict[str, Any]] = Field(default_factory=list)
    entity_type: str | None = None
    entity_value: str | None = None


class GraphRAGRetriever:
    """Extract a graph entity from text and load its audited neighborhood."""

    def __init__(self, neo4j_client) -> None:
        self._client = neo4j_client

    def extract_entity(self, query: str) -> tuple[str, str] | None:
        """Return ``(entity_type, entity_value)`` from a natural-language query."""
        text = query.strip()
        if not text:
            return None
        if match := _IPV4.search(text):
            return "ip", match.group(0)
        if match := _URL.search(text):
            return "url", match.group(0).rstrip(".,)")
        if match := _SHA256.search(text):
            return "filehash", match.group(0).lower()
        if match := _SHA1.search(text):
            return "filehash", match.group(0).lower()
        if match := _MD5.search(text):
            return "filehash", match.group(0).lower()
        if match := _DOMAIN.search(text):
            return "domain", match.group(0).lower()
        if match := _QUOTED.search(text):
            return "malware", match.group(1).strip()
        if match := _NAMED.search(text):
            kind = match.group(0).split()[0].lower()
            entity_type = {"actor": "threatactor", "family": "malware"}.get(kind, kind)
            if entity_type == "family":
                entity_type = "malware"
            return entity_type if entity_type in _ENTITY_SPECS else "malware", match.group(1).strip(" .")
        titles = [item for item in _TITLE.findall(text) if item not in _STOP]
        if titles:
            return "malware", titles[-1]
        return None

    async def retrieve(self, query: str, *, max_hops: int = 2) -> AnalystAnswer:
        """Build an analyst answer for one natural-language question."""
        extracted = self.extract_entity(query)
        if extracted is None:
            return AnalystAnswer(
                answer_text="No graph entity could be extracted from the question.",
                entity_type=None,
                entity_value=None,
            )
        entity_type, entity_value = extracted
        return await self.neighborhood(entity_type, entity_value, max_hops=max_hops, question=query)

    async def neighborhood(
        self,
        entity_type: str,
        entity_value: str,
        *,
        max_hops: int = 2,
        question: str | None = None,
    ) -> AnalystAnswer:
        """Load one entity and its direct audited neighborhood."""
        del max_hops  # The production query is a fixed 1-hop pattern comprehension.
        spec = _ENTITY_SPECS.get(entity_type.lower().replace("_", "").replace("-", ""))
        if spec is None:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        label, key = spec
        rows = await self._client.run(_neighborhood_cypher(label, key), {"value": entity_value})
        if not rows:
            return AnalystAnswer(
                answer_text=f"No {label} node matched {entity_value}.",
                entity_type=entity_type,
                entity_value=entity_value,
            )
        row = rows[0]
        claims = list(row.get("provenance_claims") or [])
        neighbors = list(row.get("neighbors") or [])
        conflicts = _conflicts_from_claims(claims)
        subgraph = {
            "nodes": [_node(label, entity_value, row.get("properties") or {})] + [
                {
                    "id": item.get("value"),
                    "label": (item.get("labels") or ["Unknown"])[0],
                }
                for item in neighbors
                if item.get("value")
            ],
            "edges": [
                {
                    "from": entity_value if item.get("direction") == "out" else item.get("value"),
                    "to": item.get("value") if item.get("direction") == "out" else entity_value,
                    "type": item.get("type"),
                }
                for item in neighbors
            ],
        }
        return AnalystAnswer(
            answer_text=_answer_text(question or entity_value, label, entity_value, neighbors, claims, conflicts),
            evidence_subgraph=subgraph,
            conflicts=conflicts,
            provenance_claims=claims,
            entity_type=entity_type,
            entity_value=entity_value,
        )

    async def list_conflicts(self, status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        """Return conflict nodes with the claims and decisions attached to them."""
        if status not in {"all", "active", "resolved"}:
            raise ValueError("status must be all, active, or resolved")
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        rows = await self._client.run(
            "MATCH (x:Conflict) "
            "RETURN x.id AS id, x.status AS status, x.node_label AS node_label, "
            "       x.node_value AS node_value, "
            "       [(c:Claim)-[:INVOLVED_IN]->(x) | {claim_id: c.id, accepted: c.accepted}] AS claims, "
            "       [(c:Claim)-[:INVOLVED_IN]->(x) | "
            "         [(c)-[:HAS_DECISION]->(d:Decision) | "
            "           {decision_id: d.id, verdict: d.verdict, reason: d.reason}]] AS decisions "
            "ORDER BY x.created_at DESC",
        )
        selected: list[dict[str, Any]] = []
        for row in rows:
            decisions = [item for group in (row.get("decisions") or []) for item in group]
            resolved = any(item.get("verdict") in {"accept", "reject"} for item in decisions)
            kind = "resolved" if resolved else "active"
            if status != "all" and kind != status:
                continue
            selected.append({**row, "resolution": kind, "decisions": decisions})
            if len(selected) >= limit:
                break
        return selected

    async def provenance(self, claim_id: str) -> dict[str, Any] | None:
        """Return one claim with its evidence and asserting principal."""
        rows = await self._client.run(
            "MATCH (c:Claim {id: $id}) "
            "RETURN c.id AS claim_id, c.accepted AS accepted, c.node_label AS node_label, "
            "       c.node_value AS node_value, "
            "       [(p:Principal)-[:ASSERTED]->(c) | p.id] AS principals, "
            "       [(c)-[:GROUNDED_IN]->(e:Evidence) | "
            "         {evidence_id: e.id, source: e.source, record_id: e.record_id, "
            "          timestamp: e.timestamp}] AS evidence, "
            "       [(c)-[:HAS_DECISION]->(d:Decision) | "
            "         {decision_id: d.id, verdict: d.verdict, reason: d.reason}] AS decisions",
            {"id": claim_id},
        )
        return rows[0] if rows else None


def _neighborhood_cypher(label: str, key: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
        raise ValueError(f"Unsafe label: {label}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        raise ValueError(f"Unsafe property: {key}")
    identity = f"n.{key} = $value"
    if label == "FileHash":
        identity = "(n.sha256 = $value OR n.md5 = $value OR n.sha1 = $value)"
    return (
        f"MATCH (n:{label}) WHERE {identity} "
        "RETURN labels(n) AS labels, properties(n) AS properties, "
        "[(c:Claim)-[:ASSERTS]->(n) | { "
        "  claim_id: c.id, accepted: c.accepted, operation_id: c.operation_id, "
        "  evidence: [(c)-[:GROUNDED_IN]->(e:Evidence) | { "
        "    evidence_id: e.id, source: e.source, record_id: e.record_id, timestamp: e.timestamp "
        "  }], "
        "  principals: [(p:Principal)-[:ASSERTED]->(c) | p.id], "
        "  conflicts: [(c)-[:INVOLVED_IN]->(x:Conflict) | { "
        "    conflict_id: x.id, status: x.status, node_value: x.node_value "
        "  }], "
        "  decisions: [(c)-[:HAS_DECISION]->(d:Decision) | { "
        "    decision_id: d.id, verdict: d.verdict, reason: d.reason "
        "  }] "
        "}] AS provenance_claims, "
        "[(n)-[r]->(m) WHERE NOT m:Claim AND NOT m:Evidence AND NOT m:Principal "
        "  AND NOT m:Decision AND NOT m:Conflict | { "
        "  type: type(r), direction: 'out', labels: labels(m), "
        "  value: coalesce(m.value, m.name, m.sha256, m.md5, m.sha1, m.id) "
        "}] AS neighbors"
    )


def _node(label: str, value: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {"id": value, "label": label, "properties": properties}


def _conflicts_from_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        for conflict in claim.get("conflicts") or []:
            conflict_id = str(conflict.get("conflict_id"))
            if conflict_id in seen:
                continue
            seen.add(conflict_id)
            found.append({**conflict, "claim_id": claim.get("claim_id")})
    return found


def _answer_text(
    question: str,
    label: str,
    value: str,
    neighbors: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> str:
    sources = sorted({
        evidence.get("source")
        for claim in claims
        for evidence in (claim.get("evidence") or [])
        if evidence.get("source")
    })
    neighbor_text = ", ".join(
        f"{item.get('type')} {item.get('value')}" for item in neighbors if item.get("value")
    ) or "no connected domain entities"
    source_text = ", ".join(sources) if sources else "no linked evidence source"
    dispute = (
        f"{len(conflicts)} recorded conflict(s) remain attached to this entity."
        if conflicts
        else "No conflicts are attached to this entity."
    )
    return (
        f"Question: {question}. {label} {value} connects to {neighbor_text}. "
        f"Evidence sources: {source_text}. {dispute}"
    )
