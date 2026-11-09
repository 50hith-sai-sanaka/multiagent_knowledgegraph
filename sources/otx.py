import os
import httpx
from typing import List, Dict, Any
from sources.base import BaseCTISource
from schemas.cti import NormalizedCTIRecord


class OTXSource(BaseCTISource):
    """
    AlienVault OTX API Connector & Normalizer
    API Base: https://otx.alienvault.com/api/v1/
    Fetches real-time pulses containing threat actor campaigns, MITRE ATT&CK IDs, and IOCs.
    """

    @property
    def name(self) -> str:
        return "OTX"

    def fetch_raw(self, limit: int = 100) -> List[Dict[str, Any]]:
        headers = {}
        otx_key = os.getenv("OTX_API_KEY")
        if otx_key:
            headers["X-OTX-API-KEY"] = otx_key

        all_pulses = []
        page_size = min(limit, 50)
        url = f"https://otx.alienvault.com/api/v1/pulses/subscribed?limit={page_size}"

        try:
            with httpx.Client(timeout=45.0) as client:
                while url and len(all_pulses) < limit:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        if not results:
                            break
                        all_pulses.extend(results)
                        url = data.get("next")
                    else:
                        if not all_pulses:
                            alt_url = f"https://otx.alienvault.com/api/v1/pulses/activity?limit={page_size}"
                            resp_alt = client.get(alt_url, headers=headers)
                            if resp_alt.status_code == 200:
                                all_pulses = resp_alt.json().get("results", [])
                        break

                if all_pulses:
                    return all_pulses[:limit]
        except Exception as e:
            print(f"[OTX] API Request failed: {e}. Checking fixture...")

        fixture_path = os.path.join("data", "fixtures", "otx.json")
        return self.load_raw(fixture_path)

    def normalize_record(self, raw: Dict[str, Any]) -> List[NormalizedCTIRecord]:
        records = []
        pulse_id = str(raw.get("id", ""))
        pulse_name = raw.get("name", "")
        author = raw.get("author_name")
        created = raw.get("created") or raw.get("modified") or ""
        adversary = raw.get("adversary") or None
        tags = raw.get("tags") or []
        attack_ids = raw.get("attack_ids") or []
        references = raw.get("references") or []
        reference_url = references[0] if references else f"https://otx.alienvault.com/pulse/{pulse_id}"

        # Malware families & aliases from pulse
        malware_families_raw = raw.get("malware_families") or []
        aliases = []
        if isinstance(malware_families_raw, list):
            aliases = [m.get("display_name", "") for m in malware_families_raw if isinstance(m, dict)]
        
        # Derive malware family
        malware_family = None
        if adversary:
            malware_family = adversary
        elif aliases:
            malware_family = aliases[0]
        else:
            for tag in tags:
                if tag.lower() not in ["c2", "ioc", "phishing", "malware", "ipv4", "domain", "url"]:
                    malware_family = tag
                    break

        indicators = raw.get("indicators", [])
        for ind in indicators:
            ind_id = str(ind.get("id", ""))
            ind_value = ind.get("indicator", "")
            ind_type_raw = str(ind.get("type", "")).lower()
            description = ind.get("description")

            if not ind_value:
                continue

            # Standardize IOC Type
            if "ipv4" in ind_type_raw or "ip" in ind_type_raw:
                ioc_type = "ip"
                clean_val = ind_value.strip()
            elif "domain" in ind_type_raw or "hostname" in ind_type_raw:
                ioc_type = "domain"
                clean_val = ind_value.strip().lower()
            elif "url" in ind_type_raw:
                ioc_type = "url"
                clean_val = ind_value.strip()
            elif "sha256" in ind_type_raw:
                ioc_type = "hash_sha256"
                clean_val = ind_value.strip().lower()
            elif "md5" in ind_type_raw:
                ioc_type = "hash_md5"
                clean_val = ind_value.strip().lower()
            else:
                ioc_type = ind_type_raw or "unknown"
                clean_val = ind_value.strip()

            records.append(
                NormalizedCTIRecord(
                    source=self.name,
                    record_id=f"{pulse_id}-{ind_id}",
                    timestamp=created,
                    ioc_type=ioc_type,
                    ioc_value=clean_val,
                    malware_family=malware_family,
                    threat_actor=adversary,
                    confidence=80,
                    reporter=author,
                    tags=tags,
                    threat_type=description or "threat_pulse_indicator",
                    status="active",
                    reference_url=reference_url,
                    campaign=pulse_name,
                    attack_ids=attack_ids,
                    aliases=aliases,
                    raw_data={"pulse_id": pulse_id, "pulse_name": pulse_name, "indicator": ind}
                )
            )

        return records
