from typing import List, Dict, Any
from collections import defaultdict
from schemas.cti import NormalizedCTIRecord


def detect_cti_conflicts(records: List[NormalizedCTIRecord]) -> List[Dict[str, Any]]:
    """
    Programmatically detects conflicting claims across sources for the same IOC:
    1. Malware Family Attribution Conflicts (e.g., RedLine vs AgentTesla)
    2. Significant Confidence Discrepancies (>25% score divergence)
    """
    ioc_groups = defaultdict(list)

    for record in records:
        key = (record.ioc_type, record.ioc_value.strip().lower())
        ioc_groups[key].append(record)

    conflicts = []

    for (ioc_type, ioc_value), group_records in ioc_groups.items():
        distinct_sources = set(r.source for r in group_records)
        if len(distinct_sources) < 2:
            continue

        # Extract non-empty malware families across sources
        family_map = {}
        for r in group_records:
            if r.malware_family:
                # Normalize string for comparison
                clean_fam = r.malware_family.strip().lower()
                if clean_fam not in family_map:
                    family_map[clean_fam] = []
                family_map[clean_fam].append((r.source, r.malware_family))

        # Check for Attribution Conflict
        has_attribution_conflict = len(family_map) > 1

        # Check for Confidence Discrepancy (> 25 divergence)
        confidences = [r.confidence for r in group_records if r.confidence is not None]
        has_confidence_conflict = False
        confidence_diff = 0
        if confidences:
            confidence_diff = max(confidences) - min(confidences)
            if confidence_diff > 25:
                has_confidence_conflict = True

        if has_attribution_conflict or has_confidence_conflict:
            conflicts.append({
                "ioc_type": ioc_type,
                "ioc_value": ioc_value,
                "conflict_types": [
                    "attribution_conflict" if has_attribution_conflict else None,
                    "confidence_discrepancy" if has_confidence_conflict else None
                ],
                "conflicting_families": [
                    {"canonical_name": fam, "sources": sources}
                    for fam, sources in family_map.items()
                ] if has_attribution_conflict else [],
                "confidence_range": {
                    "min": min(confidences) if confidences else None,
                    "max": max(confidences) if confidences else None,
                    "difference": confidence_diff
                },
                "involved_records": [
                    {
                        "source": r.source,
                        "record_id": r.record_id,
                        "malware_family": r.malware_family,
                        "confidence": r.confidence,
                        "reporter": r.reporter
                    }
                    for r in group_records
                ]
            })

    # Remove None values from conflict_types
    for c in conflicts:
        c["conflict_types"] = [t for t in c["conflict_types"] if t is not None]

    return conflicts
