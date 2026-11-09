# STORY-009 – G²CP Agent-to-Agent (A2A) Peer Hub

> **Prerequisite:** STORY-008 Gate must pass first.
> Check: `PYTHONPATH=. ./venv/bin/pytest tests/test_mcp_tools.py -q` → **9 passed**
> Full suite: `PYTHONPATH=. ./venv/bin/pytest -q` → **56 passed**

---

## 🎯 What You Are Building

When an agent finds an IOC in its own data source, it needs to **ask the other 3 agents** whether they can corroborate or contradict that finding. This is the **G²CP Peer Hub** — the Agent-to-Agent (A2A) consensus layer.

The flow looks like this:
1. `Principal-ThreatFox` finds IOC `https://bok.6666k.org` tagged as `Vidar`
2. It asks `Principal-URLhaus`, `Principal-MalwareBazaar`, and `Principal-OTX`: *"Have you seen this IOC?"*
3. Each peer checks its own data and replies with a **vote**:
   - `CONFIRM` — I see this IOC with **matching** malware family
   - `CONTRADICT` — I see this IOC but with a **different** malware family
   - `ABSTAIN` — I have no data on this IOC
4. A **consensus score** is computed from the votes (a float from 0.0 to 1.0)
5. The score is attached to the claim before submitting to the coordinator

This story builds the hub that orchestrates steps 2–4.

---

## 📂 Files You Will Create or Modify

```
src/
└── agents/
    ├── __init__.py    ← NEW (empty, marks it a package)
    └── a2a.py         ← NEW (the peer hub)
src/schemas/
└── models.py          ← MODIFY (add A2AResponse model + add to __all__)
tests/
└── test_a2a_hub.py    ← NEW
```

---

## 🧠 Key Concepts (Read First)

### Vote Types

| Vote | When it is given |
|---|---|
| `CONFIRM` | Peer found the same IOC **and** same malware family (or neither has a malware family) |
| `CONTRADICT` | Peer found the same IOC **but** a different malware family |
| `ABSTAIN` | Peer found nothing, OR the peer timed out (> 350 ms) |

### Consensus Score Formula

```
score = (V_confirm - V_contradict + N_peers) / (2 × N_peers)
```
- `V_confirm`    = number of CONFIRM votes
- `V_contradict` = number of CONTRADICT votes
- `N_peers`      = total number of peers queried (always 3, since there are 4 agents total)

**Worked examples:**

| Scenario | V_confirm | V_contradict | Formula | Score |
|---|---|---|---|---|
| All 3 confirm | 3 | 0 | (3 - 0 + 3) / 6 | **1.0** |
| All 3 abstain | 0 | 0 | (0 - 0 + 3) / 6 | **0.5** |
| All 3 contradict | 0 | 3 | (0 - 3 + 3) / 6 | **0.0** |
| 2 confirm, 1 contradict | 2 | 1 | (2 - 1 + 3) / 6 | **0.67** |
| 1 confirm, 1 contradict, 1 abstain | 1 | 1 | (1 - 1 + 3) / 6 | **0.5** |

The score is always in `[0.0, 1.0]`.

### Timeout
Each peer query has a **350 ms timeout** (`asyncio.wait_for`). If a peer doesn't respond in time, it automatically gets an `ABSTAIN` vote. This prevents one slow agent from stalling the entire system.

### Why asyncio?
All 3 peer queries run **simultaneously** (in parallel) using `asyncio.gather()`. Each query is wrapped with `asyncio.wait_for()` to enforce the 350 ms limit. Total worst-case wait time = 350 ms, not 3 × 350 ms.

---

## 🛠️ Step-by-Step Implementation

### Step 1 — Modify `src/schemas/models.py`

Open `src/schemas/models.py` and add the `A2AResponse` class **after the `A2AQuery` class** (around line 112), then add it to `__all__`.

