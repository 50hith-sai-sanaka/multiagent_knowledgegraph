"""
Neo4j Async Client — Two-Tier Hybrid Schema
File: src/db/neo4j_client.py
Story: STORY-001 (Tasks INF-003 + INF-004)

TWO-TIER ARCHITECTURE:
  Tier 1 (Static): 8 fixed node types + 8 fixed relationship types.
                   Hardcoded as frozensets. Never change.
                   All Tier 1 nodes stamp node_schema_version='1.0'.

  Tier 2 (Dynamic): Any type an agent proposes goes through
                    validate_and_register_type(). Requires 2 distinct
                    agent confirmations before status becomes APPROVED.
                    Approved types stamp node_schema_version='2.0'.

AGENT ACCESS RULES:
  - Agents NEVER call run() with arbitrary Cypher.
  - Agents call validate_and_register_type() to propose new types.
  - Agents call create_dynamic_node() / create_dynamic_relationship()
    for all writes (both Tier 1 and Tier 2 approved types).
  - All full coordination (locking, conflict detection, provenance)
    is handled by the MPAC coordinator (STORY-006).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

logger = logging.getLogger(__name__)


# ── Tier 1 Static Vocabulary ──────────────────────────────────────────────────
# Frozen constants. Agents cannot modify these.
# OntologyValidator (STORY-002B) adds semantic similarity on top.
# Neo4jClient enforces governance at the database layer independently.

TIER1_NODE_TYPES: frozenset = frozenset(
    {
        "Malware",
        "ThreatActor",
        "Campaign",
        "IP",
        "Domain",
        "URL",
        "FileHash",
        "AttackTechnique",
    }
)

TIER1_RELATIONSHIP_TYPES: frozenset = frozenset(
    {
        "USES_C2",
        "DISTRIBUTED_VIA",
        "HOSTED_ON",
        "ATTRIBUTED_TO",
        "PART_OF",
        "EXPLOITS",
        "TARGETS",
        "MITIGATED_BY",
    }
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_safe_identifier(value: str, kind: str) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe {kind} identifier: {value!r}")


class Neo4jClient:
    """
    Async Neo4j client with Two-Tier Hybrid Schema support.

    Credentials read from .env:
      NEO4J_URI      bolt://localhost:7687
      NEO4J_USER     neo4j
      NEO4J_PASSWORD required; no insecure default is provided
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        import os

        from dotenv import load_dotenv

        load_dotenv()
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        if not self.password:
            raise ValueError("NEO4J_PASSWORD must be configured in the environment or passed explicitly")
        self._driver: AsyncDriver | None = None

    # ── Connection Lifecycle ──────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open connection pool. Call before any other method."""
        self._driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
        await self._driver.verify_connectivity()
        logger.info("Neo4j connection pool opened at %s", self.uri)

    async def close(self) -> None:
        """Gracefully close connection pool. Always call on shutdown."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection pool closed.")

    def session(self, **kwargs):
        """Return a driver session for atomic coordinator transactions."""
        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected. Call await client.connect() first.")
        return self._driver.session(**kwargs)

    # ── Raw Query (INTERNAL / INFRASTRUCTURE USE ONLY) ────────────────────────

    async def run(
        self,
        cypher: str,
        parameters: dict | None = None,
    ) -> list:
        """
        Execute any Cypher query. Returns list of dicts.

        INTERNAL INFRASTRUCTURE USE ONLY.
        Agents must never call run() with arbitrary Cypher.
        Use create_dynamic_node() or create_dynamic_relationship() instead.
        """
        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected. Call await client.connect() first.")
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters or {})
            records = await result.data()
        return records

    # ── Schema Initialization ─────────────────────────────────────────────────

    async def initialize_schema(self) -> None:
        """
        Apply all constraints and indexes. IDEMPOTENT (IF NOT EXISTS).

        Sets up:
          Tier 1: 14 uniqueness constraints for all Tier 1 + provenance types
          Tier 2: OntologyTerm constraint + 4 indexes for fast governance lookup

        Safe to call multiple times — never raises on duplicate.
        """
        constraints = [
            # ── Tier 1 Core Entity Constraints ────────────────────────────────
            ("CREATE CONSTRAINT cst_malware_name IF NOT EXISTS FOR (m:Malware) REQUIRE m.name IS UNIQUE"),
            ("CREATE CONSTRAINT cst_threat_actor_name IF NOT EXISTS FOR (a:ThreatActor) REQUIRE a.name IS UNIQUE"),
            ("CREATE CONSTRAINT cst_campaign_id IF NOT EXISTS FOR (c:Campaign) REQUIRE c.id IS UNIQUE"),
            ("CREATE CONSTRAINT cst_ip_value IF NOT EXISTS FOR (i:IP) REQUIRE i.value IS UNIQUE"),
            ("CREATE CONSTRAINT cst_domain_value IF NOT EXISTS FOR (d:Domain) REQUIRE d.value IS UNIQUE"),
            ("CREATE CONSTRAINT cst_url_value IF NOT EXISTS FOR (u:URL) REQUIRE u.value IS UNIQUE"),
            ("CREATE CONSTRAINT cst_hash_sha256 IF NOT EXISTS FOR (h:FileHash) REQUIRE h.sha256 IS UNIQUE"),
            ("CREATE CONSTRAINT cst_hash_md5 IF NOT EXISTS FOR (h:FileHash) REQUIRE h.md5 IS UNIQUE"),
            ("CREATE CONSTRAINT cst_hash_sha1 IF NOT EXISTS FOR (h:FileHash) REQUIRE h.sha1 IS UNIQUE"),
            ("CREATE CONSTRAINT cst_technique_id IF NOT EXISTS FOR (t:AttackTechnique) REQUIRE t.id IS UNIQUE"),
            # ── Provenance Meta-Layer ─────────────────────────────────────────
            ("CREATE CONSTRAINT cst_claim_id IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE"),
            ("CREATE CONSTRAINT cst_evidence_id IF NOT EXISTS FOR (e:Evidence) REQUIRE e.id IS UNIQUE"),
            ("CREATE CONSTRAINT cst_principal_id IF NOT EXISTS FOR (p:Principal) REQUIRE p.id IS UNIQUE"),
            ("CREATE CONSTRAINT cst_conflict_id IF NOT EXISTS FOR (cf:Conflict) REQUIRE cf.id IS UNIQUE"),
            ("CREATE CONSTRAINT cst_decision_id IF NOT EXISTS FOR (dc:Decision) REQUIRE dc.id IS UNIQUE"),
            # ── Tier 2 Dynamic Extension Registry ────────────────────────────
            ("CREATE CONSTRAINT cst_ontology_term_id IF NOT EXISTS FOR (o:OntologyTerm) REQUIRE o.term_id IS UNIQUE"),
        ]

        indexes = [
            ("CREATE INDEX idx_claim_subject_predicate IF NOT EXISTS FOR (c:Claim) ON (c.subject, c.predicate)"),
            ("CREATE INDEX idx_evidence_source_record IF NOT EXISTS FOR (e:Evidence) ON (e.source, e.record_id)"),
            # OntologyTerm indexes for fast dynamic type governance
            ("CREATE INDEX idx_ontology_term_name IF NOT EXISTS FOR (o:OntologyTerm) ON (o.term_name, o.status)"),
            ("CREATE INDEX idx_ontology_term_type IF NOT EXISTS FOR (o:OntologyTerm) ON (o.term_type)"),
        ]

        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected. Call await client.connect() first.")

        async with self._driver.session() as session:
            for stmt in constraints:
                await session.run(stmt)
                logger.debug("Applied: %s", stmt[:70])
            for stmt in indexes:
                await session.run(stmt)
                logger.debug("Applied: %s", stmt[:70])

        logger.info(
            "Schema initialized: %d constraints, %d indexes.",
            len(constraints),
            len(indexes),
        )

    # ── Tier 2 Dynamic Type Governance ────────────────────────────────────────

    async def validate_and_register_type(
        self,
        term_name: str,
        term_type: str,
        proposing_agent: str,
    ) -> dict[str, Any]:
        """
        Database-level type governance for agent-proposed types.

        Decision flow:
          1. Exact Tier 1 match              → MERGE  (no DB write)
          2. Already APPROVED in OntologyTerm → APPROVED
          3. Already PENDING → increment count:
             a. count reaches 2 → auto-approve → APPROVE
             b. count < 2       → PENDING
          4. Brand new term → write PENDING

        Args:
          term_name:       e.g. "CryptoWallet", "FUNDS_VIA"
          term_type:       "NODE_LABEL" or "RELATIONSHIP_TYPE"
          proposing_agent: e.g. "Agent-ThreatFox"

        Returns:
          Dict: {decision, term_id, target_type, reason}
        """
        if term_type not in ("NODE_LABEL", "RELATIONSHIP_TYPE"):
            raise ValueError(f"term_type must be 'NODE_LABEL' or 'RELATIONSHIP_TYPE', got {term_type!r}")

        tier1 = TIER1_NODE_TYPES if term_type == "NODE_LABEL" else TIER1_RELATIONSHIP_TYPES

        # Step 1: Exact Tier 1 Match — no DB write needed
        if term_name in tier1:
            return {
                "decision": "MERGE",
                "term_id": None,
                "target_type": term_name,
                "reason": f"Exact Tier 1 match: use existing type '{term_name}'",
            }

        # Step 2/3: Check existing OntologyTerm
        rows = await self.run(
            "MATCH (o:OntologyTerm {term_name: $n, term_type: $t}) "
            "RETURN o.term_id AS id, o.status AS status, "
            "       o.confirmation_count AS cnt",
            {"n": term_name, "t": term_type},
        )

        if rows:
            row = rows[0]
            existing_id = row["id"]
            status = row["status"]
            count = int(row["cnt"] or 1)

            if status == "APPROVED":
                return {
                    "decision": "APPROVED",
                    "term_id": existing_id,
                    "target_type": term_name,
                    "reason": f"Already an approved Tier 2 type: '{term_name}'",
                }

            new_count = count + 1
            if new_count >= 2:
                # Auto-approve on 2nd confirmation
                await self.run(
                    "MATCH (o:OntologyTerm {term_id: $id}) "
                    "SET o.status = 'APPROVED', "
                    "    o.confirmation_count = $c, "
                    "    o.approved_at = timestamp()",
                    {"id": existing_id, "c": new_count},
                )
                logger.info("OntologyTerm APPROVED: %s (%d confirmations)", term_name, new_count)
                return {
                    "decision": "APPROVE",
                    "term_id": existing_id,
                    "target_type": term_name,
                    "reason": f"'{term_name}' approved after {new_count} agent confirmations",
                }
            else:
                await self.run(
                    "MATCH (o:OntologyTerm {term_id: $id}) SET o.confirmation_count = $c",
                    {"id": existing_id, "c": new_count},
                )
                return {
                    "decision": "PENDING",
                    "term_id": existing_id,
                    "target_type": term_name,
                    "reason": f"'{term_name}' is PENDING ({new_count}/2 confirmations)",
                }

        # Step 4: Brand New Term — write PENDING
        term_id = str(uuid.uuid4())
        await self.run(
            "MERGE (o:OntologyTerm {term_id: $term_id}) "
            "SET o.term_name          = $name, "
            "    o.term_type          = $type, "
            "    o.status             = 'PENDING', "
            "    o.confirmation_count = 1, "
            "    o.proposed_by        = $agent, "
            "    o.proposed_at        = timestamp(), "
            "    o.schema_version_assigned = 'pending'",
            {"term_id": term_id, "name": term_name, "type": term_type, "agent": proposing_agent},
        )
        logger.info("OntologyTerm PENDING: %s (proposed by %s)", term_name, proposing_agent)
        return {
            "decision": "PENDING",
            "term_id": term_id,
            "target_type": term_name,
            "reason": f"New type '{term_name}' registered as PENDING (1/2 confirmations needed)",
        }

    # ── Dynamic Node Writer ───────────────────────────────────────────────────

    async def create_dynamic_node(
        self,
        label: str,
        key: str,
        value: str,
        properties: dict[str, Any] | None = None,
        principal: str = "unknown",
    ) -> bool:
        """
        MERGE a node with any validated label (Tier 1 OR approved Tier 2).

        Raises ValueError for labels that are neither Tier 1 nor APPROVED.

        node_schema_version:
          '1.0' → Tier 1 type
          '2.0' → approved Tier 2 type
        """
        _require_safe_identifier(label, "node label")
        _require_safe_identifier(key, "node key")
        is_tier1 = label in TIER1_NODE_TYPES

        if not is_tier1:
            approved = await self.run(
                "MATCH (o:OntologyTerm {term_name: $n, term_type: 'NODE_LABEL', "
                "       status: 'APPROVED'}) RETURN o.term_id AS id",
                {"n": label},
            )
            if not approved:
                raise ValueError(
                    f"Label '{label}' is neither Tier 1 nor an approved Tier 2 type. "
                    f"Call validate_and_register_type('{label}', 'NODE_LABEL', agent) "
                    "and get a second agent to confirm."
                )

        props = dict(properties or {})
        props[key] = value
        props["node_schema_version"] = "1.0" if is_tier1 else "2.0"
        props["created_by"] = principal

        await self.run(
            f"MERGE (n:{label} {{{key}: $val}}) SET n += $props SET n.created_at = timestamp()",
            {"val": value, "props": props},
        )
        logger.info("Node MERGE: (%s {%s: %r}) by %s", label, key, value, principal)
        return True

    # ── Dynamic Relationship Writer ───────────────────────────────────────────

    async def create_dynamic_relationship(
        self,
        from_label: str,
        from_key: str,
        from_val: str,
        rel_type: str,
        to_label: str,
        to_key: str,
        to_val: str,
        principal: str = "unknown",
    ) -> bool:
        """
        MERGE a relationship with any validated type (Tier 1 OR approved Tier 2).

        Raises ValueError for types that are neither Tier 1 nor APPROVED.

        relationship_schema_version:
          '1.0' → Tier 1 type
          '2.0' → approved Tier 2 type
        """
        for identifier, kind in ((from_label, "source label"), (to_label, "target label"),
                                 (from_key, "source key"), (to_key, "target key"),
                                 (rel_type, "relationship type")):
            _require_safe_identifier(identifier, kind)
        is_tier1 = rel_type in TIER1_RELATIONSHIP_TYPES

        if not is_tier1:
            approved = await self.run(
                "MATCH (o:OntologyTerm {term_name: $n, term_type: 'RELATIONSHIP_TYPE', "
                "       status: 'APPROVED'}) RETURN o.term_id AS id",
                {"n": rel_type},
            )
            if not approved:
                raise ValueError(
                    f"Relationship type '{rel_type}' is neither Tier 1 nor approved Tier 2. "
                    "Call validate_and_register_type() and get 2 agent confirmations."
                )

        schema_ver = "1.0" if is_tier1 else "2.0"
        cypher = (
            f"MATCH (a:{from_label}), (b:{to_label}) "
            f"WHERE (a.{from_key} = $fv OR a.value = $fv OR a.name = $fv) "
            f"  AND (b.{to_key} = $tv OR b.value = $tv OR b.name = $tv) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r.relationship_schema_version = $sv, "
            f"    r.created_by = $agent, r.created_at = timestamp()"
        )
        await self.run(cypher, {"fv": from_val, "tv": to_val, "sv": schema_ver, "agent": principal})
        logger.info("Rel MERGE: [%s]-[%s]->[%s] by %s", from_val, rel_type, to_val, principal)
        return True

    # ── Vocabulary Query ──────────────────────────────────────────────────────

    async def get_approved_vocabulary(self) -> dict[str, list[str]]:
        """
        Returns the complete current vocabulary available for graph writes.
        Agents call this to discover all node labels and relationship types
        they are allowed to use without a governance error.

        Returns:
          {
            "tier1_nodes":         [...8 types...],
            "tier1_relationships": [...8 types...],
            "tier2_nodes":         [...approved extensions...],
            "tier2_relationships": [...approved extensions...],
            "all_nodes":           [...tier1 + tier2 combined...],
            "all_relationships":   [...tier1 + tier2 combined...],
          }
        """
        rows = await self.run(
            "MATCH (o:OntologyTerm {status: 'APPROVED'}) RETURN o.term_name AS name, o.term_type AS type"
        )
        tier2_nodes = {r["name"] for r in rows if r["type"] == "NODE_LABEL"}
        tier2_rels = {r["name"] for r in rows if r["type"] == "RELATIONSHIP_TYPE"}

        return {
            "tier1_nodes": sorted(TIER1_NODE_TYPES),
            "tier1_relationships": sorted(TIER1_RELATIONSHIP_TYPES),
            "tier2_nodes": sorted(tier2_nodes),
            "tier2_relationships": sorted(tier2_rels),
            "all_nodes": sorted(TIER1_NODE_TYPES | tier2_nodes),
            "all_relationships": sorted(TIER1_RELATIONSHIP_TYPES | tier2_rels),
        }
