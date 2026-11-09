# Story 011 – LLM‑Agentic Enrichment with Free API Keys

## Overview
We want to **augment the existing multi‑agent CTI pipeline** with a lightweight LLM that can:
- Generate natural‑language summaries of claims.
- Propose additional Neo4j node properties (tags, tactics, confidence adjustments).
- Suggest a more appropriate node label when the current one looks wrong.

The LLM will be accessed via **free‑tier API keys** (e.g., OpenAI’s free‑tier, Anthropic’s free tier, or any other public LLM service that provides a free quota). The implementation must **gracefully degrade** when no key is set – the pipeline should still run using only the existing MCP tools.

## Acceptance Criteria
1. **LLM Wrapper** – `src/llm/llm_tool.py` provides an async `complete` method that reads `LLM_API_KEY` from the environment. If the variable is missing, the wrapper raises a clear `RuntimeError`.
2. **State Extension** – `AgentState` (in `src/agents/state.py`) gains two optional fields:
   - `llm_summary: str | None`
   - `llm_extra_props: dict[str, Any] | None`
3. **LangGraph Node** – a new node `enrich_with_llm` is inserted between `extract_claim` and `a2a_peer_check` (see story‑010 implementation). It calls the LLM wrapper, parses a JSON response, and updates the state:
   - Store the human‑readable `summary` in `llm_summary`.
   - Merge `extra_props` into the `GraphOperation` before it is sent to the coordinator.
   - If `new_label` is present, replace the node label in the `GraphOperation`.
4. **Fallback Behaviour** – when `LLM_API_KEY` is not set, the node logs a warning and returns an empty dict, leaving the pipeline unchanged.
5. **Tests** – add unit tests (`tests/test_llm_enrich.py`) that:
   - Mock the LLM response and verify state updates.
   - Verify that the coordinator receives the enriched `GraphOperation`.
   - Confirm graceful fallback when the env var is missing.
6. **Documentation** – update `README.md` with a section **LLM‑Agentic Enrichment** describing how to obtain a free key and set `LLM_API_KEY`.
7. **Docker Integration** – extend `docker-compose.yml` to expose the env var to the `app` service (optional, but documented).

## Tasks (ordered)
| # | Task | Owner | Estimate (hrs) |
|---|------|-------|----------------|
| 1 | Create `src/llm/llm_tool.py` wrapper | @member1 | 2 |
| 2 | Extend `AgentState` with new fields | @member2 | 1 |
| 3 | Implement `enrich_with_llm` node in `src/agents/workflow.py` | @member1 | 3 |
| 4 | Wire node into the LangGraph graph | @member1 | 1 |
| 5 | Merge `llm_extra_props` into `GraphOperation` in `submit_to_coordinator` | @member2 | 2 |
| 6 | Write unit tests (`tests/test_llm_enrich.py`) with mocked LLM | @member2 | 3 |
| 7 | Add fallback handling when `LLM_API_KEY` missing | @member1 | 1 |
| 8 | Update documentation (`README.md`) and Docker env var | @member2 | 1 |
| 9 | Run full test suite, verify 65+ passed | — | 0.5 |

## Free API Key Options
- **OpenAI** – Sign up at https://platform.openai.com/account/api-keys. The free tier gives $5 credit and a limited number of requests per month.
- **Anthropic** – https://www.anthropic.com/api provides a free trial with 5 M tokens.
- **Mistral** – https://mistral.ai/ also offers a free tier.

The wrapper is deliberately provider‑agnostic; only the `base_url` and payload format need to be tweaked for a different service.

---

*Story 011 continues the incremental, test‑driven approach of the previous stories and keeps the repository fully functional even when the LLM service is unavailable.*
