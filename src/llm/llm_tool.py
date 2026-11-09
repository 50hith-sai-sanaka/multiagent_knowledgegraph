# src/llm/llm_tool.py
"""LLM Enrichment Tool — Story 011.

Provides an async wrapper around a free-tier LLM provider (OpenAI-compatible
API or Google Gemini). The tool enriches IOC claims with:
  - A natural-language summary of the threat
  - Extra Neo4j node properties (tags, tactics, severity, CVEs)
  - An optional label correction if the current label seems wrong

Free API options:
  - OpenAI free tier:  https://platform.openai.com  → set LLM_PROVIDER=openai
  - Google Gemini:     https://aistudio.google.com  → set LLM_PROVIDER=gemini  (DEFAULT)
  - Groq (free tier):  https://console.groq.com     → set LLM_PROVIDER=groq
  - Together AI (free):https://api.together.xyz     → set LLM_PROVIDER=together

Environment variables:
  LLM_API_KEY   – Required. API key for the chosen provider.
  LLM_PROVIDER  – Optional. One of: "gemini" (default), "openai", "groq", "together".
  LLM_MODEL     – Optional. Override the default model for the chosen provider.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Provider configurations
# ──────────────────────────────────────────────────────────────────────────────
_PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "gemini": {
        # Google Gemini 2.5 Flash — free tier via AI Studio
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "default_model": "gemini-2.5-flash",
        "auth_param": "key",  # passed as ?key=... query param
        "request_format": "gemini",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-3.5-turbo",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "request_format": "openai",
    },
    "groq": {
        # Groq free tier — very fast, Llama models
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama3-8b-8192",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "request_format": "openai",
    },
    "together": {
        # Together AI free tier
        "base_url": "https://api.together.xyz/v1/chat/completions",
        "default_model": "mistralai/Mistral-7B-Instruct-v0.2",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "request_format": "openai",
    },
}

# System prompt for CTI enrichment
_SYSTEM_PROMPT = (
    "You are a senior cyber-threat-intelligence analyst. "
    "Given an IOC (indicator of compromise), evidence records, and a proposed "
    "Neo4j graph label, produce a JSON object with EXACTLY these three keys:\n"
    "  \"summary\": A 2-sentence plain-English threat summary.\n"
    "  \"extra_props\": A flat JSON object of additional node properties to store "
    "(e.g. {\"tactics\": [\"execution\"], \"severity\": \"high\", \"cve\": null}). "
    "Keep it concise — max 6 key-value pairs.\n"
    "  \"new_label\": Either null (keep current label) or a corrected label string "
    "from this allowed set: IP, Domain, URL, FileHash, Malware, ThreatActor, "
    "Campaign, AttackTechnique.\n"
    "Return ONLY the JSON object — no markdown fences, no explanation."
)


class LLMEnrichmentTool:
    """Async LLM client for CTI claim enrichment.

    Parameters
    ----------
    provider : str, optional
        One of "gemini", "openai", "groq", "together".
        Defaults to the ``LLM_PROVIDER`` env var, or "gemini" if unset.
    api_key : str, optional
        API key. Defaults to the ``LLM_API_KEY`` env var.
    model : str, optional
        Override the default model for the provider.
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
        self._api_key = api_key or os.getenv("LLM_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "LLM_API_KEY environment variable is not set. "
                "Get a free key at https://aistudio.google.com (Gemini), "
                "https://platform.openai.com (OpenAI), "
                "https://console.groq.com (Groq), or "
                "https://api.together.xyz (Together AI)."
            )
        cfg = _PROVIDER_CONFIGS.get(self._provider)
        if cfg is None:
            raise ValueError(
                f"Unknown LLM provider {self._provider!r}. "
                f"Choose one of: {list(_PROVIDER_CONFIGS)}"
            )
        self._cfg = cfg
        self._model = model or os.getenv("LLM_MODEL", cfg["default_model"])

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_openai_request(self, user_prompt: str) -> tuple[str, dict, dict]:
        """Build (url, headers, body) for an OpenAI-compatible API."""
        url: str = self._cfg["base_url"]
        headers = {
            self._cfg["auth_header"]: f"{self._cfg['auth_prefix']} {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 512,
        }
        return url, headers, body

    def _build_gemini_request(self, user_prompt: str) -> tuple[str, dict, dict]:
        """Build (url, headers, body) for Google Gemini API."""
        url = self._cfg["base_url"].format(model=self._model)
        url = f"{url}?key={self._api_key}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                f"{_SYSTEM_PROMPT}\n\n"
                                f"IOC evidence to analyse:\n{user_prompt}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
            },
        }
        return url, headers, body

    def _extract_text(self, response_json: dict) -> str:
        """Extract the model's text output from the provider-specific response."""
        fmt = self._cfg["request_format"]
        if fmt == "gemini":
            # Gemini response: candidates[0].content.parts[0].text
            return response_json["candidates"][0]["content"]["parts"][0]["text"]
        # OpenAI-compatible: choices[0].message.content
        return response_json["choices"][0]["message"]["content"]

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def enrich(
        self,
        ioc_value: str,
        node_label: str,
        malware_family: str | None,
        evidence_sample: dict[str, Any],
    ) -> dict[str, Any]:
        """Call the LLM and return a structured enrichment dict.

        Returns
        -------
        dict with keys:
          summary (str)       – 2-sentence threat narrative
          extra_props (dict)  – additional Neo4j node properties
          new_label (str|None)– corrected label or None
        On any error the method returns safe defaults so the pipeline continues.
        """
        user_prompt = json.dumps(
            {
                "ioc": ioc_value,
                "current_node_label": node_label,
                "malware_family": malware_family,
                "evidence_sample": evidence_sample,
            },
            indent=2,
        )

        fmt = self._cfg["request_format"]
        if fmt == "gemini":
            url, headers, body = self._build_gemini_request(user_prompt)
        else:
            url, headers, body = self._build_openai_request(user_prompt)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                raw_text = self._extract_text(resp.json())

            # Strip accidental markdown fences produced by some providers
            raw_text = raw_text.strip()
            # Handle ```json ... ``` and ``` ... ``` blocks
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                # Drop first line (```json or ```) and last line (```)
                inner_lines = lines[1:]
                if inner_lines and inner_lines[-1].strip() == "```":
                    inner_lines = inner_lines[:-1]
                raw_text = "\n".join(inner_lines).strip()

            parsed: dict = json.loads(raw_text)
            return {
                "summary": str(parsed.get("summary", "")),
                "extra_props": parsed.get("extra_props") or {},
                "new_label": parsed.get("new_label") or None,
            }

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "LLM API returned HTTP %d: %s — skipping enrichment",
                exc.response.status_code,
                exc.response.text[:200],
            )
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned non-JSON response: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM enrichment failed: %s", exc)

        # Safe fallback — empty enrichment
        return {"summary": "", "extra_props": {}, "new_label": None}
