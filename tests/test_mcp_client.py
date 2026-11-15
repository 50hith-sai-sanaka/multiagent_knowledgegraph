"""
Tests for Real MCP Client Manager — STORY-012.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_client.py -v
"""

import json
import pytest

from src.mcp_servers.mcp_client import RealMCPClientManager


@pytest.mark.asyncio
async def test_mcp_client_session_and_resource_read():
    mgr = RealMCPClientManager()
    async with mgr.session() as session:
        schema = await mgr.read_ontology_resource(session)
        assert isinstance(schema, dict)
        assert "node_labels" in schema
        assert "IP" in schema["node_labels"]
        assert "predicates" in schema
        assert schema["predicates"]["USES_C2"]["is_functional"] is True
        assert schema["predicates"]["EXPLOITS"]["is_functional"] is False


@pytest.mark.asyncio
async def test_mcp_client_discover_langchain_tools_and_invoke():
    mgr = RealMCPClientManager()
    async with mgr.session() as session:
        tools = await mgr.discover_langchain_tools(session, bound_principal="threatfox")
        tool_names = [t.name for t in tools]
        assert "search_cti_indicator" in tool_names
        assert "pivot_by_malware_family" in tool_names

        search_tool = next(t for t in tools if t.name == "search_cti_indicator")
        # Verify 'principal' is excluded from LLM-visible arguments schema
        assert "principal" not in search_tool.args
        assert "ioc_value" in search_tool.args

        # Invoke tool over JSON-RPC wire
        raw_result = await search_tool.ainvoke({"ioc_value": "139.59.33.238"})
        res = json.loads(raw_result)
        assert res["principal"] == "threatfox"
        assert res["ioc_value"] == "139.59.33.238"
        assert "matches" in res

