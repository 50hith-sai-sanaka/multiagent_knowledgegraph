# tests/test_models.py
"""
Test suite for STORY-002 data contracts and utilities.
Run with:
    PYTHONPATH=. ./venv/bin/python3 -m pytest tests/test_models.py -v
"""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from src.schemas import (
    A2AQuery,
    ArbitrationDecision,
    Claim,
    CoordinationResult,
    GraphOperation,
)
from src.utils import normalize_timestamp


# ----------------------------------------------------------------------
# Claim – ID generation
# ----------------------------------------------------------------------
def test_claim_generate_id_is_deterministic_and_collision_proof():
    ev = "evidence-42"
    ts1 = datetime(2024, 7, 3, 12, 0, 0, tzinfo=timezone.utc)  # noqa: UP017
    ts2 = ts1 + timedelta(seconds=1)

    # Direct classmethod usage
    id1 = Claim.generate_id(ev, ts1)
    id2 = Claim.generate_id(ev, ts2)

    assert id1 != id2, "Different timestamps must yield different hashes"
    assert len(id1) == 64 and all(c in "0123456789abcdef" for c in id1)

    # Verify deterministic content
    expected = hashlib.sha256(f"{ev}{ts1.isoformat()}".encode()).hexdigest()
    assert id1 == expected

    # Model auto‑populates ``id`` when omitted
    claim = Claim(evidence_id=ev, timestamp=ts1)
    assert claim.id == id1


# ----------------------------------------------------------------------
# GraphOperation – lock key handling
# ----------------------------------------------------------------------
def test_graphoperation_lock_sorting_and_empty_validation():
    op = GraphOperation(operation="create", lock_keys=["z_key", "a_key", "m_key"])
    assert op.lock_keys == ["a_key", "m_key", "z_key"]

    with pytest.raises(ValueError, match="must contain at least one key"):
        GraphOperation(operation="delete", lock_keys=[])


# ----------------------------------------------------------------------
# Simple model instantiation (no extra logic)
# ----------------------------------------------------------------------
def test_arbitration_decision_creation():
    dec = ArbitrationDecision(decision="accept", reason="looks good")
    assert dec.decision == "accept"
    assert dec.reason == "looks good"


def test_coordination_result_creation():
    res = CoordinationResult(status="partial", detail="some nodes failed")
    assert res.status == "partial"
    assert res.detail == "some nodes failed"


def test_a2aquery_creation():
    q = A2AQuery(query_id="q123", payload={"foo": "bar"})
    assert q.query_id == "q123"
    assert q.payload["foo"] == "bar"


# ----------------------------------------------------------------------
# Timestamp normaliser – covering all four feed formats
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, iso_expected, epoch_expected",
    [
        ("2024-07-03 14:52:31", "2024-07-03T14:52:31Z", 1719981151),
        ("2024-07-03T14:52:31Z", "2024-07-03T14:52:31Z", 1719981151),
        ("2024-07-03T14:52:31+00:00", "2024-07-03T14:52:31Z", 1719981151),
        ("2024-07-03 14:52:31+00:00", "2024-07-03T14:52:31Z", 1719981151),
        ("2024-07-03 14:52:31 UTC", "2024-07-03T14:52:31Z", 1719981151),
        ("2024-07-03T14:52:31.183000", "2024-07-03T14:52:31Z", 1719981151),
    ],
)
def test_normalize_timestamp_success(raw, iso_expected, epoch_expected):
    iso, epoch = normalize_timestamp(raw)
    assert iso == iso_expected
    epoch_expected = int(datetime(2024, 7, 3, 14, 52, 31, tzinfo=timezone.utc).timestamp())  # noqa: UP017
    assert epoch == epoch_expected


def test_normalize_timestamp_invalid():
    with pytest.raises(ValueError, match="Unsupported timestamp format"):
        normalize_timestamp("not-a-timestamp")
