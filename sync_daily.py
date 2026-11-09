import json
import os
from datetime import datetime
from dotenv import load_dotenv

from sources.threatfox import ThreatFoxSource
from sources.urlhaus import URLhausSource
from sources.malwarebazaar import MalwareBazaarSource
from sources.otx import OTXSource
from analysis.overlap import find_cross_source_overlaps
from analysis.conflict import detect_cti_conflicts


def run_daily_sync():
    """
    Daily Sync Job:
    1. Fetches the latest live feeds from all 4 sources.
    2. Merges with existing normalized records (deduplicating by source + record_id).
    3. Re-computes updated cross-source overlaps and conflicts.
    4. Logs the sync timestamp and new indicators added.
    """
    load_dotenv()
    now_utc = datetime.utcnow().isoformat() + "Z"

    print("==========================================================")
    print(f"      ProGRESS Automated Daily CTI Sync [{now_utc}]       ")
    print("==========================================================")

    # 1. Load existing normalized dataset
    normalized_path = os.path.join("data", "normalized", "normalized_cti.json")
    existing_map = {}
    if os.path.exists(normalized_path):
        with open(normalized_path, "r", encoding="utf-8") as f:
            existing_records = json.load(f)
            for r in existing_records:
                key = (r["source"], r["record_id"])
                existing_map[key] = r
    print(f"[*] Loaded existing dataset: {len(existing_map):,} records.")

    sources = [
        ThreatFoxSource(),
        URLhausSource(),
        MalwareBazaarSource(),
        OTXSource()
    ]

    new_records_count = 0

    for source in sources:
        print(f"\n[+] Syncing fresh feed from {source.name}...")
        raw_data = source.fetch_raw(limit=2000)
        
        # Update raw archive
        raw_filepath = os.path.join("data", "raw", f"{source.name.lower()}.json")
        source.save_raw(raw_data, raw_filepath)

        normalized = source.normalize(raw_data)
        source_new = 0
        for rec in normalized:
            key = (rec.source, rec.record_id)
            if key not in existing_map:
                existing_map[key] = rec.model_dump()
                new_records_count += 1
                source_new += 1

        print(f"    Normalized: {len(normalized):,} | Fresh new records added: {source_new:,}")

    # 2. Save Updated Merged Dataset & Individual Provider Files
    updated_records = list(existing_map.values())
    with open(normalized_path, "w", encoding="utf-8") as f:
        json.dump(updated_records, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] Updated dataset saved -> {normalized_path} ({len(updated_records):,} total records)")

    # Save per-provider datasets
    for source in sources:
        provider_norm_path = os.path.join("data", "normalized", f"{source.name.lower()}.json")
        provider_records = [r for r in updated_records if r["source"] == source.name]
        with open(provider_norm_path, "w", encoding="utf-8") as f:
            json.dump(provider_records, f, indent=2, ensure_ascii=False)

    # 3. Re-run Analysis on updated dataset
    from schemas.cti import NormalizedCTIRecord
    re_instantiated = [NormalizedCTIRecord(**r) for r in updated_records]

    overlaps = find_cross_source_overlaps(re_instantiated)
    overlaps_path = os.path.join("data", "analysis", "overlaps.json")
    with open(overlaps_path, "w", encoding="utf-8") as f:
        json.dump(overlaps, f, indent=2, ensure_ascii=False)

    conflicts = detect_cti_conflicts(re_instantiated)
    conflicts_path = os.path.join("data", "analysis", "conflicts.json")
    with open(conflicts_path, "w", encoding="utf-8") as f:
        json.dump(conflicts, f, indent=2, ensure_ascii=False)

    # 4. Save Sync Log
    sync_log = {
        "last_sync_utc": now_utc,
        "new_records_added": new_records_count,
        "total_records": len(updated_records),
        "total_overlaps": len(overlaps),
        "total_conflicts": len(conflicts)
    }
    source_breakdown = {
        source.name: sum(1 for record in updated_records if record["source"] == source.name)
        for source in sources
    }
    statistics = {
        "total_normalized_records": len(updated_records),
        "unique_iocs": len({(r["ioc_type"], r["ioc_value"].strip().lower()) for r in updated_records}),
        "cross_source_overlaps": len(overlaps),
        "detected_conflicts": len(conflicts),
        "source_breakdown": source_breakdown,
    }
    stats_path = os.path.join("data", "analysis", "statistics.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(statistics, f, indent=2)
    log_path = os.path.join("data", "analysis", "sync_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(sync_log, f, indent=2)

    print("\n==========================================================")
    print(f" [✓] Daily Sync Complete! Added {new_records_count:,} new records.")
    print(f" Total Records : {len(updated_records):,} | Overlaps: {len(overlaps):,} | Conflicts: {len(conflicts):,}")
    print("==========================================================")


if __name__ == "__main__":
    run_daily_sync()
