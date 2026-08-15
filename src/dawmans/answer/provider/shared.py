"""Shared-backend stub behind the 6.15 disclosure gate.

The backend is not costed, hosted or owned (design §Open). What exists
is the gate: selecting this kind records nothing, status() reports the
acknowledgement requirement, and a turn attempted before acknowledgement
fails pre-flight as provider-unconfigured / disclosure-unacknowledged.
The optional script is the stand-in stream a test drives 6.2 with.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from dawmans.answer.provider.base import (
    ProbeResult,
    ProviderFailure,
    ProviderKind,
    ProviderStatus,
    SynthesisRequest,
)


class SharedBackendProvider:
    kind = ProviderKind.SHARED_BACKEND
    requires_ack = True

    def __init__(
        self, *, acknowledged: bool = False, script: Sequence[str] = ()
    ) -> None:
        self.acknowledged = acknowledged
        self._script = tuple(script)

    def acknowledge(self) -> None:
        """6.15: the one way the disclosure becomes acknowledged."""
        self.acknowledged = True

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            kind=self.kind,
            configured=self.acknowledged,
            masked=None,
            requires_disclosure_ack=not self.acknowledged,
        )

    async def probe(self) -> ProbeResult:
        return ProbeResult(reachable=False, detail="shared backend stub")

    async def stream(self, req: SynthesisRequest) -> AsyncIterator[str]:
        if not self.acknowledged:
            # Defence in depth: the pre-flight gate classifies this turn
            # before any provider call; nothing may stream regardless.
            raise ProviderFailure("error", detail="disclosure unacknowledged")
        for delta in self._script:
            yield delta
