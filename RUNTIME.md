# ProGRESS Runtime Guide

## What currently runs

The local runtime uses normalized CTI JSON snapshots under `data/normalized/` as agent evidence. The four source-specific tools search their corresponding files. `POST /sync` deliberately refreshes these files using the source adapters; it may contact public CTI providers and updates local data, so call it only when a refresh is intended. The peer hub compares local snapshots; it is not a networked MCP server or remote agent mesh.

The graph sequence is receive → source evidence lookup → claim construction → optional LLM enrichment → optional peer check → selected coordinator. The LLM is advisory: its suggested label does not authorize schema changes, and generated properties are not source evidence. Live Neo4j/Redis operation and one API-to-MPAC transaction have been exercised locally, but this is not a substitute for production deployment validation.

## Local setup and start

1. Install dependencies with `./venv/bin/pip install -r requirements.txt`.
2. Configure Neo4j and Redis credentials in the ignored `.env` file. Docker Compose and the Neo4j client use `NEO4J_USER`/`NEO4J_PASSWORD`. The local `.env` is owner-readable only. Do not copy secrets to code, docs, fixtures, or logs. `LLM_PROVIDER` must match the provider for `LLM_API_KEY`.
3. Start services with `docker compose up -d`; Neo4j, Redis, and the API bind to loopback only.
4. Initialize the graph with `PYTHONPATH=. ./venv/bin/python run_schema_init.py`.
5. Start the API with `PYTHONPATH=. ./venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000`.
6. Check `GET http://127.0.0.1:8000/health`; send `POST /agents/process` with `principal_id`, `ioc_value`, and a supported protocol. `POST /agents/batch` accepts up to 100 requests. `POST /sync` explicitly refreshes source data.

The API has no authentication. Keep it bound to localhost; do not expose it on a network until authentication, authorization, rate limits, and deployment hardening are implemented.

## Snapshot and documentation reconciliation

The checked-in snapshot is the authority for current counts: `data/normalized/normalized_cti.json` contains 16,270 records and 12,012 normalized `(ioc_type, ioc_value)` pairs; `data/analysis/statistics.json` reports 259 overlaps and 63 heuristic conflicts. Per-source counts are ThreatFox 3,000, URLhaus 10,000, MalwareBazaar 1,536, and OTX 1,734. The separate `data/analysis/sync_log.json` is historical and disagrees (16,960 records, 431 overlaps, 120 conflicts; last sync 2026-10-10); it remains unchanged to preserve that observation. Older PRD/story figures such as 16,481/371 and 16,270/259 are historical planning values. Current conflicts are rule-detected family disagreement/confidence spread, not independently adjudicated ground truth.

Schema initialization creates **16 uniqueness constraints** (including SHA-256, MD5, and SHA-1) and **4 indexes**. Older story checklists that say 14 constraints/3 indexes are historical.

## Protocols and limitations

Supported protocol names are `adhoc`, `mpac`, `ablation_no_a2a`, `ablation_no_locks`, and `ablation_timestamp`. Ad-Hoc is an intentionally uncoordinated benchmark baseline, not production-safe. Current MPAC arbitration is deterministic FCFS; authority/confidence-weighted reconciliation is not implemented. Dynamic Tier-2 ontology governance is not yet integrated into MPAC writes. A valid comparative benchmark harness also remains future work.

## Verification status

After STORY-012 changes, **81 tests pass**, including Neo4j integration tests. Schema initialization succeeded, Redis and Neo4j were reachable, and the API health endpoint plus a synthetic evidence write through MPAC into Neo4j succeeded; the synthetic graph records were deleted after the smoke test. All 43 Python files parse, and focused Ruff checks pass on core changed modules. Full-repository Ruff still reports legacy style findings outside the focused check. The live smoke test disabled LLM calls. The Gemini credential was not used for the smoke test; rotate it because it was pasted into chat.
