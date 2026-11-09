"""
STORY-001 Gate Tests — Two-Tier Hybrid Schema
File: tests/test_neo4j_client.py
Owner: @member2

ALL 12 tests must pass before STORY-003 begins.

Requires: Neo4j Docker container running.
If not running: docker compose up -d && sleep 45
"""

import pytest

from src.db.neo4j_client import TIER1_NODE_TYPES, TIER1_RELATIONSHIP_TYPES, Neo4jClient


@pytest.fixture
async def client():
    """Connected Neo4jClient for each test. Always closed after."""
    c = Neo4jClient()
    await c.connect()
    await c.initialize_schema()
    yield c
    await c.close()


# ── Foundation Tests ──────────────────────────────────────────────────────────


async def test_connection(client):
    """Neo4j must be reachable and return correct query results."""
    result = await client.run("RETURN 1 AS value")
    assert len(result) == 1
    assert result[0]["value"] == 1


async def test_schema_initialization_idempotent(client):
    """initialize_schema() must be safe to call multiple times (IF NOT EXISTS)."""
    await client.initialize_schema()  # Second call — must not raise


async def test_all_constraints_exist(client):
    """All 16 uniqueness constraints must exist."""
    result = await client.run("SHOW CONSTRAINTS YIELD name RETURN name")
    existing = {row["name"] for row in result}
    required = {
        "cst_malware_name",
        "cst_threat_actor_name",
        "cst_campaign_id",
        "cst_ip_value",
        "cst_domain_value",
        "cst_url_value",
        "cst_hash_sha256",
        "cst_hash_md5",
        "cst_hash_sha1",
        "cst_technique_id",
        "cst_claim_id",
        "cst_evidence_id",
        "cst_principal_id",
        "cst_conflict_id",
        "cst_decision_id",
        "cst_ontology_term_id",
    }
    missing = required - existing
    assert not missing, f"MISSING constraints: {missing} — re-run initialize_schema()"


async def test_all_indexes_exist(client):
    """All 4 custom indexes must exist."""
    result = await client.run("SHOW INDEXES YIELD name RETURN name")
    existing = {row["name"] for row in result}
    required = {
        "idx_claim_subject_predicate",
        "idx_evidence_source_record",
        "idx_ontology_term_name",
        "idx_ontology_term_type",
    }
    missing = required - existing
    assert not missing, f"MISSING indexes: {missing} — re-run initialize_schema()"


async def test_uniqueness_constraint_enforced(client):
    """Tier 1 uniqueness constraint must block duplicate Malware nodes."""
    test_name = "__test_unit_malware__"
    await client.run("MATCH (m:Malware {name: $n}) DETACH DELETE m", {"n": test_name})
    await client.run("CREATE (m:Malware {name: $n, node_schema_version: '1.0'})", {"n": test_name})
    with pytest.raises(Exception) as exc:
        await client.run("CREATE (m:Malware {name: $n, node_schema_version: '1.0'})", {"n": test_name})
    err = str(exc.value).lower()
    assert "already exists" in err or "constraint" in err
    await client.run("MATCH (m:Malware {name: $n}) DETACH DELETE m", {"n": test_name})


# ── Tier 1 Vocabulary Tests ───────────────────────────────────────────────────


def test_tier1_node_types_count():
    """Tier 1 must define exactly 8 node types."""
    assert len(TIER1_NODE_TYPES) == 8


def test_tier1_relationship_types_count():
    """Tier 1 must define exactly 8 relationship types."""
    assert len(TIER1_RELATIONSHIP_TYPES) == 8


# ── Dynamic Type Governance Tests ─────────────────────────────────────────────


async def test_tier1_exact_match_returns_merge(client):
    """
    validate_and_register_type() for a Tier 1 type must return MERGE
    without writing any OntologyTerm node to the database.
    """
    result = await client.validate_and_register_type("Malware", "NODE_LABEL", "Agent-ThreatFox")
    assert result["decision"] == "MERGE"
    assert result["term_id"] is None  # No DB write for Tier 1


async def test_new_type_proposal_writes_pending(client):
    """
    A new type proposed by one agent must become PENDING.
    An OntologyTerm node with status=PENDING must exist in Neo4j.
    """
    test_type = "__TestCryptoWallet__"
    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})

    result = await client.validate_and_register_type(test_type, "NODE_LABEL", "Agent-ThreatFox")
    assert result["decision"] == "PENDING"
    assert result["term_id"] is not None

    rows = await client.run(
        "MATCH (o:OntologyTerm {term_name: $n}) RETURN o.status AS s, o.confirmation_count AS c", {"n": test_type}
    )
    assert rows, "OntologyTerm node not written to DB"
    assert rows[0]["s"] == "PENDING"
    assert rows[0]["c"] == 1

    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})


async def test_second_confirmation_auto_approves(client):
    """
    When a second agent confirms the same type,
    status must change from PENDING to APPROVED automatically.
    """
    test_type = "__TestTelegramChannel__"
    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})

    r1 = await client.validate_and_register_type(test_type, "NODE_LABEL", "Agent-ThreatFox")
    assert r1["decision"] == "PENDING"

    r2 = await client.validate_and_register_type(test_type, "NODE_LABEL", "Agent-OTX")
    assert r2["decision"] == "APPROVE"

    rows = await client.run("MATCH (o:OntologyTerm {term_name: $n}) RETURN o.status AS s", {"n": test_type})
    assert rows[0]["s"] == "APPROVED"
    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})


# ── Dynamic Node Write Tests ──────────────────────────────────────────────────


async def test_create_dynamic_node_tier1_succeeds(client):
    """
    create_dynamic_node() with Tier 1 label must write node
    with node_schema_version='1.0'.
    """
    await client.run("MATCH (i:IP {value: '__test_dyn_ip__'}) DETACH DELETE i")
    ok = await client.create_dynamic_node(
        label="IP", key="value", value="__test_dyn_ip__", properties={"confidence": 0.9}, principal="Agent-ThreatFox"
    )
    assert ok is True
    rows = await client.run("MATCH (i:IP {value: '__test_dyn_ip__'}) RETURN i.node_schema_version AS v")
    assert rows and rows[0]["v"] == "1.0"
    await client.run("MATCH (i:IP {value: '__test_dyn_ip__'}) DETACH DELETE i")


async def test_unapproved_label_raises_value_error(client):
    """
    create_dynamic_node() with unapproved label must raise ValueError.
    No node should be written.
    """
    with pytest.raises(ValueError, match="neither Tier 1 nor"):
        await client.create_dynamic_node(
            label="__UnapprovedType__", key="value", value="test", principal="Agent-ThreatFox"
        )


async def test_get_approved_vocabulary_contains_tier1(client):
    """
    get_approved_vocabulary() must always include all 8 Tier 1
    node types and all 8 Tier 1 relationship types.
    """
    vocab = await client.get_approved_vocabulary()
    assert len(vocab["tier1_nodes"]) == 8
    assert len(vocab["tier1_relationships"]) == 8
    assert "Malware" in vocab["all_nodes"]
    assert "IP" in vocab["all_nodes"]
    assert "USES_C2" in vocab["all_relationships"]
