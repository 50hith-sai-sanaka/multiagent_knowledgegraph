"""
Tests for the NL-GraphRAG Analyst Copilot
File: tests/test_analyst_copilot.py

Covers:
  - AST Validator (Schema Shield)
  - Cypher Generator (structured output mocked)
  - Copilot end-to-end (Neo4j + LLM mocked)
  - API endpoint (FastAPI TestClient)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.analyst.ast_validator import CypherValidator, CypherValidationError


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: AST Validator Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCypherValidator:
    """Tests for the Schema Shield AST Validator."""

    def setup_method(self):
        self.validator = CypherValidator()

    def test_valid_read_query_passes(self):
        cypher = "MATCH (i:IP {value: '139.59.33.238'})-[:USES_C2]->(m:Malware) RETURN i, m LIMIT 25"
        result = self.validator.validate(cypher)
        assert "LIMIT" in result
        assert "MATCH" in result

    def test_mutation_create_rejected(self):
        cypher = "CREATE (n:IP {value: '1.2.3.4'})"
        with pytest.raises(CypherValidationError) as exc_info:
            self.validator.validate(cypher)
        assert "CREATE" in exc_info.value.violations[0]

    def test_mutation_merge_rejected(self):
        cypher = "MERGE (n:Malware {name: 'Evil'}) SET n.severity = 'Critical'"
        with pytest.raises(CypherValidationError) as exc_info:
            self.validator.validate(cypher)
        assert len(exc_info.value.violations) >= 1

    def test_mutation_delete_rejected(self):
        cypher = "MATCH (n:IP) DELETE n"
        with pytest.raises(CypherValidationError) as exc_info:
            self.validator.validate(cypher)
        assert "DELETE" in exc_info.value.violations[0]

    def test_mutation_detach_delete_rejected(self):
        cypher = "MATCH (n) DETACH DELETE n"
        with pytest.raises(CypherValidationError) as exc_info:
            self.validator.validate(cypher)
        violations_text = " ".join(exc_info.value.violations)
        assert "DETACH" in violations_text or "DELETE" in violations_text

    def test_mutation_drop_rejected(self):
        cypher = "DROP CONSTRAINT unique_ip"
        with pytest.raises(CypherValidationError) as exc_info:
            self.validator.validate(cypher)
        assert "DROP" in exc_info.value.violations[0]

    def test_mutation_load_csv_rejected(self):
        cypher = "LOAD CSV FROM 'file:///evil.csv' AS row CREATE (n:IP {value: row[0]})"
        with pytest.raises(CypherValidationError) as exc_info:
            self.validator.validate(cypher)
        assert len(exc_info.value.violations) >= 1

    def test_auto_appends_limit_if_missing(self):
        cypher = "MATCH (n:IP) RETURN n"
        result = self.validator.validate(cypher)
        assert "LIMIT 50" in result

    def test_preserves_existing_limit(self):
        cypher = "MATCH (n:IP) RETURN n LIMIT 10"
        result = self.validator.validate(cypher)
        assert "LIMIT 10" in result
        assert result.count("LIMIT") == 1

    def test_strips_trailing_semicolon(self):
        cypher = "MATCH (n:IP) RETURN n LIMIT 5;"
        result = self.validator.validate(cypher)
        assert not result.endswith(";")

    def test_valid_provenance_query_passes(self):
        cypher = (
            "MATCH (p:Principal)-[:ASSERTED]->(c:Claim)-[:GROUNDED_IN]->(e:Evidence) "
            "RETURN p, c, e LIMIT 20"
        )
        result = self.validator.validate(cypher)
        assert "Principal" in result
        assert "Claim" in result

    def test_valid_conflict_query_passes(self):
        cypher = (
            "MATCH (c:Claim)-[:INVOLVED_IN]->(x:Conflict)-[:RESOLVED_BY]->(d:Decision) "
            "RETURN c, x, d LIMIT 25"
        )
        result = self.validator.validate(cypher)
        assert "Conflict" in result

    def test_optional_match_allowed(self):
        cypher = "MATCH (i:IP) OPTIONAL MATCH (i)-[:USES_C2]->(m:Malware) RETURN i, m LIMIT 20"
        result = self.validator.validate(cypher)
        assert "OPTIONAL MATCH" in result

    def test_is_safe_returns_bool(self):
        assert self.validator.is_safe("MATCH (n:IP) RETURN n LIMIT 10") is True
        assert self.validator.is_safe("CREATE (n:IP {value: '1.2.3.4'})") is False

    def test_injection_attempt_blocked(self):
        cypher = "MATCH (n:IP) RETURN n; DROP CONSTRAINT unique_ip"
        with pytest.raises(CypherValidationError):
            self.validator.validate(cypher)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: Copilot Integration Tests (Mocked LLM + Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_copilot_fallback_on_empty_results():
    """When Cypher returns empty results, copilot falls back to GraphRAG retriever."""
    from src.analyst.copilot import AnalystCopilot

    mock_client = AsyncMock()
    mock_client.run = AsyncMock(return_value=[])

    copilot = AnalystCopilot(mock_client)

    with patch("src.analyst.cypher_generator.invoke_structured_llm") as mock_llm:
        from src.analyst.cypher_generator import IntentClassification, GeneratedCypher

        mock_llm.side_effect = [
            IntentClassification(
                mode="entity_deep_dive",
                entities_mentioned=["198.51.100.99"],
                summary="Looking up an IP address."
            ),
            GeneratedCypher(
                cypher="MATCH (i:IP {value: '198.51.100.99'}) RETURN i LIMIT 25",
                explanation="Direct IP lookup.",
                highlight_labels=["IP"],
            ),
        ]

        result = await copilot.chat("What is 198.51.100.99?")
        assert result.fallback_used is True
        assert result.query == "What is 198.51.100.99?"


@pytest.mark.asyncio
async def test_copilot_handles_llm_failure_gracefully():
    """When LLM fails entirely, copilot uses deterministic fallback."""
    from src.analyst.copilot import AnalystCopilot

    mock_client = AsyncMock()
    mock_client.run = AsyncMock(return_value=[])

    copilot = AnalystCopilot(mock_client)

    with patch("src.analyst.cypher_generator.invoke_structured_llm", side_effect=Exception("LLM down")):
        result = await copilot.chat("Tell me about 139.59.33.238")
        assert result.fallback_used is True
        # Should still have a non-empty answer
        assert len(result.answer_markdown) > 0


@pytest.mark.asyncio
async def test_copilot_successful_cypher_execution():
    """When Cypher executes successfully, copilot returns structured answer."""
    from src.analyst.copilot import AnalystCopilot

    mock_client = AsyncMock()
    # First call: Cypher query execution
    mock_client.run = AsyncMock(return_value=[
        {"ip": "139.59.33.238", "malware": "Jackskid", "severity": "High", "confidence": 0.94}
    ])

    copilot = AnalystCopilot(mock_client)

    with patch("src.analyst.cypher_generator.invoke_structured_llm") as mock_llm, \
         patch("src.analyst.copilot.get_chat_llm") as mock_synth:

        from src.analyst.cypher_generator import IntentClassification, GeneratedCypher

        mock_llm.side_effect = [
            IntentClassification(
                mode="entity_deep_dive",
                entities_mentioned=["139.59.33.238"],
                summary="What malware is on this IP?"
            ),
            GeneratedCypher(
                cypher="MATCH (i:IP {value: '139.59.33.238'})-[:USES_C2]->(m:Malware) RETURN i.value AS ip, m.name AS malware, m.severity AS severity LIMIT 25",
                explanation="Direct IP to malware lookup.",
                highlight_labels=["IP", "Malware"],
            ),
        ]

        # Mock synthesis LLM
        synth_response = MagicMock()
        synth_response.content = "IP `139.59.33.238` is associated with **Jackskid** (DDoS Loader) [Source: ThreatFox]."
        mock_synth_llm = MagicMock()
        mock_synth_llm.ainvoke = AsyncMock(return_value=synth_response)
        mock_synth.return_value = mock_synth_llm

        result = await copilot.chat("What malware is on 139.59.33.238?")
        assert result.fallback_used is False
        assert "139.59.33.238" in result.generated_cypher
        assert len(result.raw_results) == 1
        assert result.intent.mode == "entity_deep_dive"


@pytest.mark.asyncio
async def test_copilot_project_architecture_query():
    """Copilot handles system architecture & capability queries with full context."""
    from src.analyst.copilot import AnalystCopilot

    mock_client = AsyncMock()
    mock_client.run = AsyncMock(return_value=[
        {"label": "IP", "count": 214},
        {"label": "Domain", "count": 189},
        {"label": "Claim", "count": 380},
    ])

    copilot = AnalystCopilot(mock_client)

    with patch("src.analyst.cypher_generator.invoke_structured_llm") as mock_llm:
        from src.analyst.cypher_generator import IntentClassification

        mock_llm.return_value = IntentClassification(
            mode="project_architecture",
            entities_mentioned=[],
            summary="Explain the system architecture and capabilities."
        )

        result = await copilot.chat("What can you do and how does Bayesian arbitration work?")
        assert result.fallback_used is False
        assert "MATCH (n)" in result.generated_cypher
        # Should contain comprehensive architecture / capabilities content
        assert "ProGRESS" in result.answer_markdown or "Bayesian" in result.answer_markdown



# ══════════════════════════════════════════════════════════════════════════════
# Phase 3: API Endpoint Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_suggested_prompts_endpoint():
    """GET /api/v1/analyst/suggested-prompts returns prompt categories."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/analyst/suggested-prompts")
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) >= 4
        categories = [s["category"] for s in data["suggestions"]]
        assert "Entity Investigation" in categories
        assert "Dispute Forensics" in categories