Add this class:
```python
class A2AResponse(BaseModel):
    """Response from one peer agent to an A2A peer query."""

    peer_id: str                              # Which agent responded
    vote: Literal["CONFIRM", "CONTRADICT", "ABSTAIN"]
    evidence_summary: str | None = None       # Brief description of what the peer found
    confidence: int | None = None             # Peer's confidence score (0–100), if available

    model_config = ConfigDict(frozen=True, extra="forbid")
```

Then add `"A2AResponse"` to the `__all__` list at the bottom of the file.

> **Why?** The hub returns `A2AResponse` objects. Story 010 (the workflow) imports this model too.

After editing, the `__all__` list should look like:
```python
__all__ = [
    "A2AResponse",
    "A2AQuery",
    "ArbitrationDecision",
    "Claim",
    "CoordinationResult",
    "GraphOperation",
]
```

---

### Step 2 — Create `src/agents/__init__.py`

```bash
mkdir -p src/agents
touch src/agents/__init__.py
```

The file stays **empty**. It just tells Python that `src/agents/` is a package.

---

### Step 3 — Create `src/agents/a2a.py`

This is the core of Story 009. Read the comments carefully — each section maps to one of the acceptance criteria.

```python
# src/agents/a2a.py
"""
G²CP Agent-to-Agent Peer Hub — Story 009

Implements the peer consensus query layer of the G²CP protocol.
When an agent has a claim about an IOC, it broadcasts a query to all
other agents (peers) and aggregates their votes into a consensus score.

Architecture:
    Requesting agent
        └── G2CPPeerHub.query_peers(ioc_value, requesting_agent_id)
                ├── _safe_peer_query("Principal-URLhaus", ...)       ← asyncio task
                ├── _safe_peer_query("Principal-MalwareBazaar", ...) ← asyncio task
                └── _safe_peer_query("Principal-OTX", ...)           ← asyncio task
            All three run concurrently; each has a 350 ms timeout.
            Returns: list[A2AResponse] + consensus_score (float)
"""
from __future__ import annotations

import asyncio
import logging

from src.mcp.tools import MCP_TOOLS
from src.schemas.models import A2AResponse

logger = logging.getLogger(__name__)

# All known principal IDs in the system (one per data source)
ALL_PRINCIPALS: list[str] = [
    "Principal-ThreatFox",
    "Principal-URLhaus",
    "Principal-MalwareBazaar",
    "Principal-OTX",
]

# Maximum time (seconds) to wait for each peer to respond
PEER_TIMEOUT_SECONDS: float = 0.350  # 350 milliseconds


class G2CPPeerHub:
    """Manages agent-to-agent peer consensus queries.

    Usage:
        hub = G2CPPeerHub()
        votes, score = await hub.query_peers(
            ioc_value="https://bok.6666k.org",
            requesting_agent_id="Principal-ThreatFox",
            claim_malware_family="Vidar",
        )
    """

    async def _single_peer_query(
        self,
        peer_id: str,
        ioc_value: str,
        claim_malware_family: str | None,
    ) -> A2AResponse:
        """Ask one peer agent whether it can CONFIRM, CONTRADICT, or ABSTAIN.

        Vote logic:
        - ABSTAIN:     peer found no records for this IOC
        - CONFIRM:     peer found the IOC AND malware families match
                       (or neither the claim nor the peer has a malware family)
        - CONTRADICT:  peer found the IOC AND malware families differ
        """
        tool = MCP_TOOLS.get(peer_id)
        if tool is None:
            logger.warning("No MCP tool found for peer %s — ABSTAIN", peer_id)
            return A2AResponse(peer_id=peer_id, vote="ABSTAIN")

        # Query the peer's data source (synchronous file search)
        response = tool.invoke(ioc_value)

        if not response.records:
            # Peer has no data on this IOC
            return A2AResponse(
                peer_id=peer_id,
                vote="ABSTAIN",
                evidence_summary="No records found",
            )

        # Peer found at least one record — decide vote based on malware family
        peer_record     = response.records[0]
        peer_malware    = peer_record.get("malware_family")
        peer_confidence = peer_record.get("confidence")

        if claim_malware_family and peer_malware:
            # Both sides have a malware family — compare them
            if peer_malware.strip().lower() == claim_malware_family.strip().lower():
                vote = "CONFIRM"
            else:
                vote = "CONTRADICT"
        else:
            # One or both sides lack a malware family — can't contradict, treat as CONFIRM
            vote = "CONFIRM"

        summary = (
            f"{peer_id} found {len(response.records)} record(s); "
            f"malware_family={peer_malware}"
        )
        return A2AResponse(
            peer_id=peer_id,
            vote=vote,
            evidence_summary=summary,
            confidence=peer_confidence,
        )

    async def _safe_peer_query(
        self,
        peer_id: str,
        ioc_value: str,
        claim_malware_family: str | None,
    ) -> A2AResponse:
        """Wrapper that enforces the 350 ms timeout on a single peer query.

        If _single_peer_query takes longer than PEER_TIMEOUT_SECONDS,
        this returns ABSTAIN instead of waiting forever.
        """
        try:
            return await asyncio.wait_for(
                self._single_peer_query(peer_id, ioc_value, claim_malware_family),
                timeout=PEER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Peer %s timed out after 350 ms — returning ABSTAIN", peer_id)
            return A2AResponse(
                peer_id=peer_id,
                vote="ABSTAIN",
                evidence_summary="Timeout (>350 ms)",
            )

    @staticmethod
    def _compute_consensus_score(responses: list[A2AResponse]) -> float:
        """Compute normalised consensus score in [0.0, 1.0].

        Formula: (V_confirm - V_contradict + N_peers) / (2 * N_peers)

        Edge case: if N_peers == 0 (no peers queried), return 0.5 (neutral).
        """
        n_peers = len(responses)
        if n_peers == 0:
            return 0.5

        v_confirm    = sum(1 for r in responses if r.vote == "CONFIRM")
        v_contradict = sum(1 for r in responses if r.vote == "CONTRADICT")

        score = (v_confirm - v_contradict + n_peers) / (2 * n_peers)
        # Clamp to [0.0, 1.0] for safety (mathematically should already be in range)
        return max(0.0, min(1.0, score))

    async def query_peers(
        self,
        ioc_value: str,
        requesting_agent_id: str,
        claim_malware_family: str | None = None,
    ) -> tuple[list[A2AResponse], float]:
        """Broadcast an IOC query to all peers except the requesting agent.

        Queries all peers CONCURRENTLY. Each peer has 350 ms to respond.
        Slow or unresponsive peers automatically vote ABSTAIN.

        Parameters
        ----------
        ioc_value:
            The IOC string to query peers about (e.g. "https://bok.6666k.org").
        requesting_agent_id:
            The principal ID of the agent making the request. This agent is
            EXCLUDED from the peer list (agents don't query themselves).
        claim_malware_family:
            The malware family the requesting agent believes is associated
            with this IOC (e.g. "Vidar"). Used for CONFIRM/CONTRADICT logic.
            Pass None if no malware family is known.

        Returns
        -------
        tuple[list[A2AResponse], float]
            - List of A2AResponse objects (one per peer, always 3)
            - consensus_score: float in [0.0, 1.0]
        """
        # Determine which peers to query (everyone except the requesting agent)
        peer_ids = [p for p in ALL_PRINCIPALS if p != requesting_agent_id]
        logger.info(
            "A2A query from %s for IOC '%s' → querying %d peers",
            requesting_agent_id, ioc_value, len(peer_ids),
        )

        # Fire all peer queries at the same time (concurrently)
        tasks = [
            self._safe_peer_query(peer_id, ioc_value, claim_malware_family)
            for peer_id in peer_ids
        ]
        responses: list[A2AResponse] = list(await asyncio.gather(*tasks))

        # Compute the consensus score from all votes
        score = self._compute_consensus_score(responses)
        logger.info(
            "A2A result for '%s': votes=%s score=%.3f",
            ioc_value,
            [r.vote for r in responses],
            score,
        )
        return responses, score
```

