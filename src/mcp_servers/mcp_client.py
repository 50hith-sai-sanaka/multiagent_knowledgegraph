"""
Real MCP Protocol Client (JSON-RPC 2.0 via mcp.ClientSession)
File: src/mcp_servers/mcp_client.py
"""

import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import Field, create_model


class RealMCPClientManager:
    """Connects to cti_mcp_server.py over real MCP JSON-RPC stdio transport."""

    def __init__(self, server_script: str = "src/mcp_servers/cti_mcp_server.py"):
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env=dict(os.environ),
        )

    @asynccontextmanager
    async def session(self):
        """Opens a real JSON-RPC 2.0 MCP ClientSession over stdio."""
        async with stdio_client(self.server_params) as (read_stream, write_stream):
            mcp_session = ClientSession(read_stream, write_stream)
            await mcp_session.initialize()
            yield mcp_session

    async def read_ontology_resource(self, mcp_session: ClientSession) -> Dict[str, Any]:
        """Reads the active ontology schema via MCP resources/read."""
        res = await mcp_session.read_resource("ontology://tier1-schema")
        for content in res.contents:
            if hasattr(content, "text") and content.text:
                return json.loads(content.text)
        return {}

    async def discover_langchain_tools(
        self, mcp_session: ClientSession, bound_principal: str
    ) -> List[StructuredTool]:
        """
        Dynamically calls MCP tools/list over JSON-RPC and builds LangChain StructuredTools
        with principal cryptographically bound in closure so the LLM cannot spoof its identity.
        """
        tools_response = await mcp_session.list_tools()
        lc_tools: List[StructuredTool] = []

        for tool_def in tools_response.tools:
            t_name = tool_def.name
            t_desc = tool_def.description or f"MCP Tool {t_name}"
            props = tool_def.inputSchema.get("properties", {})

            # Build dynamic Pydantic args_schema excluding 'principal' (injected via closure)
            fields_dict: Dict[str, Any] = {}
            for prop_name, prop_meta in props.items():
                if prop_name == "principal":
                    continue
                py_type = int if prop_meta.get("type") == "integer" else str
                default_val = prop_meta.get("default", ...)
                fields_dict[prop_name] = (
                    py_type,
                    Field(default=default_val, description=prop_meta.get("title", "")),
                )

            ArgsModel = create_model(f"{t_name}_Args", **fields_dict)

            def _make_tool_invoker(target_tool: str):
                async def _invoke_mcp_tool(**kwargs) -> str:
                    payload = dict(kwargs)
                    payload["principal"] = bound_principal
                    rpc_result = await mcp_session.call_tool(target_tool, arguments=payload)
                    texts = [c.text for c in rpc_result.content if hasattr(c, "text")]
                    return "\n".join(texts)
                return _invoke_mcp_tool

            lc_tools.append(
                StructuredTool.from_function(
                    coroutine=_make_tool_invoker(t_name),
                    name=t_name,
                    description=t_desc,
                    args_schema=ArgsModel,
                )
            )

        return lc_tools

