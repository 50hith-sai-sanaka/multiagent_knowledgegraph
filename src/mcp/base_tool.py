# src/mcp/base_tool.py
"""MCP Tool Base Class — Story 008

Defines the contract that every MCP tool must implement.
All 4 source tools inherit this class.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPResponse:
    """Standard return type for every MCP tool.

    Attributes
    ----------
    source: str
        Name of the data source (e.g. "ThreatFox").
    records: list[dict[str, Any]]
        Matching records; empty list means no match.
    """
    source: str
    records: List[dict[str, Any]] = field(default_factory=list)


class BaseMCPTool(ABC):
    """Abstract base class for all MCP tool adapters.

    Subclasses must provide ``source_name`` and ``data_file`` properties.
    The ``invoke`` method performs a case‑insensitive lookup on the
    ``ioc_value`` field of each record.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human readable source name, e.g. "ThreatFox"."""
        ...

    @property
    @abstractmethod
    def data_file(self) -> Path:
        """Path to the normalized JSON file for this source."""
        ...

    def _load_records(self) -> List[dict[str, Any]]:
        """Load JSON data lazily and cache it on the instance.

        The JSON files are a list of plain dict records.
        """
        if not hasattr(self, "_cache"):
            path = self.data_file
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / path
            if not path.is_file():
                logger.warning("MCP data file not found: %s", path)
                self._cache = []
            else:
                with path.open(encoding="utf-8") as fh:
                    self._cache = json.load(fh)
                logger.debug("Loaded %d records from %s", len(self._cache), path)
        return self._cache

    def invoke(self, ioc_value: str) -> MCPResponse:
        """Search for records whose ``ioc_value`` matches the supplied value.

        Matching is case‑insensitive and whitespace‑trimmed.
        """
        needle = ioc_value.strip().lower()
        matches = [r for r in self._load_records() if str(r.get("ioc_value", "")).strip().lower() == needle]
        logger.debug("%s: %d match(es) for '%s'", self.source_name, len(matches), ioc_value)
        return MCPResponse(source=self.source_name, records=matches)