---

### Step 4 — Write `tests/test_a2a_hub.py`

```python
# tests/test_a2a_hub.py
"""
Tests for G2CPPeerHub — STORY-009.

Run with:
    PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_hub.py -v
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.a2a import G2CPPeerHub
from src.mcp.base_tool import MCPResponse
from src.schemas.models import A2AResponse


# ---------------------------------------------------------------------------
# Helper — load a real IOC from a normalized data file
# ---------------------------------------------------------------------------

def _first_ioc_and_malware(json_path: str) -> tuple[str, str | None]:
    """Return (ioc_value, malware_family) for the first record in a JSON file."""
    with open(json_path, encoding="utf-8") as fh:
        records = json.load(fh)
    r = records[0]
    return r["ioc_value"], r.get("malware_family")


# ---------------------------------------------------------------------------
# Test 1 — Full consensus: 3 peers all CONFIRM
# Expected score: (3 - 0 + 3) / 6 = 1.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_consensus_all_confirm():
    """When all 3 peers find the IOC with matching malware family, score = 1.0."""
    hub = G2CPPeerHub()
    ioc, malware = _first_ioc_and_malware("data/normalized/threatfox.json")

    # Build a fake response that matches the claim's malware family
    fake_record   = {"source": "ANY", "ioc_value": ioc, "malware_family": malware, "confidence": 90}
    fake_response = MCPResponse(source="ANY", records=[fake_record])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=fake_response)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=fake_response)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=fake_response)),
    }):
        responses, score = await hub.query_peers(
            ioc_value=ioc,
            requesting_agent_id="Principal-ThreatFox",
            claim_malware_family=malware,
        )

    assert len(responses) == 3
    assert all(r.vote == "CONFIRM" for r in responses)
    assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 2 — All abstain (peers have no data on this IOC)
# Expected score: (0 - 0 + 3) / 6 = 0.5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_peers_abstain():
    """When all 3 peers have no data, votes are all ABSTAIN and score = 0.5."""
    hub            = G2CPPeerHub()
    empty_response = MCPResponse(source="ANY", records=[])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=empty_response)),
    }):
        responses, score = await hub.query_peers(
            ioc_value="unknown-ioc-xyz-999.example.com",
            requesting_agent_id="Principal-ThreatFox",
        )

    assert len(responses) == 3
    assert all(r.vote == "ABSTAIN" for r in responses)
    assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test 3 — Split vote: 1 CONFIRM, 1 CONTRADICT, 1 ABSTAIN
# Expected score: (1 - 1 + 3) / 6 = 0.5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_split_vote():
    """Mixed votes: CONFIRM + CONTRADICT + ABSTAIN → score = 0.5."""
    hub          = G2CPPeerHub()
    ioc          = "1.2.3.4"
    claim_malware = "Emotet"

    confirm_resp    = MCPResponse(source="A", records=[{"source": "A", "ioc_value": ioc, "malware_family": "Emotet", "confidence": 80}])
    contradict_resp = MCPResponse(source="B", records=[{"source": "B", "ioc_value": ioc, "malware_family": "Ryuk",   "confidence": 70}])
    empty_resp      = MCPResponse(source="C", records=[])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=confirm_resp)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=contradict_resp)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=empty_resp)),
    }):
        responses, score = await hub.query_peers(
            ioc_value=ioc,
            requesting_agent_id="Principal-ThreatFox",
            claim_malware_family=claim_malware,
        )

    votes = {r.peer_id: r.vote for r in responses}
    assert votes["Principal-URLhaus"]       == "CONFIRM"
    assert votes["Principal-MalwareBazaar"] == "CONTRADICT"
    assert votes["Principal-OTX"]           == "ABSTAIN"
    assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test 4 — Timeout: slow peer returns ABSTAIN without hanging the test
#
# IMPORTANT: We patch _single_peer_query (the inner coroutine) to sleep
# asynchronously. This is necessary because _single_peer_query calls
# tool.invoke() synchronously — a sync sleep in invoke() would block the
# event loop and prevent asyncio.wait_for from firing the timeout.
# Patching _single_peer_query directly ensures the timeout works correctly.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_returns_abstain():
    """Peers that don't respond within 350 ms receive an ABSTAIN vote."""
    hub = G2CPPeerHub()

    async def _slow_coroutine(peer_id: str, ioc_value: str, claim_malware_family):
        await asyncio.sleep(10.0)  # much longer than 350 ms — will be cancelled
        return A2AResponse(peer_id=peer_id, vote="CONFIRM")

    # Patch the inner coroutine so asyncio.wait_for can actually cancel it
    with patch.object(hub, "_single_peer_query", side_effect=_slow_coroutine):
        responses, score = await hub.query_peers(
            ioc_value="1.2.3.4",
            requesting_agent_id="Principal-ThreatFox",
        )

    assert len(responses) == 3
    assert all(r.vote == "ABSTAIN" for r in responses)
    assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test 5 — Requester is NOT included in the peer list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_requester_excluded_from_peers():
    """The requesting agent must NOT appear in the list of queried peers."""
    hub            = G2CPPeerHub()
    empty_response = MCPResponse(source="ANY", records=[])

    with patch("src.agents.a2a.MCP_TOOLS", {
        "Principal-URLhaus":       MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-MalwareBazaar": MagicMock(invoke=MagicMock(return_value=empty_response)),
        "Principal-OTX":           MagicMock(invoke=MagicMock(return_value=empty_response)),
    }):
        responses, _ = await hub.query_peers(
            ioc_value="any-ioc",
            requesting_agent_id="Principal-ThreatFox",
        )

    peer_ids = [r.peer_id for r in responses]
    assert "Principal-ThreatFox" not in peer_ids  # requester must be excluded
    assert len(peer_ids) == 3                      # always 3 peers (4 agents - 1)
```

