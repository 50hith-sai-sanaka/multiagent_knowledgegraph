from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NormalizedCTIRecord(BaseModel):
    """
    Standardized, Provenance-Aware CTI Record representation across all ingestion sources.
    Incorporates domain threat intelligence, operational status, and attribution metadata.
    """
    source: str = Field(..., description="Source name: ThreatFox, URLhaus, MalwareBazaar, or OTX")
    record_id: str = Field(..., description="Unique ID of record from original source")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp string")
    ioc_type: str = Field(..., description="Standardized IOC type: ip, domain, url, hash_sha256, hash_md5")
    ioc_value: str = Field(..., description="The indicator value (e.g., 185.x.x.x, example.com, hash)")
    malware_family: Optional[str] = Field(None, description="Malware family name if identified (e.g., RedLine)")
    threat_actor: Optional[str] = Field(None, description="Threat actor / adversary name if identified")
    confidence: Optional[int] = Field(None, description="Confidence score standardized to 0-100 scale")
    reporter: Optional[str] = Field(None, description="Reporter or pulse author (principal proxy)")
    tags: List[str] = Field(default_factory=list, description="Associated tags or classifications")

    # --- Enhanced CTI & Provenance Fields ---
    threat_type: Optional[str] = Field(None, description="Nature of threat: botnet_cc, payload_delivery, phishing, etc.")
    status: Optional[str] = Field(None, description="Operational state: online, offline, active")
    reference_url: Optional[str] = Field(None, description="Direct URL to external research whitepaper or evidence link")
    campaign: Optional[str] = Field(None, description="Associated threat campaign or pulse name")
    attack_ids: List[str] = Field(default_factory=list, description="Associated MITRE ATT&CK technique IDs (e.g., T1071.001)")
    aliases: List[str] = Field(default_factory=list, description="Known aliases for the malware family or threat actor")

    raw_data: Dict[str, Any] = Field(..., description="Complete untouched raw API response")


class IOCAnalysisSummary(BaseModel):
    """
    Analysis results comparing IOCs across sources.
    """
    total_records: int
    unique_iocs: int
    cross_source_overlaps: int
    potential_conflicts: int
