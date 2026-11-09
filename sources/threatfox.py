import os
import httpx
from typing import List, Dict, Any
from sources.base import BaseCTISource
from schemas.cti import NormalizedCTIRecord


class ThreatFoxSource(BaseCTISource):
    """
    ThreatFox Official Live Export Feed Connector & Normalizer
    Export Feed: https://threatfox.abuse.ch/export/json/recent/
    Updated daily with thousands of active Indicators of Compromise.
    """

    @property
    def name(self) -> str:
        return "ThreatFox"

    def fetch_raw(self, limit: int = 1000) -> List[Dict[str, Any]]:
        export_url = "https://threatfox.abuse.ch/export/json/recent/"
        headers = {"User-Agent": "ProGRESS-CTI-Research/1.0"}

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(export_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_list = []
                    if isinstance(data, dict):
                        for ioc_id, items in data.items():
                            if isinstance(items, list):
                                for item in items:
                                    item["id"] = ioc_id
                                    item["ioc"] = item.get("ioc_value") or item.get("ioc")
                                    raw_list.append(item)
                            elif isinstance(items, dict):
                                items["id"] = ioc_id
                                items["ioc"] = items.get("ioc_value") or items.get("ioc")
                                raw_list.append(items)
                    elif isinstance(data, list):
                        raw_list = data

                    if raw_list:
                        return raw_list[:limit] if limit > 0 else raw_list
        except Exception as e:
            print(f"[ThreatFox] Bulk feed fetch failed: {e}. Checking fixture...")

        fixture_path = os.path.join("data", "fixtures", "threatfox.json")
        return self.load_raw(fixture_path)

    def normalize_record(self, raw: Dict[str, Any]) -> List[NormalizedCTIRecord]:
        record_id = str(raw.get("id", ""))
        raw_ioc = raw.get("ioc_value") or raw.get("ioc") or ""
        ioc_type_raw = str(raw.get("ioc_type", "")).lower()

        if not raw_ioc:
            return []

        # Parse IOC Type & Value
        if "ip" in ioc_type_raw:
            ioc_type = "ip"
            ioc_value = raw_ioc.split(":")[0]  # Strip port if present
        elif "domain" in ioc_type_raw:
            ioc_type = "domain"
            ioc_value = raw_ioc
        elif "url" in ioc_type_raw:
            ioc_type = "url"
            ioc_value = raw_ioc
        elif "sha256" in ioc_type_raw:
            ioc_type = "hash_sha256"
            ioc_value = raw_ioc
        elif "md5" in ioc_type_raw:
            ioc_type = "hash_md5"
            ioc_value = raw_ioc
        else:
            ioc_type = ioc_type_raw or "unknown"
            ioc_value = raw_ioc

        malware = raw.get("malware_printable") or raw.get("malware")
        confidence = raw.get("confidence_level")
        if isinstance(confidence, str) and confidence.isdigit():
            confidence = int(confidence)
        elif not isinstance(confidence, int):
            confidence = None

        timestamp = raw.get("first_seen_utc") or raw.get("first_seen") or ""
        
        # Tags parsing
        tags_raw = raw.get("tags")
        if isinstance(tags_raw, list):
            tags = tags_raw
        elif isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags = []

        # Aliases parsing
        aliases_raw = raw.get("malware_alias")
        if isinstance(aliases_raw, str):
            aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        elif isinstance(aliases_raw, list):
            aliases = aliases_raw
        else:
            aliases = []

        threat_type = raw.get("threat_type")
        reference_url = raw.get("reference")

        return [
            NormalizedCTIRecord(
                source=self.name,
                record_id=record_id,
                timestamp=timestamp,
                ioc_type=ioc_type,
                ioc_value=ioc_value.strip().lower() if ioc_type in ["domain", "hash_sha256", "hash_md5"] else ioc_value.strip(),
                malware_family=malware,
                threat_actor=None,
                confidence=confidence,
                reporter=raw.get("reporter"),
                tags=tags,
                threat_type=threat_type,
                status="active",
                reference_url=reference_url,
                campaign=None,
                attack_ids=[],
                aliases=aliases,
                raw_data=raw
            )
        ]
