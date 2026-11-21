"""
Multi-Provider LLM Factory with SHA256 Content-Addressed Benchmark Cache
File: src/agents/llm_factory.py
Sprint: Sprint 2 (STORY-006)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional, Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
_CACHE_PATH = os.path.join("data", "cache", "llm_structured_cache.json")
_CACHE_LOCK = asyncio.Lock()


def get_chat_llm(temperature: float = 0.0):
    """Instantiate configured LLM provider (Gemini, OpenAI, Groq)."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model_name = os.getenv("LLM_MODEL", "gemini-3.8-flash")

    if provider == "gemini":
        api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=temperature)
        except ImportError:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                temperature=temperature,
            )
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model_name, temperature=temperature)
    
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model_name, temperature=temperature)


def compute_cache_key(prompt: str, schema_cls: Type[BaseModel]) -> str:
    """Compute deterministic SHA-256 hash over schema name and prompt text."""
    raw = f"{schema_cls.__name__}:{prompt.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def invoke_structured_llm(
    prompt: str,
    schema_cls: Type[T],
    cache_path: Optional[str] = None,
) -> T:
    """
    Invokes the LLM with structured Pydantic output, cached by content-addressed SHA256.

    Guarded by asyncio.Lock to prevent concurrent task race conditions on disk.
    If cached on disk, loads and returns the model immediately without making network calls.
    """
    path = cache_path or _CACHE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cache_key = compute_cache_key(prompt, schema_cls)

    # 1. Check cache under lock
    async with _CACHE_LOCK:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                if cache_key in cache:
                    logger.debug("LLM cache hit for key %s", cache_key)
                    return schema_cls(**cache[cache_key])
            except Exception as e:
                logger.warning("Could not read LLM cache at %s: %s", path, e)

    # 2. Invoke LLM outside the lock (avoid blocking concurrent tasks during network I/O)
    llm = get_chat_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(schema_cls)
    result: T = await structured_llm.ainvoke(prompt)

    # 3. Persist to cache under lock
    async with _CACHE_LOCK:
        current_cache: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    current_cache = json.load(f)
            except Exception:
                current_cache = {}

        current_cache[cache_key] = result.model_dump()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(current_cache, f, indent=2)
        except Exception as e:
            logger.warning("Could not write LLM cache to %s: %s", path, e)

    return result

