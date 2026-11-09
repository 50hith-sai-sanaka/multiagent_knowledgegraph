import json
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from schemas.cti import NormalizedCTIRecord
from src.utils.time import normalize_timestamp

class BaseCTISource(ABC):
    """
    Abstract base class for all CTI Source fetchers and normalizers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the source (e.g. ThreatFox, URLhaus, MalwareBazaar, OTX)"""
        pass

    @abstractmethod
    def fetch_raw(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch raw JSON records from the live API (or fallback to fixture)"""
        pass

    @abstractmethod
    def normalize_record(self, raw_record: Dict[str, Any]) -> List[NormalizedCTIRecord]:
        """Convert a single raw JSON dict into normalized CTI records (may return >1 if multi-IOC)"""
        pass

    def normalize(self, raw_records: List[Dict[str, Any]]) -> List[NormalizedCTIRecord]:
        """Normalize a list of raw records"""
        normalized_list = []
        for raw in raw_records:
            try:
                records = self.normalize_record(raw)
                for record in records:
                    if record.timestamp:
                        try:
                            record.timestamp = normalize_timestamp(record.timestamp)[0]
                        except ValueError:
                            # Keep the original source timestamp for forensic review.
                            pass
                normalized_list.extend(records)
            except Exception as e:
                # Log normalization warning and skip corrupted record
                print(f"[{self.name}] Warning normalizing record: {e}")
        return normalized_list

    def save_raw(self, raw_records: List[Dict[str, Any]], filepath: str) -> None:
        """Save raw records to JSON file"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(raw_records, f, indent=2, ensure_ascii=False)

    def load_raw(self, filepath: str) -> List[Dict[str, Any]]:
        """Load raw records from JSON file"""
        if not os.path.exists(filepath):
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
