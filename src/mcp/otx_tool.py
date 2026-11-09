# src/mcp/otx_tool.py
"""MCP tool for OTX data source.

Searches ``data/normalized/otx.json`` for matching IOC values.
"""
from __future__ import annotations

from pathlib import Path

from src.mcp.base_tool import BaseMCPTool


class OTXMCPTool(BaseMCPTool):
    """Concrete MCP tool for the OTX source."""

    @property
    def source_name(self) -> str:
        return "OTX"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/otx.json")
