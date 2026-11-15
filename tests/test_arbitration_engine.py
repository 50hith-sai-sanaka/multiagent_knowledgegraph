"""
Tests for Bayesian Log-Odds Arbitration Engine
File: tests/test_arbitration_engine.py
Sprint: Sprint 2 (STORY-008)
"""

from src.coordination.arbitration_engine import ArbitrationEngine
from src.schemas.models import GraphOperation, PeerAttestation


def make_op(op_id: str, principal: str, target: str, conf: int = 90, sig: str = "", **kw):
    defaults = {
        "operation_type": "create_edge",
        "operation_id": op_id,
        "lock_keys": ["entity:ip:185.220.101.4"],
        "node_label": "IP",
        "node_value": "185.220.101.4",
        "predicate": "USES_C2",
        "target_label": "Malware",
        "target_value": target,
        "principal": principal,
        "confidence": conf,
        "upstream_origin_signature": sig,
        "is_functional": True,
    }
    defaults.update(kw)
    return GraphOperation(**defaults)


def test_bayesian_higher_prior_wins():
    engine = ArbitrationEngine()
    # MalwareBazaar (0.833) vs OTX (0.636) with equal confidence
    op_mb = make_op("op-mb", "malwarebazaar", "redline stealer", conf=90)
    op_otx = make_op("op-otx", "otx", "cobalt strike", conf=90)

    decisions = engine.resolve([op_mb, op_otx], [(op_mb, op_otx)], mode="bayesian")
    assert decisions["op-mb"].decision == "accept"
    assert decisions["op-otx"].decision == "reject"
    assert decisions["op-mb"].posterior_prob > decisions["op-otx"].posterior_prob


def test_bayesian_peer_attestations_influence():
    engine = ArbitrationEngine()
    # ThreatFox alone vs OTX backed by URLhaus CONFIRM attestation
    att_urlhaus = PeerAttestation(
        responder_principal="urlhaus",
        stance="CONFIRM",
        confidence=95,
        upstream_origin_signature="unique-sig-1",
    )
    op_otx = make_op("op-otx", "otx", "redline stealer", conf=80, peer_attestations=[att_urlhaus])
    op_tf = make_op("op-tf", "threatfox", "vidar", conf=80)

    decisions = engine.resolve([op_otx, op_tf], [(op_otx, op_tf)], mode="bayesian")
    assert decisions["op-otx"].decision == "accept"
    assert decisions["op-tf"].decision == "reject"


def test_bayesian_lineage_deduplication():
    engine = ArbitrationEngine()
    # Two identical reports sharing same upstream signature count only once
    sig = "abuse_ch:shared_sample_42"
    att_dup = PeerAttestation(
        responder_principal="urlhaus",
        stance="CONFIRM",
        confidence=90,
        upstream_origin_signature=sig,
    )
    op1 = make_op("op-1", "threatfox", "redline stealer", conf=90, sig=sig, peer_attestations=[att_dup])
    op2 = make_op("op-2", "otx", "cobalt strike", conf=90)

    prob_with_dedup = engine.compute_posterior(op1, [op2])
    # The duplicate attestation should not double-count
    assert 0.5 < prob_with_dedup < 1.0


def test_fcfs_fallback_mode():
    engine = ArbitrationEngine()
    op1 = make_op("op-1", "otx", "first_candidate")
    op2 = make_op("op-2", "malwarebazaar", "second_candidate")

    decisions = engine.resolve([op1, op2], [(op1, op2)], mode="fcfs")
    assert decisions["op-1"].decision == "accept"
    assert decisions["op-2"].decision == "reject"


def test_bayesian_corroborating_claims_strengthen_hypothesis():
    engine = ArbitrationEngine()
    # ThreatFox alone vs OTX
    op_tf_alone = make_op("op-tf1", "threatfox", "redline stealer", conf=80)
    op_otx = make_op("op-otx", "otx", "cobalt strike", conf=80)
    p_alone = engine.compute_posterior(op_tf_alone, [op_otx])

    # ThreatFox AND URLhaus both corroborating "redline stealer" vs OTX
    op_urlhaus = make_op("op-uh", "urlhaus", "redline stealer", conf=80)
    p_corroborated = engine.compute_posterior(op_tf_alone, [op_otx], corroborators=[op_urlhaus])

    # Corroboration strictly increases posterior probability
    assert p_corroborated > p_alone

    # Both corroborators receive decision="accept"
    conflicts = [(op_tf_alone, op_otx), (op_urlhaus, op_otx)]
    decisions = engine.resolve([op_tf_alone, op_urlhaus, op_otx], conflicts, mode="bayesian")
    assert decisions["op-tf1"].decision == "accept"
    assert decisions["op-uh"].decision == "accept"
    assert decisions["op-otx"].decision == "reject"

