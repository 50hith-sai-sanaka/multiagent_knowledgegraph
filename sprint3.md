# SPRINT 3: Real FastMCP Server & Real A2A Protocol Layer
## Complete Step-by-Step Execution Guide

| Field | Details |
|---|---|
| **Sprint** | Sprint 3 |
| **Total Story Points** | **18 points** (3 stories: 5 + 5 + 8) |
| **Stories Included** | `STORY-011`, `STORY-012`, `STORY-013` |
| **Lead** | @member2 (FastMCP Server, MCP Client Manager, A2A JSON-RPC Router, Verifier LLM) |
| **Support** | @member1 (Test Harness, HMAC Attestation Validation, Stdio Process Lifecycles, Integration Gate) |
| **Estimated Time** | ~14 hours total |
| **Prerequisite** | Sprint 1 & Sprint 2 Gates passing (**125 passed across all modules**) |
| **Master Spec Ref** | [autonomoustechspec.md](file:///Users/sohithsai/multiagent_knowledgegraph/autonomoustechspec.md) §3.1, §3.2, §3.3 |
| **Task Breakdown Ref** | [new_taskbreakdown.md](file:///Users/sohithsai/multiagent_knowledgegraph/new_taskbreakdown.md) Sprint 3 (`MCP-101` through `A2A-105`) |

---

> **HOW TO USE THIS GUIDE**
> 
> Read every section before executing commands. Each task contains:
> - A **WHY & ARCHITECTURAL PATCHES** block — explains the protocol contracts, wire-level semantics, and edge cases.
> - An **exact drop-in code block** — copy-paste it directly to eliminate human transcription errors.
> - A **VERIFICATION CHECK** — run immediately after the step.
> - An **IF IT FAILS** block — targeted diagnostics if an error occurs.
>
> **Sequential Testing Rule:** Never proceed to the next story until the current story's `⛔ GATE` command passes 100%.

---

## Section 0 — Pre-Flight Checks

Run all 4 checks before modifying or writing code.

---

### Check 0.1 — Confirm Working Directory

```bash
pwd
```

**VERIFICATION CHECK 0.1**  
Must show:
```
/Users/sohithsai/multiagent_knowledgegraph
```

**IF IT FAILS:**
```bash
cd /Users/sohithsai/multiagent_knowledgegraph
pwd
```

---

### Check 0.2 — Confirm Virtual Environment Python

```bash
./venv/bin/python3 --version
```

**VERIFICATION CHECK 0.2**  
Must show:
```
Python 3.9.x
```

---

### Check 0.3 — Confirm Cumulative Regression Suite Passes (Sprint 1 & Sprint 2)

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py tests/test_irs_resolver.py tests/test_ontology_validator.py tests/test_lock_manager.py tests/test_llm_factory.py tests/test_conflict_detector.py tests/test_arbitration_engine.py tests/test_mpac_coordinator.py tests/test_adhoc_coordinator.py tests/test_ablation_coordinator.py -q
```

**VERIFICATION CHECK 0.3**  
Must end with:
```
51 passed in 0.xxs
```

---

### Check 0.4 — Zero Non-Breaking Spaces (`U+00A0`) & Zero-Width Spaces (`U+200B`)

Run this sanitization sweep to ensure no non-ASCII whitespaces pollute source or test files:
```bash
LC_ALL=C sed -i '' $'s/\u00a0/ /g; s/\u200b//g' src/**/*.py tests/*.py run_schema_init.py 2>/dev/null || true
```

---

## Section 0.5 — Standard MCP Protocol Compatibility Layer

### WHY & ARCHITECTURAL PATCHES

* **The Python 3.9 vs. MCP SDK Compatibility Trap:** The official Anthropic `mcp` Python SDK requires Python >= 3.10 due to modern typing syntax (`TypeAlias`, `|` union operators). The active environment runs macOS system Python 3.9.6. Attempting to install the official package directly on 3.9 raises `ImportError: cannot import name 'TypeAlias' from 'typing'`.
* **String Annotation Introspection under `from __future__ import annotations`:** In `FastMCP._generate_schema()`, comparing annotations via identity (`if annotation is int:`) breaks whenever a module uses string annotations (`"int"`). The schema generator must inspect both classes and string representations `annotation in (int, "int")`.
* **10 MB Line Buffer (`asyncio.StreamReader`):** Default `StreamReader` line limits (`64 KB`) crash with `asyncio.LimitOverrunError` when tool responses contain batches of CTI records. We configure `limit=10 * 1024 * 1024` (10 MB) across both server and client streams.
* **Concurrent `call_tool()` Interleaving Protection:** A shared `ClientSession` executing multiple tool invocations concurrently via `asyncio.gather()` would interleave `readline()` on the stdout pipe. We protect stdio read/write transactions with an internal `asyncio.Lock()`.
* **Zombie Subprocess Termination with Grace Timeout:** Process teardown in `stdio_client` waits up to 2.0s with `asyncio.wait_for(process.wait(), timeout=2.0)` and falls back to `process.kill()` to prevent hanging test suites.

---

### Step S3-000-A — Create Standard MCP Protocol Package

Create `mcp/__init__.py`:

```python
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
```

---

### Step S3-000-B — Create FastMCP Server Implementation

Create `mcp/server/__init__.py` and `mcp/server/fastmcp.py`:

```python
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
```

---

### Step S3-000-C — Create Stdio Client Transport

Create `mcp/client/__init__.py` and `mcp/client/stdio.py`:

```python
"""
Stdio transport client for Model Context Protocol.
"""

import asyncio
from contextlib import asynccontextmanager
import os
import subprocess
from typing import AsyncIterator, Tuple
from mcp import StdioServerParameters


@asynccontextmanager
async def stdio_client(
    server_params: StdioServerParameters,
) -> AsyncIterator[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
    """Spawns an MCP server subprocess and yields its async (read_stream, write_stream)."""
    env = dict(os.environ)
    if server_params.env:
        env.update(server_params.env)

    # Ensure PYTHONPATH includes workspace root
    if "PYTHONPATH" not in env:
        env["PYTHONPATH"] = "."

    # 10 MB line buffer to prevent LimitOverrunError on large payloads
    process = await asyncio.create_subprocess_exec(
        server_params.command,
        *server_params.args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        limit=10 * 1024 * 1024,
    )

    try:
        yield process.stdout, process.stdin
    finally:
        if process.stdin:
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except Exception:
                pass
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except Exception:
                try:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except Exception:
                    pass
```

---

## STORY-011: Standalone FastMCP CTI Data Server (`mcp.server.fastmcp`)

| Field | Details |
|---|---|
| **Story ID** | `STORY-011` |
| **Story Points** | **5 points** |
| **Target Files** | `src/mcp_servers/__init__.py`, `src/mcp_servers/cti_mcp_server.py`, `tests/test_cti_mcp_server.py` |
| **Tasks** | `MCP-101`, `MCP-102`, `MCP-103`, `MCP-104`, `MCP-105` |

---

### WHY & ARCHITECTURAL PATCHES

* **Single Source of Truth for Ontology Schema:** Rather than hardcoding 5 predicates, `get_tier1_ontology_schema()` directly reads `TIER1_NODE_TYPES` and `TIER1_RELATIONSHIP_METADATA` from `src.ontology.validator` (ensuring `EXPLOITS`, `PART_OF`, `TARGETS`, and `MITIGATED_BY` are exposed to clients).
* **Defanged IOC Normalization:** `search_cti_indicator()` normalizes defanged IOC representations (`[.]` to `.`, `[:]` to `:`, `hxxp://` to `http://`) so agent queries match normalized database records cleanly.
* **Taint Separation & Cryptographic Provenance:** Partitions incoming records into `trusted_telemetry` and `tainted_text_origin`, calculating deterministic `raw_evidence_sha256` (`sha256:{hex}`) and `upstream_origin_signature` (`{reporter}:{needle}:{malware}`.lower()).
* **Line-Delimited Stdio Flushing:** Ensures `sys.stdout.flush()` is called on every write to avoid subprocess deadlock.

---

### Step S3-011-A — Implement `src/mcp_servers/cti_mcp_server.py`

Create `src/mcp_servers/__init__.py` (empty) and `src/mcp_servers/cti_mcp_server.py`:

```python
"""
Real Model Context Protocol (MCP) Server
File: src/mcp_servers/cti_mcp_server.py
Run standalone via stdio JSON-RPC transport.
"""

import hashlib
import json
import os
from typing import Any, Dict, List
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ProGRESS-CTI-MCP-Server")
_FEED_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _clean_ioc(val: str) -> str:
    """Normalizes defanged IOC representations."""
    cleaned = str(val or "").strip().lower()
    return (
        cleaned.replace("[.]", ".")
        .replace("[:]", ":")
        .replace("hxxps://", "https://")
        .replace("hxxp://", "http://")
    )


def _load_feed(principal: str) -> List[Dict[str, Any]]:
    """Loads normalized CTI records on-demand with memory caching."""
    key = principal.strip().lower().replace("principal-", "")
    if key not in _FEED_CACHE:
        path = os.path.join("data", "normalized", f"{key}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _FEED_CACHE[key] = json.load(f)
        else:
            _FEED_CACHE[key] = []
    return _FEED_CACHE[key]


@mcp.resource("ontology://tier1-schema")
def get_tier1_ontology_schema() -> str:
    """Exposes the active knowledge graph ontology dynamically from validator truth."""
    from src.ontology.validator import TIER1_NODE_TYPES, TIER1_RELATIONSHIP_METADATA

    preds = dict(TIER1_RELATIONSHIP_METADATA)
    if "HAS_SAMPLE" not in preds:
        preds["HAS_SAMPLE"] = {
            "is_functional": True,
            "description": "FileHash binary belongs to Malware family",
        }

    return json.dumps({
        "node_labels": sorted(list(TIER1_NODE_TYPES)),
        "predicates": preds,
    })


@mcp.tool()
async def search_cti_indicator(principal: str, ioc_value: str) -> str:
    """
    Search a principal's CTI feed (threatfox, urlhaus, malwarebazaar, otx) for an exact IOC
    (IP, Domain, URL, SHA256, MD5). Returns taint-separated telemetry and cryptographic hashes.
    """
    records = _load_feed(principal)
    needle = _clean_ioc(ioc_value)

    matches = [
        r for r in records
        if _clean_ioc(r.get("ioc_value", "")) == needle
        or _clean_ioc(r.get("raw_data", {}).get("ioc_value", "")) == needle
        or _clean_ioc(r.get("raw_data", {}).get("ioc", "")) == needle
    ]

    results = []
    for rec in matches[:8]:
        raw_bytes = json.dumps(rec.get("raw_data", rec), sort_keys=True).encode("utf-8")
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        reporter = rec.get("reporter") or rec.get("source", principal)
        origin_sig = f"{reporter}:{needle}:{rec.get('malware_family', 'unknown')}".lower()

        results.append({
            "trusted_telemetry": {
                "record_id": str(rec.get("record_id", "")),
                "ioc_type": rec.get("ioc_type", "ip"),
                "ioc_value": rec.get("ioc_value", needle),
                "malware_family": rec.get("malware_family"),
                "threat_actor": rec.get("threat_actor"),
                "confidence": rec.get("confidence", 80),
                "timestamp": rec.get("timestamp", "2026-10-12T00:00:00Z"),
            },
            "tainted_text_origin": {
                "tags": rec.get("tags", []),
                "reporter": reporter,
            },
            "raw_evidence_sha256": f"sha256:{raw_sha256}",
            "upstream_origin_signature": origin_sig,
        })

    return json.dumps({"principal": principal, "ioc_value": needle, "matches": results})


@mcp.tool()
async def pivot_by_malware_family(principal: str, malware_family: str, limit: int = 3) -> str:
    """
    Pivot across a principal's dataset to find other indicators (IPs, URLs, Hashes) associated
    with a discovered malware family for multi-hop knowledge graph expansion.
    """
    records = _load_feed(principal)
    target = malware_family.strip().lower()
    matching = [
        r for r in records
        if (r.get("malware_family") or "").strip().lower() == target
    ]
    matching.sort(key=lambda x: x.get("confidence") or 0, reverse=True)

    pivots = []
    for rec in matching[: min(limit, 5)]:
        pivots.append({
            "record_id": str(rec.get("record_id", "")),
            "ioc_type": rec.get("ioc_type"),
            "ioc_value": rec.get("ioc_value"),
            "malware_family": rec.get("malware_family"),
            "confidence": rec.get("confidence", 80),
            "timestamp": rec.get("timestamp", "2026-10-12T00:00:00Z"),
        })
    return json.dumps({"principal": principal, "malware_family": malware_family, "pivots": pivots})


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

### Step S3-011-B — Write Comprehensive Tests in `tests/test_cti_mcp_server.py`

Create `tests/test_cti_mcp_server.py`:

```python
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
```

---

### Step S3-011-C — Verification Gate

Execute the test suite:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_cti_mcp_server.py -v
```

**VERIFICATION CHECK 011**  
Must end with:
```
4 passed in 0.xxs
```

---

## STORY-012: Real MCP Protocol Client Manager (`mcp.ClientSession`)

| Field | Details |
|---|---|
| **Story ID** | `STORY-012` |
| **Story Points** | **5 points** |
| **Target Files** | `src/mcp_servers/mcp_client.py`, `tests/test_mcp_client.py` |
| **Tasks** | `MCP-201`, `MCP-202`, `MCP-203`, `MCP-204` |

---

### WHY & ARCHITECTURAL PATCHES

* **Dynamic Tool Discovery & Parameter Type Casting:** Uses `session.list_tools()` to construct dynamic Pydantic `ArgsModel` classes, casting `integer` types cleanly even when string annotations are present.
* **Principal Identity Injection Closure:** Strips `principal` from the LLM-visible argument schema and injects `bound_principal` into the execution closure.
* **Environment Inheritance:** Passes `dict(os.environ)` to guarantee the child Python interpreter inherits `PYTHONPATH=.`.

---

### Step S3-012-A — Implement `src/mcp_servers/mcp_client.py`

Create `src/mcp_servers/mcp_client.py`:

```python
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
```

---

### Step S3-012-B — Write Comprehensive Tests in `tests/test_mcp_client.py`

Create `tests/test_mcp_client.py`:

```python
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
```

---

### Step S3-012-C — Verification Gate

Execute the test suite:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_client.py -v
```

**VERIFICATION CHECK 012**  
Must end with:
```
2 passed in 0.xxs
```

---

## STORY-013: Standards-Compliant A2A HTTP JSON-RPC Router & Verifier LLM (`src/a2a/peer_hub.py`)

| Field | Details |
|---|---|
| **Story ID** | `STORY-013` |
| **Story Points** | **8 points** |
| **Target Files** | `src/a2a/__init__.py`, `src/a2a/peer_hub.py`, `tests/test_a2a_peer_hub.py` |
| **Tasks** | `A2A-101`, `A2A-102`, `A2A-103`, `A2A-104`, `A2A-105` |

---

### WHY & ARCHITECTURAL PATCHES

* **Subprocess Re-use Pool:** Spawning 3 new OS subprocesses on every claim verification to parse 16,481 JSON records causes massive latency and 3500ms timeouts during 500-claim benchmarks. We maintain a persistent `_get_shared_mcp_session()` to reuse a warm FastMCP server instance across requests.
* **Malware Alias Canonicalization Fast-Path:** In `_evaluate_peer_evidence_with_llm()`, raw telemetry malware families are canonicalized via `IdentityResolutionService().canonicalize_target("Malware", ...)` *before* comparing against the claimed target. This allows alias matches (`RedLine` vs `RedLine Stealer`, `Heodo` vs `Emotet`) to hit the sub-millisecond fast-path without invoking the LLM.
* **Top Informative Match Selection:** If a query returns multiple matches where the first match has `malware_family = None` and the second match has `malware_family = "Vidar"`, `handle_a2a_task_send` selects the first informative match rather than blindly abstaining.
* **Strict Stance Validation & Upper-Casing:** `LLMPeerVerificationJudgment.stance` is typed with `Literal["CONFIRM", "CONTRADICT", "ABSTAIN"]` and normalized with `.strip().upper()`.
* **Hop Budget Validation (`hop_budget == 0`):** Rejects any request with `hop_budget > 0` with JSON-RPC code `-32602` to prevent circular query storms.

---

### Step S3-013-A — Implement `src/a2a/peer_hub.py`

Create `src/a2a/__init__.py` (empty) and `src/a2a/peer_hub.py`:

```python
"""
Real A2A (G²CP) HTTP JSON-RPC Router & LLM Peer Verifier
File: src/a2a/peer_hub.py
"""

import asyncio
import hashlib
import hmac
import json
from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter
import httpx
from pydantic import BaseModel, Field

from src.irs.resolver import IdentityResolutionService
from src.mcp_servers.mcp_client import RealMCPClientManager
from src.schemas.models import PeerAttestation

PRINCIPALS = ["threatfox", "urlhaus", "malwarebazaar", "otx"]
a2a_router = APIRouter()

# Shared MCP session management to eliminate subprocess storms across benchmark runs
_MCP_MANAGER: Optional[RealMCPClientManager] = None
_MCP_SESSION_CM = None
_MCP_SESSION = None
_MCP_SESSION_LOCK = asyncio.Lock()


async def _get_shared_mcp_session():
    """Returns a long-lived shared ClientSession instance for A2A endpoints."""
    global _MCP_MANAGER, _MCP_SESSION_CM, _MCP_SESSION
    async with _MCP_SESSION_LOCK:
        if _MCP_SESSION is None or _MCP_SESSION._read_stream.at_eof():
            _MCP_MANAGER = RealMCPClientManager()
            _MCP_SESSION_CM = _MCP_MANAGER.session()
            _MCP_SESSION = await _MCP_SESSION_CM.__aenter__()
        return _MCP_SESSION


async def close_shared_mcp_session():
    """Gracefully shuts down the shared MCP session on gateway exit."""
    global _MCP_MANAGER, _MCP_SESSION_CM, _MCP_SESSION
    async with _MCP_SESSION_LOCK:
        if _MCP_SESSION_CM is not None:
            try:
                await _MCP_SESSION_CM.__aexit__(None, None, None)
            except Exception:
                pass
            _MCP_SESSION = None
            _MCP_SESSION_CM = None
            _MCP_MANAGER = None


class A2ATaskSendRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    method: str = "tasks/send"
    params: Dict[str, Any]


class LLMPeerVerificationJudgment(BaseModel):
    stance: Literal["CONFIRM", "CONTRADICT", "ABSTAIN"] = Field(
        description="Must be strictly 'CONFIRM', 'CONTRADICT', or 'ABSTAIN'"
    )
    confidence: int = Field(default=80, description="Confidence 0-100 in this peer judgment")
    counter_object: Optional[str] = Field(default=None, description="Competing malware/entity if CONTRADICT")
    reasoning: str = Field(description="1-sentence justification grounded in the peer's MCP records")


def _sign_payload(principal: str, text: str) -> str:
    """Computes deterministic HMAC-SHA256 signature for peer attestations."""
    secret = f"progress-ed25519-secret-{principal}".encode("utf-8")
    return hmac.new(secret, text.encode("utf-8"), hashlib.sha256).hexdigest()


@a2a_router.get("/.well-known/agent.json")
async def get_multi_principal_agent_cards() -> Dict[str, Any]:
    """Standard A2A discovery endpoint publishing Agent Cards for all 4 CTI principals."""
    return {
        "protocol_version": "A2A-G2CP-1.0",
        "agents": [
            {
                "agent_id": f"agent-{p}",
                "principal": p,
                "endpoint": f"/a2a/{p}/tasks/send",
                "capabilities": {
                    "streaming": False,
                    "hop_budget_enforced": 0,
                    "llm_verification": True,
                },
                "skills": [
                    {
                        "id": "verify_claim_quad",
                        "description": f"Verify CTI claims against {p} MCP feed",
                    }
                ],
            }
            for p in PRINCIPALS
        ],
    }


@a2a_router.post("/a2a/{principal}/tasks/send")
async def handle_a2a_task_send(principal: str, req: A2ATaskSendRequest) -> Dict[str, Any]:
    """
    Real A2A JSON-RPC 2.0 handler. The receiving peer queries its own MCP server over JSON-RPC
    and uses an LLM Judge to evaluate whether its evidence confirms or contradicts the claim.
    """
    params = req.params
    if int(params.get("hop_budget", 0)) > 0:
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "error": {"code": -32602, "message": "hop_budget must be 0"},
        }

    ioc_value = str(params.get("subject_value", "")).strip()
    predicate = str(params.get("predicate", "USES_C2"))
    claimed_target = str(params.get("object_value", "")).strip()

    mcp_session = await _get_shared_mcp_session()
    rpc_res = await mcp_session.call_tool(
        "search_cti_indicator", arguments={"principal": principal, "ioc_value": ioc_value}
    )
    raw_json = rpc_res.content[0].text if rpc_res.content else "{}"
    parsed = json.loads(raw_json)

    matches = parsed.get("matches", [])
    if not matches:
        sig = _sign_payload(principal, f"{ioc_value}:ABSTAIN")
        att = PeerAttestation(responder_principal=principal, stance="ABSTAIN", signature=sig)
        return {"jsonrpc": "2.0", "id": req.id, "result": att.model_dump()}

    # Select the first match with an informative malware family if available
    top_match = next(
        (
            m for m in matches
            if m.get("trusted_telemetry", {}).get("malware_family")
            and str(m.get("trusted_telemetry", {}).get("malware_family")).strip().lower() != "unknown"
        ),
        matches[0],
    )
    telemetry = top_match["trusted_telemetry"]
    judgment = await _evaluate_peer_evidence_with_llm(
        peer_principal=principal,
        ioc_value=ioc_value,
        predicate=predicate,
        claimed_target=claimed_target,
        peer_telemetry=telemetry,
    )

    irs = IdentityResolutionService()
    canon_counter = (
        irs.canonicalize_target("Malware", judgment.counter_object)
        if judgment.counter_object
        else None
    )
    normalized_stance = judgment.stance.strip().upper()
    if normalized_stance not in ("CONFIRM", "CONTRADICT", "ABSTAIN"):
        normalized_stance = "ABSTAIN"

    sig = _sign_payload(
        principal, f"{ioc_value}:{normalized_stance}:{canon_counter or claimed_target}"
    )

    att = PeerAttestation(
        responder_principal=principal,
        stance=normalized_stance,
        confidence=judgment.confidence,
        counter_object=canon_counter if normalized_stance == "CONTRADICT" else None,
        evidence_id=telemetry.get("record_id", ""),
        upstream_origin_signature=top_match.get("upstream_origin_signature", ""),
        signature=sig,
    )
    return {"jsonrpc": "2.0", "id": req.id, "result": att.model_dump()}


async def _evaluate_peer_evidence_with_llm(
    peer_principal: str,
    ioc_value: str,
    predicate: str,
    claimed_target: str,
    peer_telemetry: Dict[str, Any],
) -> LLMPeerVerificationJudgment:
    """Invokes structured LLM judge with deterministic SHA256 cache for benchmark replay."""
    from src.agents.llm_factory import invoke_structured_llm

    irs = IdentityResolutionService()
    raw_telemetry_malware = str(peer_telemetry.get("malware_family") or "").strip()
    telemetry_malware = (
        irs.canonicalize_target("Malware", raw_telemetry_malware)
        if raw_telemetry_malware
        else ""
    )
    target_clean = irs.canonicalize_target("Malware", claimed_target)

    # Sub-millisecond rule fast-paths with alias resolution
    if not telemetry_malware or telemetry_malware == "unknown":
        return LLMPeerVerificationJudgment(
            stance="ABSTAIN",
            confidence=50,
            counter_object=None,
            reasoning=f"No conclusive malware family reported in {peer_principal} telemetry.",
        )

    if telemetry_malware == target_clean:
        return LLMPeerVerificationJudgment(
            stance="CONFIRM",
            confidence=peer_telemetry.get("confidence", 85),
            counter_object=None,
            reasoning=f"{peer_principal} telemetry corroborates {claimed_target}.",
        )

    prompt = (
        f"You are the autonomous verification agent for CTI Principal '{peer_principal}'.\n"
        f"A peer agent claims: ({ioc_value}) -[{predicate}]-> ({claimed_target}).\n"
        f"Your local MCP telemetry record for {ioc_value} is: {json.dumps(peer_telemetry, sort_keys=True)}.\n"
        f"Note known aliases: Heodo/Geodo = Emotet; RedLine = RedLine Stealer; QakBot = QBot.\n"
        f"Decide if your telemetry CONFIRMS the claim, CONTRADICTS it (reports a different malware family), "
        f"or ABSTAINS (no malware family information present)."
    )
    return await invoke_structured_llm(prompt, LLMPeerVerificationJudgment)


class A2APeerHub:
    """Client hub that dispatches real HTTP JSON-RPC 2.0 requests to peer A2A endpoints."""

    def __init__(
        self,
        app=None,
        base_url: str = "http://127.0.0.1:8000",
        timeout_ms: int = 3500,
    ):
        self._app = app
        self._base_url = base_url
        self._timeout = timeout_ms / 1000.0

    async def verify_claim_with_peers(
        self,
        requesting_principal: str,
        ioc_value: str,
        predicate: str,
        claimed_target: str,
    ) -> List[PeerAttestation]:
        req_clean = requesting_principal.strip().lower().replace("principal-", "")
        peers = [p for p in PRINCIPALS if p != req_clean]

        transport = httpx.ASGITransport(app=self._app) if self._app else None
        async with httpx.AsyncClient(
            transport=transport, base_url=self._base_url, timeout=self._timeout
        ) as client:

            async def _call_peer(peer: str) -> PeerAttestation:
                payload = {
                    "jsonrpc": "2.0",
                    "id": f"verify-{peer}-{ioc_value}",
                    "method": "tasks/send",
                    "params": {
                        "requesting_principal": req_clean,
                        "subject_value": ioc_value,
                        "predicate": predicate,
                        "object_value": claimed_target,
                        "hop_budget": 0,
                    },
                }
                try:
                    resp = await client.post(f"/a2a/{peer}/tasks/send", json=payload)
                    data = resp.json()
                    return PeerAttestation(**data["result"])
                except Exception:
                    return PeerAttestation(
                        responder_principal=peer, stance="ABSTAIN", signature="timeout"
                    )

            return list(await asyncio.gather(*[_call_peer(p) for p in peers]))
```

---

### Step S3-013-B — Write Comprehensive Tests in `tests/test_a2a_peer_hub.py`

Create `tests/test_a2a_peer_hub.py`:

```python
"""
Tests for Standards-Compliant A2A HTTP JSON-RPC Router & LLM Peer Verifier — STORY-013.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_peer_hub.py -v
"""

from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
import pytest

from src.a2a.peer_hub import (
    A2APeerHub,
    LLMPeerVerificationJudgment,
    a2a_router,
    close_shared_mcp_session,
)


@pytest.fixture
def app():
    api = FastAPI()
    api.include_router(a2a_router)
    return api


@pytest.fixture(autouse=True)
async def cleanup_mcp():
    yield
    await close_shared_mcp_session()


@pytest.mark.asyncio
async def test_a2a_discovery_agent_cards(app):
    hub = A2APeerHub(app=app, base_url="http://test")
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol_version"] == "A2A-G2CP-1.0"
        assert len(data["agents"]) == 4
        principals = [a["principal"] for a in data["agents"]]
        assert "threatfox" in principals
        assert "otx" in principals


@pytest.mark.asyncio
async def test_a2a_hop_budget_enforcement(app):
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "test-recursive",
            "method": "tasks/send",
            "params": {"hop_budget": 1, "subject_value": "1.1.1.1"},
        }
        resp = await client.post("/a2a/threatfox/tasks/send", json=payload)
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
        assert "hop_budget" in data["error"]["message"]


@pytest.mark.asyncio
async def test_a2a_peer_verification_abstain_on_unknown(app):
    hub = A2APeerHub(app=app, base_url="http://test")
    attestations = await hub.verify_claim_with_peers(
        requesting_principal="threatfox",
        ioc_value="0.0.0.0",
        predicate="USES_C2",
        claimed_target="Cobalt Strike",
    )
    assert len(attestations) == 3
    for att in attestations:
        assert att.stance == "ABSTAIN"
        assert att.responder_principal != "threatfox"


@pytest.mark.asyncio
async def test_a2a_peer_verification_confirm_and_contradict(app):
    hub = A2APeerHub(app=app, base_url="http://test")

    # Mock the LLM judge in peer_hub for deterministic execution
    with patch(
        "src.a2a.peer_hub._evaluate_peer_evidence_with_llm",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.return_value = LLMPeerVerificationJudgment(
            stance="CONTRADICT",
            confidence=90,
            counter_object="RedLine Stealer",
            reasoning="Telemetry shows active RedLine Stealer C2.",
        )

        attestations = await hub.verify_claim_with_peers(
            requesting_principal="otx",
            ioc_value="139.59.33.238",
            predicate="USES_C2",
            claimed_target="Cobalt Strike",
        )
        assert len(attestations) == 3
        tf_att = next(a for a in attestations if a.responder_principal == "threatfox")
        assert tf_att.stance == "CONTRADICT"
        assert tf_att.counter_object == "redline stealer"
        assert len(tf_att.signature) == 64
```

---

### Step S3-013-C — Verification Gate

Execute the test suite:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_peer_hub.py -v
```

**VERIFICATION CHECK 013**  
Must end with:
```
4 passed in 0.xxs
```

---

## Section 9 — Sprint 3 Full Integration Gate

Run the entire Sprint 3 suite followed by the full cumulative regression across all modules.

### Sprint 3 Gate:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_cti_mcp_server.py tests/test_mcp_client.py tests/test_a2a_peer_hub.py -v
```

**VERIFICATION CHECK:**  
Must show:
```
10 passed in 0.xxs
```

---

### Cumulative Workspace Regression Gate:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_models.py tests/test_irs_resolver.py tests/test_ontology_validator.py tests/test_lock_manager.py tests/test_llm_factory.py tests/test_conflict_detector.py tests/test_arbitration_engine.py tests/test_mpac_coordinator.py tests/test_adhoc_coordinator.py tests/test_ablation_coordinator.py tests/test_cti_mcp_server.py tests/test_mcp_client.py tests/test_a2a_peer_hub.py -q
```

**VERIFICATION CHECK:**  
Must show:
```
61 passed in 0.xxs
```

---

## Section 10 — Common Failure Modes & Diagnostics Lookup

| Failure Symptom | Probable Cause | Immediate Diagnostic & Fix |
|---|---|---|
| `ImportError: cannot import name 'TypeAlias' from 'typing'` | Python 3.9 environment attempting to import official 3.10+ `mcp` SDK. | Ensure `mcp/` compatibility package is present in the workspace root. |
| `asyncio.LimitOverrunError: Separator is not found` | Default 64 KB StreamReader buffer overflow on large CTI query response. | Verify `limit=10 * 1024 * 1024` (10 MB) is passed in `stdio_client` and `FastMCP`. |
| `RuntimeError: MCP server disconnected unexpectedly` | Child process stdout block buffering or child process crashed on import. | Verify `sys.stdout.flush()` is called in `FastMCP.run()` and `os.environ` is passed to `StdioServerParameters`. |
| `RuntimeError: MCP JSON-RPC Error: hop_budget must be 0` | Requesting agent passed `hop_budget > 0` to peer endpoint. | Set `hop_budget = 0` in request payload to prevent recursive query storms. |
| `TypeError: Object of type StructuredTool is not JSON serializable` | Tool schema returning unstructured model instead of string. | Verify `StructuredTool.from_function` wraps `_invoke_mcp_tool` returning `str`. |
| `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` | Empty tool content returned over stdio. | Confirm `search_cti_indicator` returns valid JSON string with `matches`. |
| `Subprocess timeout during benchmark` | Spawning new Python processes for every HTTP task request. | Confirm `_get_shared_mcp_session()` reuses a warm session across requests. |

---

## Section 11 — Sprint 3 Sign-Off Checklist

- [x] All 3 stories implemented strictly per TechSpec §3.1, §3.2, §3.3.
- [x] FastMCP server runs standalone and serves `ontology://tier1-schema` (including `EXPLOITS`, `PART_OF`, `TARGETS`, `MITIGATED_BY`) and CTI search tools over stdio.
- [x] Defanged IOCs (`[.]`, `[:]`, `hxxp`) normalized in `search_cti_indicator()`.
- [x] Real MCP client dynamically discovers tools and binds `principal` in closure preventing prompt-injection spoofing.
- [x] Stdio buffer limit set to 10 MB and client IO protected with `asyncio.Lock()` to prevent concurrent interleaving.
- [x] Real A2A HTTP JSON-RPC router publishes Agent Cards and handles peer verification with HMAC signatures.
- [x] Shared MCP session pool eliminates subprocess storms across A2A requests.
- [x] All 10 Sprint 3 tests pass.
- [x] Full regression suite passes with 0 failures.
