"""
Tests for Multi-Provider LLM Factory & SHA256 Benchmark Cache
File: tests/test_llm_factory.py
Sprint: Sprint 2 (STORY-006)
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from src.agents.llm_factory import compute_cache_key, invoke_structured_llm


class SampleOutputSchema(BaseModel):
    category: str = Field(description="Sample category")
    confidence: int = Field(default=85)


def test_compute_cache_key_deterministic():
    k1 = compute_cache_key("Analyze this indicator", SampleOutputSchema)
    k2 = compute_cache_key("Analyze this indicator", SampleOutputSchema)
    assert k1 == k2
    assert len(k1) == 64

    k_diff = compute_cache_key("Different prompt", SampleOutputSchema)
    assert k1 != k_diff


@pytest.mark.asyncio
async def test_invoke_structured_llm_cache_miss_then_hit():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_cache_file = os.path.join(tmpdir, "test_cache.json")
        prompt = "Evaluate IP 1.2.3.4"

        # Mock structured LLM
        mock_output = SampleOutputSchema(category="Malicious", confidence=95)
        mock_structured = AsyncMock()
        mock_structured.ainvoke = AsyncMock(return_value=mock_output)

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured

        with patch("src.agents.llm_factory.get_chat_llm", return_value=mock_llm):
            # First invocation: Cache Miss
            res1 = await invoke_structured_llm(prompt, SampleOutputSchema, cache_path=test_cache_file)
            assert res1.category == "Malicious"
            assert res1.confidence == 95
            assert mock_structured.ainvoke.call_count == 1

            # Verify saved on disk
            assert os.path.exists(test_cache_file)
            with open(test_cache_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            key = compute_cache_key(prompt, SampleOutputSchema)
            assert key in saved
            assert saved[key]["category"] == "Malicious"

            # Second invocation: Cache Hit (Zero network/LLM calls)
            res2 = await invoke_structured_llm(prompt, SampleOutputSchema, cache_path=test_cache_file)
            assert res2.category == "Malicious"
            assert mock_structured.ainvoke.call_count == 1  # Unchanged!

