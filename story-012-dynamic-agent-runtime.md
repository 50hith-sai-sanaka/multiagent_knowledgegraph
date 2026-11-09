# STORY-012 — Dynamic CTI Agent Runtime and Graph Integrity

**Status:** Implemented and live-service verified; product-hardening work remains  
**Created:** 2026-11-04  
**Executed:** 2026-11-04  
**Purpose:** Convert the existing ProGRESS prototype into a safely executable, data-driven CTI agent pipeline; repair coordination and provenance correctness; reconcile written project status with what is actually implemented and tested.

> Security note: API credentials are runtime secrets. Never commit them, place them in story/documentation, print them, or include them in diagnostics. Provider selection must be explicit; do not infer a provider from the credential value.

## Context and user story

The project had source-feed adapters, normalized offline datasets, local JSON-backed source tools, LangGraph workflow code, multiple coordinators, Neo4j schema code, and tests, but also material integration gaps: MPAC did not use the lock-manager contract; rejected operations could still be written and counted as committed; ablation hooks were not on the active execution path; protocol selection silently defaulted; source timestamps were not consistently normalized; and the main plan documents disagreed with the checked-in metrics and current modules.

As a CTI analyst/researcher, I want source-specific agents to process current or reproducible CTI evidence, coordinate proposed graph writes, and retain traceable evidence and decisions, so that graph results are auditable and inconsistent claims are preserved rather than silently overwritten.

## Execution results

Implemented MPAC lock-token acquisition/release, fail-closed Redis setup, safe cleanup after partial lock acquisition, deterministic arbitration, and operation counts based on writes actually applied. Rejected claims are retained with Evidence, Claim, Decision, and Conflict audit links but do not mutate domain entities. Accepted entity writes plus their provenance use one Neo4j transaction. Cypher labels/property identifiers are validated; values are parameterized. Ablations now override active hooks; timestamp ablation uses evidence timestamps, no-lock mode bypasses semantic locks, and no-A2A mode bypasses peer verification.

Added a loopback-only FastAPI service with health, one-IOC processing, batch processing, and explicit source-sync routes; added a runtime guide and Makefile target. Data tools resolve paths from the project root. Feed timestamps are normalized to UTC ISO-8601 when parseable. Sync now refreshes `statistics.json` alongside the sync log. LLM label suggestions cannot authorize graph schema changes; generated properties are allowlisted; missing family attribution produces A2A abstentions. Neo4j and Docker now use the same environment-driven password instead of mismatched hardcoded defaults. Main planning documents are identified as historical, and the stale sync-log values are labeled as historical rather than overwritten.

## Acceptance criteria

### Runtime and reproducibility

- [x] Offline dataset replay remains available and source paths are independent of caller working directory.
- [x] Local API supports one IOC and batches with explicit supported protocol names; unknown names fail explicitly.
- [x] Source refresh is a deliberate `/sync` call; the source sync updates snapshot statistics and log.
- [x] Source-specific agents use their matching local source adapter; peers without comparable family evidence abstain.
- [x] Runtime guide documents setup, database/schema initialization, optional LLM configuration, API usage, and readiness boundaries.

### Coordination and graph integrity

- [x] MPAC follows the lock manager's token contract and releases partial or completed locks on failure paths.
- [x] Rejected operations do not write domain entities and are not counted as committed.
- [x] Accepted writes and linked evidence/claim/provenance records share one transaction; rejected claims and decisions remain auditable.
- [x] Stable MERGE identities and explicit provenance/conflict/decision relationships are used.
- [x] Interpolated Cypher identifiers are validated; dynamic writes remain limited to safe approved identifiers.
- [x] Ablations alter active execution hooks and have regression tests.
- [x] The runtime guide describes the implemented deterministic FCFS policy honestly; authority/confidence-weighted arbitration is not claimed.

### Evidence and agent behavior

- [x] Graph operations carry source, record ID, timestamp, canonical IOC key, and raw-evidence reference material from normalized records.
- [~] Tier-1 labels are deterministically gated and LLM label changes are rejected. Full dynamic Tier-2 ontology proposal/approval integrated into MPAC writes remains unfinished.
- [x] Peer verification uses actual local peer evidence, offloads blocking file scans, and abstains when comparison evidence is incomplete.
- [x] LLM enrichment remains optional/advisory, does not supply provenance facts, and generated extra fields are allowlisted.
- [x] Model output cannot overwrite source, record, timestamp, identity, or audit fields through arbitrary properties.

### Tests and documentation

- [x] Added deterministic regression tests for locks, rejected writes, audit links, safe labels, protocol dispatch, ablation behavior, missing attribution, and timestamp parsing.
- [x] Neo4j integration tests ran against the local service and passed; they remain separately identifiable from offline tests.
- [~] Current snapshot counts are stated from the normalized file/statistics file; the conflicting sync log and old PRD/stories remain intact but are labeled historical. The datasets were not independently ground-truth verified.
- [x] PRD, technical spec, task breakdown, and runtime guide distinguish historical plan from present execution.
- [x] All 43 Python files AST-parse; the API module imports; focused Ruff checks pass. **81 tests pass**, including Neo4j integration tests.
- [x] Local schema initialization and an API→agent→MPAC→Neo4j transaction smoke test passed; the synthetic test graph records were deleted afterward.

## Remaining work and verification blockers

Full dynamic Tier-2 ontology governance, authentication/authorization before exposing the API beyond loopback, authority/confidence-weighted arbitration, and a valid comparative benchmark harness remain future work. The API is loopback-only. The full-repository Ruff run still reports legacy findings outside the focused touched-file check.

No LLM can be guaranteed to “perfectly think.” The system target is bounded, evidence-grounded, reproducible behavior with explicit abstention and auditable uncertainty—not perfect reasoning or production readiness claims.

## Definition of done

The local corrective implementation, offline regression criteria, schema initialization, Neo4j integration tests, and one service-backed API/MPAC graph transaction are executed. Broader benchmark/research validity and future production hardening are not claimed.
