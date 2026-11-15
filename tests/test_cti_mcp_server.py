"""
Tests for Standalone FastMCP CTI Data Server — STORY-011.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_cti_mcp_server.py -v
"""

import json
import pytest

from src.mcp_servers.cti_mcp_server import (
    _load_feed,
    get_tier1_ontology_schema,
    pivot_by_malware_family,
    search_cti_indicator,
)


def test_load_feed_caching():
    feed1 = _load_feed("ThreatFox")
    feed2 = _load_feed("principal-threatfox")
    assert feed1 is feed2
    assert isinstance(feed1, list)
    if feed1:
        assert "ioc_value" in feed1[0]


def test_ontology_schema_resource():
    raw_schema = get_tier1_ontology_schema()
    schema = json.loads(raw_schema)
    assert "node_labels" in schema
    assert "IP" in schema["node_labels"]
    assert "predicates" in schema
    assert "USES_C2" in schema["predicates"]
    assert "EXPLOITS" in schema["predicates"]
    assert "TARGETS" in schema["predicates"]
    assert schema["predicates"]["USES_C2"]["is_functional"] is True
    assert schema["predicates"]["ATTRIBUTED_TO"]["is_functional"] is False


@pytest.mark.asyncio
async def test_search_cti_indicator_taint_separation():
    threatfox_feed = _load_feed("threatfox")
    assert len(threatfox_feed) > 0
    sample_ioc = threatfox_feed[0]["ioc_value"]

    # Test with defanged variation
    defanged_ioc = sample_ioc.replace(".", "[.]")
    raw_res = await search_cti_indicator("threatfox", defanged_ioc)
    res = json.loads(raw_res)
    assert res["principal"] == "threatfox"
    assert res["ioc_value"] == sample_ioc.strip().lower()
    assert len(res["matches"]) >= 1

    match = res["matches"][0]
    assert "trusted_telemetry" in match
    assert "tainted_text_origin" in match
    assert match["raw_evidence_sha256"].startswith("sha256:")
    assert len(match["raw_evidence_sha256"]) == 71
    assert "upstream_origin_signature" in match


@pytest.mark.asyncio
async def test_pivot_by_malware_family_limit():
    raw_res = await pivot_by_malware_family("threatfox", "Cobalt Strike", limit=2)
    res = json.loads(raw_res)
    assert res["malware_family"] == "Cobalt Strike"
    assert len(res["pivots"]) <= 2
    for p in res["pivots"]:
        assert p["malware_family"].lower() == "cobalt strike"
        assert "ioc_value" in p
        assert "confidence" in p

