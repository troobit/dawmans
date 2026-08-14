"""StateValue, StateSnapshot, the StateSource protocol.

A state value is a flat (key, value, observed_at, origin, origin_kind)
triple, not a DAW-shaped object model (Decision 7): the flat shape is
what admits the LogTail and Als implementations without redefinition
(8.4). `origin_kind` is the one field beyond raw provenance — a
saved-file source is stale by definition, so 8.7's warning fires from
the record's own shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class StateValue:
    key: str  # dotted, e.g. "track.3.monitor", "audio.device"
    value: str | int | float | bool
    observed_at: datetime  # 8.5 freshness
    origin: str  # 8.5 which implementation
    origin_kind: Literal["live", "saved-file"]  # drives 8.7


@dataclass(frozen=True)
class StateSnapshot:
    values: tuple[StateValue, ...]
    acquired_at: datetime


@runtime_checkable
class StateSource(Protocol):
    origin: str

    async def snapshot(self) -> StateSnapshot:
        """May raise; the engine bounds it with wait_for(0.100) (8.9)."""
        ...
