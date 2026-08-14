"""NullStateSource: the empty snapshot, immediately.

The only MVP implementation (8.3). Returning immediately is what keeps
the 100 ms state timeout immaterial and 8.2's no-degradation guarantee
free of special cases — asserted in the turn-pipeline tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dawmans.answer.state.base import StateSnapshot


class NullStateSource:
    origin = "null"

    async def snapshot(self) -> StateSnapshot:
        return StateSnapshot(values=(), acquired_at=datetime.now(UTC))
