import argparse
import json
import os
from dotenv import load_dotenv

from sources.threatfox import ThreatFoxSource
from sources.urlhaus import URLhausSource
from sources.malwarebazaar import MalwareBazaarSource
from sources.otx import OTXSource
from analysis.overlap import find_cross_source_overlaps
from analysis.conflict import detect_cti_conflicts


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="ProGRESS High-Volume CTI Data Ingestion Pipeline")
    parser.add_argument("--threatfox-limit", type=int, default=3000, help="Max ThreatFox IOCs to ingest (default: 3000)")
    parser.add_argument("--urlhaus-limit", type=int, default=5000, help="Max URLhaus URLs to ingest (default: 5000)")
    parser.add_argument("--bazaar-limit", type=int, default=1000, help="Max MalwareBazaar samples to ingest (default: 1000)")
    parser.add_argument("--otx-limit", type=int, default=100, help="Max OTX pulses to ingest (default: 100)")
    parser.add_argument("--full", action="store_true", help="Ingest all available records without truncation")
    args = parser.parse_args()

    tf_limit = 0 if args.full else args.threatfox_limit
    uh_limit = 0 if args.full else args.urlhaus_limit
    mb_limit = 0 if args.full else args.bazaar_limit
    otx_limit = 0 if args.full else args.otx_limit

    print("==========================================================")
    print("      ProGRESS High-Volume Real CTI Ingestion Pipeline     ")
    print("==========================================================")
    print(f" Target Limits -> ThreatFox: {tf_limit or 'ALL'}, URLhaus: {uh_limit or 'ALL'}, Bazaar: {mb_limit or 'ALL'}, OTX: {otx_limit or 'ALL'}")

    sources_with_limits = [
        (ThreatFoxSource(), tf_limit),
        (URLhausSource(), uh_limit),
        (MalwareBazaarSource(), mb_limit),
        (OTXSource(), otx_limit)
    ]

    all_normalized_records = []
    stats_breakdown = {}

    for source, limit in sources_with_limits:
        print(f"\n[+] Fetching live feed from {source.name}...")
        raw_data = source.fetch_raw(limit=limit)
        print(f"    Raw records retrieved: {len(raw_data):,}")

        # Save raw JSON dump
        raw_filepath = os.path.join("data", "raw", f"{source.name.lower()}.json")
        source.save_raw(raw_data, raw_filepath)
        print(f"    Saved raw dump -> {raw_filepath}")

        # Normalize records
        normalized = source.normalize(raw_data)
        all_normalized_records.extend(normalized)
        stats_breakdown[source.name] = len(normalized)
        print(f"    Normalized CTI records: {len(normalized):,}")

        # Save separate normalized file for this specific provider
        provider_norm_path = os.path.join("data", "normalized", f"{source.name.lower()}.json")
        os.makedirs(os.path.dirname(provider_norm_path), exist_ok=True)
        with open(provider_norm_path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in normalized], f, indent=2, ensure_ascii=False)
        print(f"    Saved provider normalized dataset -> {provider_norm_path}")

    # Save Unified Combined Normalized Dataset
    normalized_path = os.path.join("data", "normalized", "normalized_cti.json")
    os.makedirs(os.path.dirname(normalized_path), exist_ok=True)
    with open(normalized_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in all_normalized_records], f, indent=2, ensure_ascii=False)
    print(f"\n[✓] Saved unified normalized dataset -> {normalized_path} ({len(all_normalized_records):,} records)")

    # Cross-Source Overlap Detection
    print("\n[+] Running Cross-Source Overlap Detection across all records...")
    overlaps = find_cross_source_overlaps(all_normalized_records)
    overlaps_path = os.path.join("data", "analysis", "overlaps.json")
    os.makedirs(os.path.dirname(overlaps_path), exist_ok=True)
    with open(overlaps_path, "w", encoding="utf-8") as f:
        json.dump(overlaps, f, indent=2, ensure_ascii=False)
    print(f"    Saved overlaps report -> {overlaps_path} ({len(overlaps):,} overlaps found)")

    # Programmatic Conflict Detection
    print("\n[+] Running Programmatic Conflict Detection across all records...")
    conflicts = detect_cti_conflicts(all_normalized_records)
    conflicts_path = os.path.join("data", "analysis", "conflicts.json")
    with open(conflicts_path, "w", encoding="utf-8") as f:
        json.dump(conflicts, f, indent=2, ensure_ascii=False)
    print(f"    Saved conflicts report -> {conflicts_path} ({len(conflicts):,} conflicts detected)")

    # Summary Statistics
    unique_iocs = len(set((r.ioc_type, r.ioc_value.strip().lower()) for r in all_normalized_records))

    stats = {
        "total_normalized_records": len(all_normalized_records),
        "unique_iocs": unique_iocs,
        "cross_source_overlaps": len(overlaps),
        "detected_conflicts": len(conflicts),
        "source_breakdown": stats_breakdown
    }

    stats_path = os.path.join("data", "analysis", "statistics.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print("\n==========================================================")
    print("                HIGH-VOLUME PIPELINE REPORT                ")
    print("==========================================================")
    print(f" Total Normalized Records : {len(all_normalized_records):,}")
    print(f" Unique IOC Indicators     : {unique_iocs:,}")
    print(f" Cross-Source Overlaps     : {len(overlaps):,}")
    print(f" Conflicting Claims        : {len(conflicts):,}")
    print("----------------------------------------------------------")
    print(" Breakdown by Source:")
    for src_name, count in stats_breakdown.items():
        print(f"   - {src_name:<15}: {count:,} records")
    print("==========================================================")
    print("[✓] High-Volume CTI Ingestion & Conflict Analysis Complete!")


if __name__ == "__main__":
    main()
