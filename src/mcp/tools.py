# src/mcp/tools.py
"""MCP Tool Registry — Story 008.

Provides a dictionary mapping each principal (agent ID) to its exclusive
MCP tool instance. The agents use this registry to look up the tool that
matches their data source.
"""
from __future__ import annotations

from src.mcp.malwarebazaar_tool import MalwareBazaarMCPTool
from src.mcp.otx_tool import OTXMCPTool
from src.mcp.threatfox_tool import ThreatFoxMCPTool
from src.mcp.urlhaus_tool import URLhausMCPTool

# Mapping of principal ID → tool instance
MCP_TOOLS: dict[str, object] = {
    "Principal-ThreatFox":       ThreatFoxMCPTool(),
    "Principal-URLhaus":         URLhausMCPTool(),
    "Principal-MalwareBazaar":   MalwareBazaarMCPTool(),
    "Principal-OTX":             OTXMCPTool(),
}

__all__ = ["MCP_TOOLS"]
