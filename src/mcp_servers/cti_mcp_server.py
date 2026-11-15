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

