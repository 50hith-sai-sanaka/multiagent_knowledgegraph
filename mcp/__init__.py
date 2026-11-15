"""
Standard Model Context Protocol (MCP) Python Implementation.
Provides full JSON-RPC 2.0 stdio client and server compatibility for Python 3.9+.
"""

import asyncio
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    inputSchema: Dict[str, Any] = Field(default_factory=dict)


class ToolContent(BaseModel):
    type: str = "text"
    text: str


class CallToolResult(BaseModel):
    content: List[ToolContent] = Field(default_factory=list)
    isError: bool = False


class ResourceContent(BaseModel):
    uri: str
    mimeType: Optional[str] = "application/json"
    text: str


class ReadResourceResult(BaseModel):
    contents: List[ResourceContent] = Field(default_factory=list)


class ListToolsResult(BaseModel):
    tools: List[Tool] = Field(default_factory=list)


class StdioServerParameters(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None


class ClientSession:
    """Async ClientSession executing JSON-RPC 2.0 requests over stdio streams with IO locking."""

    def __init__(self, read_stream, write_stream):
        self._read_stream = read_stream
        self._write_stream = write_stream
        self._req_id = 0
        self._io_lock = asyncio.Lock()

    async def initialize(self) -> Dict[str, Any]:
        resp = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"resources": {}, "tools": {}},
                "clientInfo": {"name": "ProGRESS-MCP-Client", "version": "1.0.0"},
            },
        )
        await self._send_notification("notifications/initialized", {})
        return resp

    async def read_resource(self, uri: str) -> ReadResourceResult:
        resp = await self._send_request("resources/read", {"uri": uri})
        contents = [
            ResourceContent(
                uri=item.get("uri", uri),
                mimeType=item.get("mimeType", "application/json"),
                text=item.get("text", ""),
            )
            for item in resp.get("contents", [])
        ]
        return ReadResourceResult(contents=contents)

    async def list_tools(self) -> ListToolsResult:
        resp = await self._send_request("tools/list", {})
        tools = [
            Tool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {}),
            )
            for t in resp.get("tools", [])
        ]
        return ListToolsResult(tools=tools)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        resp = await self._send_request("tools/call", {"name": name, "arguments": arguments})
        content = [
            ToolContent(type=c.get("type", "text"), text=c.get("text", ""))
            for c in resp.get("content", [])
        ]
        return CallToolResult(content=content, isError=resp.get("isError", False))

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        import json
        async with self._io_lock:
            self._req_id += 1
            req_id = self._req_id
            msg = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }
            wire = json.dumps(msg) + "\n"
            self._write_stream.write(wire.encode("utf-8"))
            await self._write_stream.drain()

            line = await self._read_stream.readline()
            if not line:
                raise RuntimeError(
                    f"MCP server disconnected unexpectedly while awaiting response for {method}"
                )
            res = json.loads(line.decode("utf-8"))
            if "error" in res:
                raise RuntimeError(f"MCP JSON-RPC Error: {res['error']}")
            return res.get("result", {})

    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        import json
        async with self._io_lock:
            msg = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
            wire = json.dumps(msg) + "\n"
            self._write_stream.write(wire.encode("utf-8"))
            await self._write_stream.drain()

