"""
Identity Resolution Service (IRS) & Deterministic Keying
File: src/irs/resolver.py
Sprint: Sprint 1 (STORY-002)

Provides:
  - IOC canonicalization (IP, Domain, URL, Hash)
  - Malware synonym normalization (Heodo -> emotet, RedLine -> redline stealer) aligned with Malpedia taxonomy
  - Deterministic lexicographical mutex lock key construction
  - Operation canonicalization
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from src.schemas.models import GraphOperation

MALWARE_ALIASES: Dict[str, str] = {
    # Emotet family
    "heodo": "emotet",
    "geodo": "emotet",
    "emotet": "emotet",
    # RedLine family
    "redline": "redline stealer",
    "redlinestealer": "redline stealer",
    "redline stealer": "redline stealer",
    # QakBot family
    "qakbot": "qbot",
    "quakbot": "qbot",
    "qbot": "qbot",
    # Cobalt Strike
    "cobalt strike": "cobalt strike",
    "cobaltstrike": "cobalt strike",
    # Agent Tesla
    "agent tesla": "agent tesla",
    "agenttesla": "agent tesla",
    # AsyncRAT
    "asyncrat": "asyncrat",
    # Remcos
    "remcos": "remcos",
    "remcosrat": "remcos",
}


class IdentityResolutionService:
    """Canonicalizes IOC values, resolves threat entity synonyms, and builds mutex lock keys."""

    def __init__(self, alias_map: Optional[Dict[str, str]] = None):
        self._alias_map = alias_map or MALWARE_ALIASES

    def canonicalize_ioc(self, ioc_type: str, raw_value: str) -> str:
        """Strip whitespace, defang brackets, normalize schemes, and handle IPv4/IPv6."""
        t = ioc_type.strip().lower()

        if t in ("ip", "ipv4", "ipv6", "ip:port"):
            val = str(raw_value).strip().lower()
            val = val.replace("[.]", ".").replace("[at]", "@")
            # Strip port only if single colon in IPv4 (e.g. 1.2.3.4:8080) or bracketed IPv6 ([2001:db8::1]:80)
            if val.count(":") == 1 and "." in val:
                val = val.split(":")[0]
            elif val.startswith("[") and "]:" in val:
                val = val.split("]:")[0].lstrip("[")
            elif val.startswith("[") and val.endswith("]"):
                val = val[1:-1]
            return val.strip()

        if t in ("domain", "hostname"):
            val = str(raw_value).strip().lower()
            val = val.replace("[.]", ".").replace("[at]", "@")
            return val.rstrip(".")

        if t == "url":
            # RFC 3986: Scheme and hostname are lowercase; path and query case is preserved
            val_url = str(raw_value).strip()
            val_url = val_url.replace("[.]", ".").replace("[at]", "@")
            val_url = re.sub(
                r"^hxxps?://",
                lambda m: "https://" if "s" in m.group(0).lower() else "http://",
                val_url,
                flags=re.IGNORECASE,
            )
            if not re.match(r"^[a-zA-Z]+://", val_url):
                val_url = "http://" + val_url
            parsed = urlparse(val_url)
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip("/")
            query = f"?{parsed.query}" if parsed.query else ""
            return f"{parsed.scheme.lower()}://{netloc}{path}{query}"

        if t in ("filehash", "hash", "sha256", "md5"):
            return str(raw_value).strip().lower()

        val = str(raw_value).strip().lower()
        val = val.replace("[.]", ".").replace("[at]", "@")
        return val.strip()

    def canonicalize_target(self, target_label: str, raw_target: str) -> str:
        """Normalize target entities using domain alias maps with punctuation and whitespace collapsing."""
        val = str(raw_target).strip().lower()
        if target_label.strip().lower() in ("malware", "threatfamily"):
            clean_name = re.sub(r"[^a-z0-9]+", " ", val).strip()
            clean_name = re.sub(r"\s+", " ", clean_name)
            return self._alias_map.get(clean_name, self._alias_map.get(val, clean_name))
        return val

    def build_lock_keys(
        self,
        subject_label: str,
        subject_value: str,
        predicate: Optional[str] = None,
        is_functional: bool = False,
    ) -> List[str]:
        """
        Builds deterministic mutex keys in strict lexicographical order.

        1. Entity Lock: entity:{label}:{canon_val}
        2. Slot Lock (if predicate and is_functional): slot:{label}:{canon_val}:{predicate}
        """
        sub_type = subject_label.strip().lower()
        canon_val = self.canonicalize_ioc(sub_type, subject_value)

        entity_key = f"entity:{sub_type}:{canon_val}"
        keys = [entity_key]

        if predicate and is_functional:
            pred = predicate.strip().upper()
            slot_key = f"slot:{sub_type}:{canon_val}:{pred.lower()}"
            keys.append(slot_key)

        return sorted(keys)

    def canonicalize_operation(self, op: GraphOperation) -> GraphOperation:
        """Returns a new GraphOperation with canonicalized subject, target, and lock keys."""
        canon_sub = self.canonicalize_ioc(op.node_label, op.node_value)
        canon_tgt = self.canonicalize_target(op.target_label, op.target_value) if op.target_value else ""

        new_keys = self.build_lock_keys(
            subject_label=op.node_label,
            subject_value=canon_sub,
            predicate=op.predicate if op.predicate else None,
            is_functional=op.is_functional,
        )

        return op.model_copy(
            update={
                "node_value": canon_sub,
                "target_value": canon_tgt,
                "lock_keys": new_keys,
            }
        )

