from typing import List, Dict, Any
from collections import defaultdict
from schemas.cti import NormalizedCTIRecord


def find_cross_source_overlaps(records: List[NormalizedCTIRecord]) -> List[Dict[str, Any]]:
    """
    Identifies IOCs that appear in more than one distinct CTI data source.
    """
    ioc_groups = defaultdict(list)

    for record in records:
        # Group key by IOC type and sanitized value
        key = (record.ioc_type, record.ioc_value.strip().lower())
        ioc_groups[key].append(record)

    overlaps = []
    for (ioc_type, ioc_value), group_records in ioc_groups.items():
        distinct_sources = set(r.source for r in group_records)
        
        # We only care if the IOC appears in 2 or more DIFFERENT sources
        if len(distinct_sources) > 1:
            overlaps.append({
                "ioc_type": ioc_type,
                "ioc_value": ioc_value,
                "distinct_source_count": len(distinct_sources),
                "sources": sorted(list(distinct_sources)),
                "record_count": len(group_records),
                "records": [
                    {
                        "source": r.source,
                        "record_id": r.record_id,
                        "malware_family": r.malware_family,
                        "confidence": r.confidence,
                        "reporter": r.reporter,
                        "timestamp": r.timestamp
                    }
                    for r in group_records
                ]
            })

    # Sort by number of distinct sources descending
    overlaps.sort(key=lambda x: x["distinct_source_count"], reverse=True)
    return overlaps
