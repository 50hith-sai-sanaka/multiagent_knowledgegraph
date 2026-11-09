# STORY-008 – MCP Tool Adapters (4 Sources)

> **Prerequisite:** Sprint 2 Full Gate must pass — all 47 tests green — before you touch a single line here.
> Check: `PYTHONPATH=. ./venv/bin/pytest -q` → **47 passed**

---

## 🎯 What You Are Building

Right now the system has coordinators and lock managers, but agents have no way to **fetch evidence** from the CTI data sources.

This story builds four **MCP Tool Adapters** — one per data source — that read from the pre-saved normalized JSON files in `data/normalized/` and return matching records for a given IOC value.

Think of each MCP tool as a **search function**:
- You give it an IOC value (e.g. `"https://bok.6666k.org"`)
- It searches **only its own** source's JSON file
- It returns a list of matching records (or an empty list if not found)

**Why offline/JSON-based?** The real live feeds are already fetched and saved. Agents query the saved files so tests don't need internet access.

---

## 📂 Files You Will Create

```
src/
└── mcp/
    ├── __init__.py           ← NEW (empty, marks it a package)
    ├── base_tool.py          ← NEW (abstract base class + MCPResponse)
    ├── threatfox_tool.py     ← NEW (searches threatfox.json)
    ├── urlhaus_tool.py       ← NEW (searches urlhaus.json)
    ├── malwarebazaar_tool.py ← NEW (searches malwarebazaar.json)
    ├── otx_tool.py           ← NEW (searches otx.json)
    └── tools.py              ← NEW (registry dict: principal_id → tool instance)
tests/
└── test_mcp_tools.py         ← NEW
```

**No existing files are modified.**

---

## 🧠 Key Concepts (Read This First)

### What is an MCP Tool?
An MCP tool is a Python class with an `invoke(ioc_value)` method. When an agent wants evidence for an IOC, it calls `tool.invoke("some-ip-or-hash")` and gets back an `MCPResponse`.

### What is an MCPResponse?
A dataclass with two fields:
- `source` — name of the data source (e.g. `"ThreatFox"`)
- `records` — list of matching record dicts. Empty list = nothing found.

### Principal Isolation
Each of the 4 agents is bound to exactly one source:

| Principal (Agent ID) | Data Source | JSON File |
|---|---|---|
| `"Principal-ThreatFox"` | ThreatFox | `data/normalized/threatfox.json` |
| `"Principal-URLhaus"` | URLhaus | `data/normalized/urlhaus.json` |
| `"Principal-MalwareBazaar"` | MalwareBazaar | `data/normalized/malwarebazaar.json` |
| `"Principal-OTX"` | OTX | `data/normalized/otx.json` |

An agent **must never** see another source's records. This is enforced because each tool only reads its own JSON file.

### What does the JSON look like?
Each JSON file is a list of records. A sample ThreatFox record:
```json
{
  "source": "ThreatFox",
  "record_id": "1961371",
  "timestamp": "2026-10-12 07:08:44",
  "ioc_type": "url",
  "ioc_value": "https://bok.6666k.org",
  "malware_family": "Vidar",
  "confidence": 100,
  "threat_type": "botnet_cc",
  "status": "active"
}
```
Matching is done by comparing `ioc_value` (case-insensitive, stripped of whitespace).

---

## 🛠️ Step-by-Step Implementation

### Step 1 — Create the package directory

```bash
mkdir -p src/mcp
touch src/mcp/__init__.py
```

The `__init__.py` stays **empty**. It just tells Python that `src/mcp/` is a package.

---

### Step 2 — Create `src/mcp/base_tool.py`

