from analysis.conflict import detect_cti_conflicts
from analysis.overlap import find_cross_source_overlaps
from schemas.cti import NormalizedCTIRecord
from sources.threatfox import ThreatFoxSource


def test_threatfox_normalization():
    source = ThreatFoxSource()
    raw = {
        "id": "101",
        "ioc": "192.168.1.1:8080",
        "ioc_type": "ip:port",
        "malware_printable": "RedLine Stealer",
        "confidence_level": 90,
        "first_seen": "2026-09-21 00:00:00 UTC",
        "reporter": "analyst1",
    }
    records = source.normalize_record(raw)
    assert len(records) == 1
    rec = records[0]
    assert rec.source == "ThreatFox"
    assert rec.record_id == "101"
    assert rec.ioc_type == "ip"
    assert rec.ioc_value == "192.168.1.1"
    assert rec.malware_family == "RedLine Stealer"
    assert rec.confidence == 90


def test_overlap_and_conflict_detection():
    r1 = NormalizedCTIRecord(
        source="ThreatFox",
        record_id="1",
        timestamp="2026-09-21T00:00:00Z",
        ioc_type="ip",
        ioc_value="10.0.0.1",
        malware_family="RedLine",
        confidence=90,
        reporter="rep1",
        tags=[],
        raw_data={},
    )

    r2 = NormalizedCTIRecord(
        source="OTX",
        record_id="2",
        timestamp="2026-09-21T01:00:00Z",
        ioc_type="ip",
        ioc_value="10.0.0.1",
        malware_family="AgentTesla",  # Conflicting attribution
        confidence=40,  # Conflicting confidence (>25 divergence)
        reporter="rep2",
        tags=[],
        raw_data={},
    )

    records = [r1, r2]

    overlaps = find_cross_source_overlaps(records)
    assert len(overlaps) == 1
    assert overlaps[0]["ioc_value"] == "10.0.0.1"
    assert overlaps[0]["distinct_source_count"] == 2

    conflicts = detect_cti_conflicts(records)
    assert len(conflicts) == 1
    assert "attribution_conflict" in conflicts[0]["conflict_types"]
    assert "confidence_discrepancy" in conflicts[0]["conflict_types"]
