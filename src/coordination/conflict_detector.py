"""
Conflict Detector
File: src/coordination/conflict_detector.py
Story: STORY-005 (Task CD-001)

Given a list of GraphOperation objects, finds pairs of operations that
conflict (share at least one lock_key). The caller (ArbiterCoordinator)
uses this list to decide which operations to accept or reject.

Algorithm: O(N·K) — for each operation, check each of its lock_keys
against a running map of key->first_operation. If the key already exists,
the current operation conflicts with the stored one.
"""

from __future__ import annotations

from src.schemas.models import GraphOperation


class ConflictDetector:
    """Detects conflicting GraphOperation pairs by inspecting lock_keys."""

    def detect(self, operations: list[GraphOperation]) -> list[tuple[GraphOperation, GraphOperation]]:
        """Return a list of (op_a, op_b) pairs that share at least one lock key.

        The FIRST operation in the list to claim a key is stored as the owner.
        Any later operation that wants the same key conflicts with the owner.

        Args:
            operations: Ordered list of GraphOperation objects (earliest first).

        Returns:
            List of conflict pairs. Each pair is (winner_candidate, loser).
        """
        conflicts: list[tuple[GraphOperation, GraphOperation]] = []
        key_owner: dict = {}

        for op in operations:
            for key in op.lock_keys:
                if key in key_owner:
                    # Current op conflicts with whoever first claimed this key
                    conflicts.append((key_owner[key], op))
                else:
                    key_owner[key] = op

        return conflicts