```python
# src/mcp/base_tool.py
"""
MCP Tool Base Class — Story 008

Defines the contract that every MCP tool must implement.
All 4 source tools inherit this class.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPResponse:
    """Standard return type for every MCP tool.

    Attributes
    ----------
    source  : Name of the data source (e.g. "ThreatFox").
    records : Matching record dicts. Empty list = no match.
    """
    source: str
    records: list[dict[str, Any]] = field(default_factory=list)


class BaseMCPTool(ABC):
    """Abstract base class for all MCP tool adapters.

    Subclasses must implement:
      - source_name  → display name (e.g. "ThreatFox")
      - data_file    → Path to the normalized JSON file
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the source name, e.g. 'ThreatFox'."""
        ...

    @property
    @abstractmethod
    def data_file(self) -> Path:
        """Return the Path to the normalized JSON file for this source."""
        ...

    def _load_records(self) -> list[dict[str, Any]]:
        """Load and cache all records from the JSON file.

        The file is read once and cached on the instance.
        Subsequent calls return the cached list immediately.
        """
        if not hasattr(self, "_cache"):
            path = self.data_file
            if not path.exists():
                logger.warning("MCP data file not found: %s", path)
                self._cache: list[dict[str, Any]] = []
            else:
                with path.open(encoding="utf-8") as fh:
                    self._cache = json.load(fh)
                logger.debug("Loaded %d records from %s", len(self._cache), path)
        return self._cache

    def invoke(self, ioc_value: str) -> MCPResponse:
        """Search this source for records matching ioc_value.

        Matching is case-insensitive and whitespace-stripped on the
        'ioc_value' field of each record.

        Parameters
        ----------
        ioc_value : The indicator to search (e.g. "185.220.101.34").

        Returns
        -------
        MCPResponse — records is [] if nothing matches. Never raises.
        """
        needle = ioc_value.strip().lower()
        matches = [
            r for r in self._load_records()
            if str(r.get("ioc_value", "")).strip().lower() == needle
        ]
        logger.debug("%s: %d match(es) for '%s'", self.source_name, len(matches), ioc_value)
        return MCPResponse(source=self.source_name, records=matches)
```

---

### Step 3 — Create the four source tools

Each tool is ~12 lines. It only declares `source_name` and `data_file` — everything else is inherited from `BaseMCPTool`.

**`src/mcp/threatfox_tool.py`**
```python
# src/mcp/threatfox_tool.py
from __future__ import annotations
from pathlib import Path
from src.mcp.base_tool import BaseMCPTool


class ThreatFoxMCPTool(BaseMCPTool):
    """Searches data/normalized/threatfox.json for a given IOC."""

    @property
    def source_name(self) -> str:
        return "ThreatFox"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/threatfox.json")
```

**`src/mcp/urlhaus_tool.py`**
```python
# src/mcp/urlhaus_tool.py
from __future__ import annotations
from pathlib import Path
from src.mcp.base_tool import BaseMCPTool


class URLhausMCPTool(BaseMCPTool):
    """Searches data/normalized/urlhaus.json for a given IOC."""

    @property
    def source_name(self) -> str:
        return "URLhaus"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/urlhaus.json")
```

**`src/mcp/malwarebazaar_tool.py`**
```python
# src/mcp/malwarebazaar_tool.py
from __future__ import annotations
from pathlib import Path
from src.mcp.base_tool import BaseMCPTool


class MalwareBazaarMCPTool(BaseMCPTool):
    """Searches data/normalized/malwarebazaar.json for a given IOC."""

    @property
    def source_name(self) -> str:
        return "MalwareBazaar"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/malwarebazaar.json")
```

**`src/mcp/otx_tool.py`**
```python
# src/mcp/otx_tool.py
from __future__ import annotations
from pathlib import Path
from src.mcp.base_tool import BaseMCPTool


class OTXMCPTool(BaseMCPTool):
    """Searches data/normalized/otx.json for a given IOC."""

    @property
    def source_name(self) -> str:
        return "OTX"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/otx.json")
```

---

### Step 4 — Create `src/mcp/tools.py` (the registry)

This maps agent principal ID → tool instance. Stories 009 and 010 import this.

