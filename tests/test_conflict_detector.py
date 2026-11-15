"""
Tests for Neuro-Symbolic 3-Class Conflict Detector
File: tests/test_conflict_detector.py
Sprint: Sprint 2 (STORY-007)
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.coordination.conflict_detector import ConflictDetector, LLMConflictClassification
from src.schemas.models import GraphOperation


def make_op(
    val: str,
    target: str,
    pred: str = "USES_C2",
    is_func: bool = True,
    date: str = "2026-10-12T00:00:00Z",
    **kw,
):
    defaults = {
        "operation_type": "create_edge",
        "lock_keys": [f"entity:ip:{val}"],
        "node_label": "IP",
        "node_value": val,
        "predicate": pred,
        "target_label": "Malware",
        "target_value": target,
        "is_functional": is_func,
        "valid_from": date,
    }
    defaults.update(kw)
    return GraphOperation(**defaults)


@pytest.mark.asyncio
async def test_classify_pair_rules():
    detector = ConflictDetector()

    # Rule 1: Different IP -> UNRELATED
    op1 = make_op("1.1.1.1", "redline")
    op2 = make_op("2.2.2.2", "redline")
    assert await detector.classify_pair_with_llm(op1, op2) == "UNRELATED"

    # Rule 2: Non-functional -> CO_TENANT_COMPATIBLE
    op_nf1 = make_op("1.1.1.1", "host1", pred="HOSTED_ON", is_func=False)
    op_nf2 = make_op("1.1.1.1", "host2", pred="HOSTED_ON", is_func=False)
    assert await detector.classify_pair_with_llm(op_nf1, op_nf2) == "CO_TENANT_COMPATIBLE"

    # Rule 3: Identical canonical target -> AGREEMENT_OVERLAP
    op_same1 = make_op("1.1.1.1", "redline stealer")
    op_same2 = make_op("1.1.1.1", "redline stealer")
    assert await detector.classify_pair_with_llm(op_same1, op_same2) == "AGREEMENT_OVERLAP"

    # Rule 4: Temporal gap > 30 days -> TEMPORAL_SUPERSESSION
    op_old = make_op("1.1.1.1", "emotet", date="2026-01-01T00:00:00Z")
    op_new = make_op("1.1.1.1", "qbot", date="2026-03-01T00:00:00Z")
    assert await detector.classify_pair_with_llm(op_old, op_new) == "TEMPORAL_SUPERSESSION"


@pytest.mark.asyncio
async def test_classify_pair_llm_judge_exclusive_contradiction():
    detector = ConflictDetector()
    op_a = make_op("1.1.1.1", "redline stealer", date="2026-10-12T00:00:00Z")
    op_b = make_op("1.1.1.1", "cobalt strike", date="2026-10-15T00:00:00Z")

    mock_judgment = LLMConflictClassification(
        conflict_class="EXCLUSIVE_CONTRADICTION",
        explanation="Single IP cannot serve two distinct malware families simultaneously.",
    )
    with patch("src.coordination.conflict_detector.invoke_structured_llm", AsyncMock(return_value=mock_judgment)):
        res = await detector.classify_pair_with_llm(op_a, op_b)
        assert res == "EXCLUSIVE_CONTRADICTION"


@pytest.mark.asyncio
async def test_detect_semantic_with_hydrated_claims():
    detector = ConflictDetector()
    incoming = [make_op("1.1.1.1", "cobalt strike", operation_id="incoming-1", date="2026-10-14T00:00:00Z")]
    existing = [make_op("1.1.1.1", "redline stealer", operation_id="hydrated-1", date="2026-10-12T00:00:00Z")]

    mock_judgment = LLMConflictClassification(
        conflict_class="EXCLUSIVE_CONTRADICTION",
        explanation="Contradictory attribution in same window.",
    )
    with patch("src.coordination.conflict_detector.invoke_structured_llm", AsyncMock(return_value=mock_judgment)):
        conflicts, classes = await detector.detect_semantic(incoming, existing)
        assert len(conflicts) == 1
        assert classes["incoming-1"] == "EXCLUSIVE_CONTRADICTION"
        assert classes["hydrated-1"] == "EXCLUSIVE_CONTRADICTION"

