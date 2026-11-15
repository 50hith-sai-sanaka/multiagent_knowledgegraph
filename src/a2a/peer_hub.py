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

