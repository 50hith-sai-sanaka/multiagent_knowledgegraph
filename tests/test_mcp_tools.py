# tests/test_mcp_tools.py
"""
Tests for MCP Tool Adapters — STORY-008.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_tools.py -v
"""
from __future__ import annotations

import json

import pytest

from src.mcp.base_tool import MCPResponse
from src.mcp.malwarebazaar_tool import MalwareBazaarMCPTool
from src.mcp.otx_tool import OTXMCPTool
from src.mcp.threatfox_tool import ThreatFoxMCPTool
from src.mcp.tools import MCP_TOOLS
from src.mcp.urlhaus_tool import URLhausMCPTool

# ---------------------------------------------------------------------------
# Helpers — grab real IOCs from each source file so tests never hardcode values
# ---------------------------------------------------------------------------

def _first_ioc(json_path: str) -> str:
    """Return the ioc_value of the first record in a normalized JSON file."""
    with open(json_path, encoding="utf-8") as fh:
        records = json.load(fh)
    return records[0]["ioc_value"]

THREATFOX_IOC     = _first_ioc("data/normalized/threatfox.json")
URLHAUS_IOC       = _first_ioc("data/normalized/urlhaus.json")
MALWAREBAZAAR_IOC = _first_ioc("data/normalized/malwarebazaar.json")
OTX_IOC           = _first_ioc("data/normalized/otx.json")

# ---------------------------------------------------------------------------
# Tests — known IOC found in the correct source
# ---------------------------------------------------------------------------

def test_threatfox_tool_finds_known_ioc():
    tool = ThreatFoxMCPTool()
    resp = tool.invoke(THREATFOX_IOC)
    assert isinstance(resp, MCPResponse)
    assert resp.source == "ThreatFox"
    assert len(resp.records) >= 1
    for r in resp.records:
        assert r["source"] == "ThreatFox"


def test_urlhaus_tool_finds_known_ioc():
    tool = URLhausMCPTool()
    resp = tool.invoke(URLHAUS_IOC)
    assert isinstance(resp, MCPResponse)
    assert resp.source == "URLhaus"
    assert len(resp.records) >= 1
    for r in resp.records:
        assert r["source"] == "URLhaus"


def test_malwarebazaar_tool_finds_known_ioc():
    tool = MalwareBazaarMCPTool()
    resp = tool.invoke(MALWAREBAZAAR_IOC)
    assert isinstance(resp, MCPResponse)
    assert resp.source == "MalwareBazaar"
    assert len(resp.records) >= 1
    for r in resp.records:
        assert r["source"] == "MalwareBazaar"


def test_otx_tool_finds_known_ioc():
    tool = OTXMCPTool()
    resp = tool.invoke(OTX_IOC)
    assert isinstance(resp, MCPResponse)
    assert resp.source == "OTX"
    assert len(resp.records) >= 1
    for r in resp.records:
        assert r["source"] == "OTX"

# ---------------------------------------------------------------------------
# Test — unknown IOC returns empty list (never raises an exception)
# ---------------------------------------------------------------------------

def test_unknown_ioc_returns_empty_list():
    tool = ThreatFoxMCPTool()
    resp = tool.invoke("this-ioc-does-not-exist-999.example.com")
    assert isinstance(resp, MCPResponse)
    assert resp.records == []

# ---------------------------------------------------------------------------
# Test — cross-source isolation
# Each tool returns ONLY its own source's records, even if the IOC exists in another source.
# ---------------------------------------------------------------------------

def test_cross_source_isolation():
    tf = ThreatFoxMCPTool()
    uh = URLhausMCPTool()
    # URLhaus IOC searched in ThreatFox — any returned records must be ThreatFox
    for r in tf.invoke(URLHAUS_IOC).records:
        assert r["source"] == "ThreatFox"
    # ThreatFox IOC searched in URLhaus — any returned records must be URLhaus
    for r in uh.invoke(THREATFOX_IOC).records:
        assert r["source"] == "URLhaus"

# ---------------------------------------------------------------------------
# Tests — registry (MCP_TOOLS dict)
# ---------------------------------------------------------------------------

def test_registry_contains_all_principals():
    expected = {
        "Principal-ThreatFox",
        "Principal-URLhaus",
        "Principal-MalwareBazaar",
        "Principal-OTX",
    }
    assert set(MCP_TOOLS.keys()) == expected


def test_registry_returns_correct_tool_type():
    assert isinstance(MCP_TOOLS["Principal-ThreatFox"],     ThreatFoxMCPTool)
    assert isinstance(MCP_TOOLS["Principal-URLhaus"],       URLhausMCPTool)
    assert isinstance(MCP_TOOLS["Principal-MalwareBazaar"], MalwareBazaarMCPTool)
    assert isinstance(MCP_TOOLS["Principal-OTX"],           OTXMCPTool)


def test_registry_tool_can_invoke():
    tool = MCP_TOOLS["Principal-ThreatFox"]
    resp = tool.invoke(THREATFOX_IOC)
    assert isinstance(resp, MCPResponse)
    assert resp.source == "ThreatFox"