---

## ✅ Gate — Run and Verify

```bash
# Run only Story 009 tests
PYTHONPATH=. ./venv/bin/pytest tests/test_a2a_hub.py -v
```

Expected output:
```
tests/test_a2a_hub.py::test_full_consensus_all_confirm     PASSED
tests/test_a2a_hub.py::test_all_peers_abstain              PASSED
tests/test_a2a_hub.py::test_split_vote                     PASSED
tests/test_a2a_hub.py::test_timeout_returns_abstain        PASSED
tests/test_a2a_hub.py::test_requester_excluded_from_peers  PASSED

5 passed
```

```bash
# Full suite — no regressions
PYTHONPATH=. ./venv/bin/pytest -q
# → 61 passed  (56 existing + 5 new)
```

---

## 🔎 Checklist Before Moving to Story 010

- [ ] `src/schemas/models.py` has `A2AResponse` class with `peer_id`, `vote`, `evidence_summary`, `confidence`
- [ ] `"A2AResponse"` added to `__all__` in `models.py`
- [ ] `src/agents/__init__.py` exists (empty)
- [ ] `src/agents/a2a.py` — `G2CPPeerHub` with `query_peers()`, `_single_peer_query()`, `_safe_peer_query()`, `_compute_consensus_score()`
- [ ] `tests/test_a2a_hub.py` — 5 tests, all PASS
- [ ] Full suite: **61 passed**

---

## ⚠️ Common Mistakes

| Mistake | Fix |
|---|---|
| `ModuleNotFoundError: src.agents` | Run with `PYTHONPATH=.` and confirm `src/agents/__init__.py` exists |
| Timeout test **hangs** for 10 seconds | You patched `tool.invoke` with a sync sleep — patch `_single_peer_query` instead (the inner async coroutine), as shown in Test 4 |
| Score not 0.5 when all abstain | Formula is `(0 - 0 + 3) / 6 = 0.5` — recheck your arithmetic in `_compute_consensus_score` |
| `patch("src.agents.a2a.MCP_TOOLS", ...)` has no effect | The patch path must match the import location in `a2a.py`. Since `a2a.py` does `from src.mcp.tools import MCP_TOOLS`, the correct patch target is `"src.agents.a2a.MCP_TOOLS"` |
| `A2AResponse` not found in models | Make sure you added both the class AND the entry in `__all__` |
