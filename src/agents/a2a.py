# src/agents/a2a.py
"""G²CP Agent-to-Agent Peer Hub — Story 009.

Implements the peer consensus query layer of the G²CP protocol.
When an agent has a claim about an IOC, it broadcasts a query to all
other agents (peers) and aggregates their votes into a consensus score.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

from src.mcp.tools import MCP_TOOLS
from src.schemas.models import A2AResponse

logger = logging.getLogger(__name__)

# All known principal IDs in the system (one per data source)
ALL_PRINCIPALS: List[str] = [
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
        - ABSTAIN:   peer found no records for this IOC
        - CONFIRM:   peer found the IOC AND malware families match
                     (or neither the claim nor the peer has a malware family)
        - CONTRADICT: peer found the IOC AND malware families differ
        """
        tool = MCP_TOOLS.get(peer_id)
        if tool is None:
            logger.warning("No MCP tool found for peer %s — ABSTAIN", peer_id)
            return A2AResponse(peer_id=peer_id, vote="ABSTAIN")

        # The source-file lookup is synchronous; run it off-loop so the peer
        # timeout actually bounds slow disk reads/large-snapshot scans.
        response = await asyncio.to_thread(tool.invoke, ioc_value)

        if not response.records:
            # Peer has no data on this IOC
            return A2AResponse(
                peer_id=peer_id,
                vote="ABSTAIN",
                evidence_summary="No records found",
            )

        # Peer found at least one record — decide vote based on malware family
        peer_record = response.records[0]
        peer_malware = peer_record.get("malware_family")
        peer_confidence = peer_record.get("confidence")

        if claim_malware_family and peer_malware:
            # Both sides have a malware family — compare them
            if peer_malware.strip().lower() == claim_malware_family.strip().lower():
                vote = "CONFIRM"
            else:
                vote = "CONTRADICT"
        else:
            # An IOC match without comparable attribution is insufficient to
            # confirm or contradict the requesting agent's family claim.
            return A2AResponse(
                peer_id=peer_id,
                vote="ABSTAIN",
                evidence_summary="IOC found but malware-family attribution is missing",
                confidence=peer_confidence,
            )

        summary = f"{peer_id} found {len(response.records)} record(s); malware_family={peer_malware}"
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
        """Wrapper that enforces the 350 ms timeout on a single peer query.

        If the underlying call takes longer than PEER_TIMEOUT_SECONDS,
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
    def _compute_consensus_score(responses: List[A2AResponse]) -> float:
        """Compute normalised consensus score in [0.0, 1.0].

        Formula: (V_confirm - V_contradict + N_peers) / (2 * N_peers)
        Edge case: if N_peers == 0 (no peers queried), return 0.5 (neutral).
        """
        n_peers = len(responses)
        if n_peers == 0:
            return 0.5
        v_confirm = sum(1 for r in responses if r.vote == "CONFIRM")
        v_contradict = sum(1 for r in responses if r.vote == "CONTRADICT")
        score = (v_confirm - v_contradict + n_peers) / (2 * n_peers)
        return max(0.0, min(1.0, score))

    async def query_peers(
        self,
        ioc_value: str,
        requesting_agent_id: str,
        claim_malware_family: str | None = None,
    ) -> Tuple[List[A2AResponse], float]:
        """Broadcast an IOC query to all peers except the requesting agent.

        Queries all peers CONCURRENTLY. Each peer has 350 ms to respond.
        Slow or unresponsive peers automatically vote ABSTAIN.
        """
        peer_ids = [p for p in ALL_PRINCIPALS if p != requesting_agent_id]
        logger.info(
            "A2A query from %s for IOC '%s' → querying %d peers",
            requesting_agent_id,
            ioc_value,
            len(peer_ids),
        )

        tasks = [self._safe_peer_query(pid, ioc_value, claim_malware_family) for pid in peer_ids]
        responses: List[A2AResponse] = list(await asyncio.gather(*tasks))
        score = self._compute_consensus_score(responses)
        logger.info(
            "A2A result for '%s': votes=%s score=%.3f",
            ioc_value,
            [r.vote for r in responses],
            score,
        )
        return responses, score