```python
# src/mcp/tools.py
"""
MCP Tool Registry — Story 008.

Maps each principal (agent) ID to its exclusive MCP tool instance.

Usage:
    from src.mcp.tools import MCP_TOOLS
    tool = MCP_TOOLS["Principal-ThreatFox"]
    response = tool.invoke("https://bok.6666k.org")
    print(response.records)   # list of matching dicts
"""
from __future__ import annotations

from src.mcp.malwarebazaar_tool import MalwareBazaarMCPTool
from src.mcp.otx_tool import OTXMCPTool
from src.mcp.threatfox_tool import ThreatFoxMCPTool
from src.mcp.urlhaus_tool import URLhausMCPTool

MCP_TOOLS: dict[str, object] = {
    "Principal-ThreatFox":     ThreatFoxMCPTool(),
    "Principal-URLhaus":       URLhausMCPTool(),
    "Principal-MalwareBazaar": MalwareBazaarMCPTool(),
    "Principal-OTX":           OTXMCPTool(),
}

__all__ = ["MCP_TOOLS"]
```

---

### Step 5 — Write `tests/test_mcp_tools.py`

```python
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
# Each tool returns ONLY its own source's records, even if the IOC exists
# in multiple sources.
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
```

---

## ✅ Gate — Run and Verify

```bash
# Run only Story 008 tests
PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_tools.py -v
```

Expected output:
```
tests/test_mcp_tools.py::test_threatfox_tool_finds_known_ioc       PASSED
tests/test_mcp_tools.py::test_urlhaus_tool_finds_known_ioc         PASSED
tests/test_mcp_tools.py::test_malwarebazaar_tool_finds_known_ioc   PASSED
tests/test_mcp_tools.py::test_otx_tool_finds_known_ioc             PASSED
tests/test_mcp_tools.py::test_unknown_ioc_returns_empty_list       PASSED
tests/test_mcp_tools.py::test_cross_source_isolation               PASSED
tests/test_mcp_tools.py::test_registry_contains_all_principals     PASSED
tests/test_mcp_tools.py::test_registry_returns_correct_tool_type   PASSED
tests/test_mcp_tools.py::test_registry_tool_can_invoke             PASSED

9 passed
```

```bash
# Then verify no regressions in the full suite
PYTHONPATH=. ./venv/bin/pytest -q
# → 56 passed  (47 existing + 9 new)
```

---

## 🔎 Checklist Before Moving to Story 009

- [ ] `src/mcp/__init__.py` — empty file exists
- [ ] `src/mcp/base_tool.py` — `MCPResponse` dataclass + `BaseMCPTool` abstract class
- [ ] `src/mcp/threatfox_tool.py` — `ThreatFoxMCPTool`
- [ ] `src/mcp/urlhaus_tool.py` — `URLhausMCPTool`
- [ ] `src/mcp/malwarebazaar_tool.py` — `MalwareBazaarMCPTool`
- [ ] `src/mcp/otx_tool.py` — `OTXMCPTool`
- [ ] `src/mcp/tools.py` — `MCP_TOOLS` dict with all 4 principals
- [ ] `tests/test_mcp_tools.py` — 9 tests, all PASS
- [ ] Full suite: **56 passed**

---

## ⚠️ Common Mistakes

| Mistake | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'src.mcp'` | Run with `PYTHONPATH=.` and confirm `src/mcp/__init__.py` exists |
| `FileNotFoundError` on JSON | Always run pytest from the project root (`multiagent_knowledgegraph/`), not from inside `src/` |
| Test fails — IOC not found | The `_first_ioc()` helper always returns a real IOC from the file — double check the JSON path is correct |
| Cross-source isolation test fails | The test only checks that **returned** records have the right `source` field — two sources CAN share the same IOC value |
| `AttributeError: '_cache'` | `_load_records()` uses `hasattr(self, "_cache")` — make sure you didn't rename it |
