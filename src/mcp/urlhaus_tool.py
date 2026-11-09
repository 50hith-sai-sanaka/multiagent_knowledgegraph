# src/mcp/urlhaus_tool.py
"""MCP tool for URLhaus data source.

Searches ``data/normalized/urlhaus.json`` for matching IOC values.
"""
from __future__ import annotations

from pathlib import Path

from src.mcp.base_tool import BaseMCPTool


class URLhausMCPTool(BaseMCPTool):
    """Concrete MCP tool for the URLhaus source."""

    @property
    def source_name(self) -> str:
        return "URLhaus"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/urlhaus.json")
