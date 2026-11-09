# STORY-002: Core Pydantic Data Contracts & Utilities

**Goal** – Provide a single source of truth for data structures used across the project.

### Acceptance Criteria
- ✅ Five Pydantic models defined: `Claim`, `GraphOperation`, `ArbitrationDecision`, `CoordinationResult`, `A2AQuery`.
- ✅ `Claim.generate_id()` creates a SHA‑256 hash of `evidence_id + timestamp` (ISO‑8601 UTC) – different timestamps give different IDs.
- ✅ `GraphOperation.lock_keys` validator sorts keys lexicographically and raises `ValueError` on an empty list.
- ✅ Timestamp normalizer parses ThreatFox, URLhaus, OTX, and MalwareBazaar formats and returns ISO‑8601 UTC string **and** Unix epoch.
- ✅ Full test suite (`tests/test_models.py`) passes with 100 % coverage.

### Tasks (ordered)
1. **Create `src/schemas/models.py`**
   - Define the five models with `BaseModel`.
   - Add `generate_id` classmethod to `Claim`.
   - Add `@field_validator('lock_keys')` to `GraphOperation` (lexicographic sort, empty‑list error).
2. **Create `src/utils/time.py`**
   - Implement `normalize_timestamp(ts: str) -> Tuple[str, int]` handling the four feed formats.
3. **Write tests `tests/test_models.py`** covering:
   - ID uniqueness for different timestamps.
   - Lock‑key sorting and empty‑list validation.
   - All timestamp‑parsing edge cases.
4. **Run verification**
   ```bash
   PYTHONPATH=. ./venv/bin/python3 -m pytest tests/test_models.py -v
   ```
   All tests must pass before any downstream story can start.

### Notes
- The story runs in parallel with STORY‑001; there are no blockers between them.
- Ensure `pytest.ini` contains `asyncio_mode = auto` (already present).
- Keep the models immutable (`ConfigDict(frozen=True)`) to guarantee data integrity.

---
*When the above steps are completed and the test gate succeeds, STORY‑002 is considered DONE.*
