"""
Text-to-Cypher Generator with Ontology-Aware Few-Shot Prompting
File: src/analyst/cypher_generator.py

Translates natural-language CTI analyst questions into safe, read-only Cypher
queries. Uses the LLM factory (Gemini 2.5 Flash) with structured output and
SHA-256 caching for deterministic, cost-free repeated queries.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from src.agents.llm_factory import invoke_structured_llm
from src.analyst.ast_validator import CypherValidator, CypherValidationError

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Structured LLM Output Schemas
# ──────────────────────────────────────────────────────────────────────────────

class IntentClassification(BaseModel):
    """NLU classification of the analyst's query."""
    mode: Literal["entity_deep_dive", "multi_hop", "dispute_audit", "landscape", "project_architecture"] = Field(
        description="The investigation mode for this query."
    )
    entities_mentioned: list[str] = Field(
        default_factory=list,
        description="IOC values, malware names, IP addresses, domains, or hashes mentioned in the query."
    )
    summary: str = Field(
        description="One-sentence restatement of what the analyst is asking."
    )


class GeneratedCypher(BaseModel):
    """LLM-generated Cypher query with explanation."""
    cypher: str = Field(description="A read-only Cypher query answering the analyst's question.")
    explanation: str = Field(description="Brief explanation of what this query retrieves.")
    highlight_labels: list[str] = Field(
        default_factory=list,
        description="Node labels that should be highlighted in the visualizer."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Ontology Schema Prompt (Injected into every LLM call)
# ──────────────────────────────────────────────────────────────────────────────

_ONTOLOGY_PROMPT = """
You are a Cypher query generator for the ProGRESS CTI Knowledge Graph.

## Neo4j Schema (Two-Tier Architecture)

### Hot Domain Layer (Operational — what analysts query):
Node Labels: IP, Domain, URL, Malware, FileHash, ThreatActor, Campaign, AttackTechnique
Relationship Types: USES_C2, DISTRIBUTED_VIA, HOSTED_ON, ATTRIBUTED_TO, PART_OF, EXPLOITS, TARGETS, MITIGATED_BY, RESOLVES_TO, HAS_SAMPLE

Key Properties:
- IP: value (string), port (int), status (string), confidence (float)
- Domain: value (string), status (string), threat_type (string), first_seen (datetime)
- Malware: name (string), aliases (list), threat_family (string), severity (string)
- FileHash: sha256 (string), md5 (string), sha1 (string), sample_name (string)
- ThreatActor: name (string), aliases (list), motivation (string)

### Cold Provenance Layer (Auditing — forensic trace):
Node Labels: Claim, Evidence, Conflict, Decision, Principal
Relationship Types: ASSERTED, ASSERTS, GROUNDED_IN, SUPPORTED_BY, INVOLVED_IN, HAS_DECISION, RESOLVED_BY, CONTESTED, CORROBORATES, DISPUTES, PROTECTS

Key Properties:
- Claim: id (string), accepted (bool), node_label (string), node_value (string), confidence (float)
- Evidence: id (string), source (string), record_id (string), timestamp (datetime)
- Conflict: id (string), status (string, "RESOLVED"/"ACTIVE"), node_label (string), node_value (string)
- Decision: id (string), verdict (string), reason (string)
- Principal: id (string, e.g. "Principal-ThreatFox")

## Rules:
1. Generate ONLY read-only Cypher. Never use CREATE, MERGE, DELETE, SET, REMOVE, DROP, CALL, or LOAD CSV.
2. Always include a LIMIT clause (max 50).
3. Use parameterized values with $param syntax where possible.
4. For IP lookups, match on the "value" property. For malware, match on "name" (case-insensitive with toLower()).
5. When asked about conflicts or disputes, query the Cold Provenance layer via Claim -> INVOLVED_IN -> Conflict -> RESOLVED_BY -> Decision.
6. When asked about provenance/source, query Principal -> ASSERTED -> Claim -> GROUNDED_IN -> Evidence.
"""

_FEW_SHOT_EXAMPLES = """
## Examples:

Q: "What malware is associated with 139.59.33.238?"
Cypher: MATCH (i:IP {value: '139.59.33.238'})-[r:USES_C2]->(m:Malware) RETURN i.value AS ip, m.name AS malware, m.severity AS severity, type(r) AS relationship, r.posterior_prob AS confidence LIMIT 25

Q: "Why was Cobalt Strike rejected on 185.220.101.5?"
Cypher: MATCH (i:IP {value: '185.220.101.5'})<-[:ASSERTS]-(c:Claim)-[:INVOLVED_IN]->(x:Conflict)-[:RESOLVED_BY]->(d:Decision) OPTIONAL MATCH (c)-[:GROUNDED_IN]->(e:Evidence) RETURN c.id AS claim_id, c.accepted AS accepted, c.confidence AS confidence, x.status AS conflict_status, d.verdict AS verdict, d.reason AS reason, e.source AS source LIMIT 25

Q: "Show all high-confidence botnet C2 servers"
Cypher: MATCH (i:IP)-[r:USES_C2]->(m:Malware) WHERE i.confidence > 80 RETURN i.value AS ip, i.port AS port, i.status AS status, m.name AS malware, m.severity AS severity, i.confidence AS confidence ORDER BY i.confidence DESC LIMIT 25

Q: "Which malware families have the most active C2 infrastructure?"
Cypher: MATCH (i:IP)-[:USES_C2]->(m:Malware) RETURN m.name AS malware_family, m.severity AS severity, count(DISTINCT i) AS c2_count ORDER BY c2_count DESC LIMIT 15

Q: "Trace the provenance for claims about Vidar"
Cypher: MATCH (p:Principal)-[:ASSERTED]->(c:Claim)-[:GROUNDED_IN]->(e:Evidence) WHERE c.node_value = 'Vidar' OR toLower(c.node_label) = 'malware' RETURN p.id AS principal, c.id AS claim_id, c.accepted AS accepted, c.confidence AS confidence, e.source AS source, e.timestamp AS timestamp ORDER BY e.timestamp DESC LIMIT 25

Q: "Find all domains resolving to IPs that host Vidar"
Cypher: MATCH (d:Domain)-[:RESOLVES_TO|HOSTED_ON]->(i:IP)-[:USES_C2]->(m:Malware {name: 'Vidar'}) RETURN d.value AS domain, i.value AS ip, m.name AS malware, m.severity AS severity LIMIT 25

Q: "Summarize the knowledge graph"
Cypher: MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC LIMIT 15

Q: "Show all resolved conflicts in the graph"
Cypher: MATCH (x:Conflict)-[:RESOLVED_BY]->(d:Decision) RETURN x.id AS conflict_id, x.status AS status, d.verdict AS verdict, d.reason AS reason LIMIT 20
"""


class CypherGenerator:
    """Generates safe Cypher from natural language using LLM + Schema Shield."""

    def __init__(self, validator: CypherValidator | None = None):
        self._validator = validator or CypherValidator()

    async def classify_intent(self, query: str) -> IntentClassification:
        """Classify the analyst's query into one of 5 investigation modes."""
        prompt = (
            f"Classify the following question into an investigation mode.\n\n"
            f"Modes:\n"
            f"- entity_deep_dive: Questions about a specific IOC (IP, hash, domain, malware name)\n"
            f"- multi_hop: Questions about relationships or paths between entities\n"
            f"- dispute_audit: Questions about why something was rejected/accepted, conflicts, arbitration\n"
            f"- landscape: Aggregation questions (counts, rankings, 'which malware has the most...')\n"
            f"- project_architecture: Questions about ProGRESS system, architecture, dual-layer design, Bayesian arbitration, protocols (MPAC/Ad-Hoc), metrics (GIR/PTC/CRA), A2A/MCP agents, feeds, capabilities, or what you can do\n\n"
            f"Question: \"{query}\"\n"
        )
        return await invoke_structured_llm(prompt, IntentClassification)

    async def generate(self, query: str, *, max_retries: int = 2) -> GeneratedCypher:
        """
        Generate a validated Cypher query from a natural-language question.

        Retries with error feedback if the first attempt fails AST validation.
        """
        prompt = (
            f"{_ONTOLOGY_PROMPT}\n"
            f"{_FEW_SHOT_EXAMPLES}\n"
            f"Now generate a Cypher query for this question:\n"
            f"Q: \"{query}\"\n"
        )

        last_error: str | None = None
        for attempt in range(max_retries + 1):
            if last_error:
                prompt += (
                    f"\n\nYour previous query was rejected: {last_error}\n"
                    f"Please fix the query and try again.\n"
                )

            result = await invoke_structured_llm(prompt, GeneratedCypher)

            try:
                validated_cypher = self._validator.validate(result.cypher)
                result.cypher = validated_cypher
                logger.info(
                    "Cypher generated (attempt %d): %s", attempt + 1, result.cypher[:120]
                )
                return result
            except CypherValidationError as exc:
                last_error = "; ".join(exc.violations)
                logger.warning(
                    "Cypher validation failed (attempt %d/%d): %s",
                    attempt + 1, max_retries + 1, last_error,
                )

        # All retries exhausted — return a safe fallback
        logger.error("All Cypher generation attempts failed. Returning safe fallback.")
        return GeneratedCypher(
            cypher="MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC LIMIT 15",
            explanation="Fallback: returning database label distribution because query generation failed.",
            highlight_labels=[],
        )

