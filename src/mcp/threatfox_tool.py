# src/mcp/threatfox_tool.py
"""MCP tool for ThreatFox data source.

Searches the pre‑saved ``data/normalized/threatfox.json`` file for a matching
IOC value and returns an :class:`MCPResponse`.
"""
from __future__ import annotations

from pathlib import Path

from src.mcp.base_tool import BaseMCPTool


class ThreatFoxMCPTool(BaseMCPTool):
    """Concrete MCP tool for the ThreatFox source."""

    @property
    def source_name(self) -> str:
        return "ThreatFox"

    @property
    def data_file(self) -> Path:
        return Path("data/normalized/threatfox.json")
