"""STORY-002B gate tests for the two-tier ontology validator."""

from unittest.mock import patch

import pytest

from src.ontology.validator import (
    TIER1_NODE_TYPES,
    TIER1_RELATIONSHIP_TYPES,
    OntologyDecision,
    OntologyValidator,
)


def make_validator():
    return OntologyValidator(neo4j_client=None)


def test_tier1_node_types_count():
    assert len(TIER1_NODE_TYPES) == 8


def test_tier1_relationship_types_count():
    assert len(TIER1_RELATIONSHIP_TYPES) == 8


def test_exact_match_node_returns_merge():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.5, "IP")):
        result = validator.validate("Malware", "NODE_LABEL", confirmation_count=0)
    assert result.decision == OntologyDecision.MERGE
    assert result.similarity_score == 1.0
    assert result.target_type == "Malware"


def test_exact_match_relationship_returns_merge():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.5, "USES_C2")):
        result = validator.validate("USES_C2", "RELATIONSHIP_TYPE", confirmation_count=0)
    assert result.decision == OntologyDecision.MERGE
    assert result.target_type == "USES_C2"


def test_high_similarity_returns_merge():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.90, "Malware")):
        result = validator.validate("StealeWare", "NODE_LABEL", confirmation_count=0)
    assert result.decision == OntologyDecision.MERGE
    assert result.target_type == "Malware"
    assert result.similarity_score == 0.90


def test_similarity_below_threshold_not_merge():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.70, "Domain")):
        result = validator.validate("TelegramChannel", "NODE_LABEL", confirmation_count=2)
    assert result.decision != OntologyDecision.MERGE


def test_two_confirmations_returns_approve():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.40, "IP")):
        result = validator.validate("CryptoWallet", "NODE_LABEL", confirmation_count=2)
    assert result.decision == OntologyDecision.APPROVE
    assert result.confirmation_count == 2


def test_three_confirmations_also_approve():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.35, "IP")):
        result = validator.validate("CloudDropper", "NODE_LABEL", confirmation_count=3)
    assert result.decision == OntologyDecision.APPROVE


def test_one_confirmation_returns_pending():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.40, "IP")):
        result = validator.validate("TelegramChannel", "NODE_LABEL", confirmation_count=1)
    assert result.decision == OntologyDecision.PENDING
    assert "pending" in result.reason.lower()


def test_zero_confirmations_returns_reject():
    validator = make_validator()
    with patch.object(validator, "_compute_nearest_similarity", return_value=(0.10, "IP")):
        result = validator.validate("HALLUCINATION_XYZ", "NODE_LABEL", confirmation_count=0)
    assert result.decision == OntologyDecision.REJECT


def test_invalid_category_raises():
    validator = make_validator()
    with pytest.raises(ValueError, match="Unknown category"):
        validator.validate("SomeType", "INVALID_CATEGORY", confirmation_count=2)
