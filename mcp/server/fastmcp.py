"""
FastMCP Server implementation conforming to Model Context Protocol JSON-RPC 2.0 specifications.
"""

import asyncio
import inspect
import json
import sys
from typing import Any, Callable, Dict, Optional


class FastMCP:
    """FastMCP Server exposing registered resources and tools over stdio JSON-RPC transport."""

    def __init__(self, name: str):
        self.name = name
        self._resources: Dict[str, Callable] = {}
        self._tools: Dict[str, Callable] = {}

    def resource(self, uri: str) -> Callable:
        """Register a URI resource provider."""
        def decorator(fn: Callable) -> Callable:
            self._resources[uri] = fn
            return fn
        return decorator

    def tool(self, name: Optional[str] = None, description: Optional[str] = None) -> Callable:
        """Register an async tool function with automatic JSON Schema generation."""
        def decorator(fn: Callable) -> Callable:
            tool_name = name or fn.__name__
            tool_desc = description or (fn.__doc__ or "").strip()
            self._tools[tool_name] = {
                "func": fn,
                "name": tool_name,
                "description": tool_desc,
                "schema": self._generate_schema(fn),
            }
            return fn
        return decorator

    def _generate_schema(self, fn: Callable) -> Dict[str, Any]:
        sig = inspect.signature(fn)
        properties: Dict[str, Any] = {}
        required = []

        for p_name, param in sig.parameters.items():
            prop: Dict[str, Any] = {"title": p_name}
            annotation = param.annotation

            # Robust type matching supporting both raw types and string annotations
            if annotation in (int, "int"):
                prop["type"] = "integer"
            elif annotation in (float, "float"):
                prop["type"] = "number"
            elif annotation in (bool, "bool"):
                prop["type"] = "boolean"
            else:
                prop["type"] = "string"

            if param.default is not inspect.Parameter.empty:
                prop["default"] = param.default
            else:
                required.append(p_name)
            properties[p_name] = prop

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def run(self, transport: str = "stdio") -> None:
        """Run the FastMCP server event loop synchronously."""
        if transport != "stdio":
            raise ValueError(f"Unsupported transport: {transport}. Only 'stdio' is supported.")
        asyncio.run(self._run_stdio_async())

    async def _run_stdio_async(self) -> None:
        loop = asyncio.get_event_loop()
        # 10 MB line buffer to prevent LimitOverrunError on large payloads
        reader = asyncio.StreamReader(limit=10 * 1024 * 1024)
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break
            raw_str = line.decode("utf-8").strip()
            if not raw_str:
                continue

            try:
                req = json.loads(raw_str)
                response = await self._handle_rpc(req)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

    async def _handle_rpc(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}, "tools": {}},
                    "serverInfo": {"name": self.name, "version": "1.0.0"},
                },
            }

        if method == "notifications/initialized":
            return None

        if method == "resources/read":
            uri = params.get("uri")
            if uri in self._resources:
                handler = self._resources[uri]
                res_val = handler() if not inspect.iscoroutinefunction(handler) else await handler()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {"uri": uri, "mimeType": "application/json", "text": str(res_val)}
                        ]
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Resource not found: {uri}"},
            }

        if method == "tools/list":
            tools_list = [
                {
                    "name": t_meta["name"],
                    "description": t_meta["description"],
                    "inputSchema": t_meta["schema"],
                }
                for t_meta in self._tools.values()
            ]
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if tool_name in self._tools:
                fn = self._tools[tool_name]["func"]
                try:
                    result = fn(**arguments)
                    if inspect.iscoroutine(result):
                        result = await result
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": str(result)}]},
                    }
                except Exception as ex:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Error: {str(ex)}"}],
                            "isError": True,
                        },
                    }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not supported: {method}"},
        }

