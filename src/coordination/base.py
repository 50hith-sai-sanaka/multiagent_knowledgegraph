"""
Base Coordinator Abstract Class
File: src/coordination/base.py
Story: STORY-004 (Task P1-001)

All three protocols implement this interface.
Agents call submit() — the protocol handles the rest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.schemas.models import CoordinationResult, GraphOperation


class BaseCoordinator(ABC):
    """Abstract base for all coordination protocols."""

    @abstractmethod
    async def submit(self, operation: GraphOperation) -> CoordinationResult:
        """Process one agent graph‑write operation.

        Returns a ``CoordinationResult`` containing status, latency,
        and conflict information.
        """
        ...
