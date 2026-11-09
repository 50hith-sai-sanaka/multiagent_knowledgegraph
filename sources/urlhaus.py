import os
import httpx
from urllib.parse import urlparse
from typing import List, Dict, Any
from sources.base import BaseCTISource
from schemas.cti import NormalizedCTIRecord


class URLhausSource(BaseCTISource):
    """
    URLhaus Official Live Export Feed Connector & Normalizer
    Export Feed: https://urlhaus.abuse.ch/downloads/json_recent/
    Contains over 30,000 active malicious URLs updated continuously.
    """

    @property
    def name(self) -> str:
        return "URLhaus"

    def fetch_raw(self, limit: int = 1000) -> List[Dict[str, Any]]:
        export_url = "https://urlhaus.abuse.ch/downloads/json_recent/"
        headers = {"User-Agent": "ProGRESS-CTI-Research/1.0"}

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(export_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_list = []
                    if isinstance(data, dict):
                        for url_id, items in data.items():
                            if isinstance(items, list):
                                for item in items:
                                    item["id"] = url_id
                                    raw_list.append(item)
                            elif isinstance(items, dict):
                                items["id"] = url_id
                                raw_list.append(items)
                    elif isinstance(data, list):
                        raw_list = data

                    if raw_list:
                        return raw_list[:limit] if limit > 0 else raw_list
        except Exception as e:
            print(f"[URLhaus] Bulk feed fetch failed: {e}. Checking fixture...")

        fixture_path = os.path.join("data", "fixtures", "urlhaus.json")
        return self.load_raw(fixture_path)

    def normalize_record(self, raw: Dict[str, Any]) -> List[NormalizedCTIRecord]:
        records = []
        record_id = str(raw.get("id", ""))
        timestamp = raw.get("dateadded") or raw.get("date_added") or ""
        reporter = raw.get("reporter")
        threat = raw.get("threat")
        url_status = raw.get("url_status")
        reference_url = raw.get("urlhaus_link")

        tags = raw.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]

        # Extract malware family from tags or threat string
        malware_family = None
        for tag in tags:
            clean_tag = tag.lower()
            if clean_tag not in ["exe", "zip", "payload", "32-bit", "64-bit", "arm", "elf", "mips", "sh", "bin"]:
                malware_family = tag
                break
        if not malware_family and threat and threat != "malware_download":
            malware_family = threat

        main_url = raw.get("url")
        if main_url:
            # 1. Primary URL Record
            records.append(
                NormalizedCTIRecord(
                    source=self.name,
                    record_id=f"{record_id}-url",
                    timestamp=timestamp,
                    ioc_type="url",
                    ioc_value=main_url.strip(),
                    malware_family=malware_family,
                    threat_actor=None,
                    confidence=75 if url_status == "online" else 50,
                    reporter=reporter,
                    tags=tags,
                    threat_type=threat or "malware_download",
                    status=url_status or "active",
                    reference_url=reference_url,
                    campaign=None,
                    attack_ids=[],
                    aliases=[],
                    raw_data=raw
                )
            )

            # 2. Extract host IP or domain from URL
            try:
                parsed = urlparse(main_url)
                netloc = parsed.netloc.split(":")[0]  # Strip port
                if netloc:
                    is_ip = netloc.replace(".", "").isdigit()
                    ioc_type = "ip" if is_ip else "domain"
                    records.append(
                        NormalizedCTIRecord(
                            source=self.name,
                            record_id=f"{record_id}-host",
                            timestamp=timestamp,
                            ioc_type=ioc_type,
                            ioc_value=netloc.lower() if ioc_type == "domain" else netloc,
                            malware_family=malware_family,
                            threat_actor=None,
                            confidence=75 if url_status == "online" else 50,
                            reporter=reporter,
                            tags=tags,
                            threat_type=threat or "malware_distribution_host",
                            status=url_status or "active",
                            reference_url=reference_url,
                            campaign=None,
                            attack_ids=[],
                            aliases=[],
                            raw_data=raw
                        )
                    )
            except Exception:
                pass

        return records
