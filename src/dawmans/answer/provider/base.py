"""Provider protocol, SynthesisRequest, ProviderFailure.

The interface carries text deltas and nothing else — no citations, no
structure, no outcome. Framing, parsing, citation resolution and
grounding are engine-side for every provider, which is what makes 6.2
structural rather than a per-provider obligation (Decision 4).

`requires_key` is derived from the kind (6.4), and `max_words` is fixed
at 400: 1.6's longer form has no transport in the MVP — the deferral is
recorded in the design, so no request field is invented here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

# 1.6: the MVP transport carries no longer-form request, so the cap is a
# constant rather than a caller choice.
MAX_WORDS = 400


class ProviderKind(StrEnum):
    KEYED_HOSTED = "keyed-hosted"
    LOCAL = "local"
    SHARED_BACKEND = "shared-backend"


def requires_key(kind: ProviderKind) -> bool:
    """6.4: whether a credential is required is a property of the kind."""
    return kind is ProviderKind.KEYED_HOSTED


def mask(key: str) -> str:
    """6.13: the only form a stored key takes on any read path."""
    return "…" + key[-4:]


@dataclass(frozen=True)
class SynthesisRequest:
    """One turn's synthesis input. `system` is the cache prefix; passages,
    history and state vary per turn and sit after the breakpoint.

    `user` is the varying half pre-rendered by `prompt.assemble` — the one
    renderer that also carries the unselected-source roster and the 7.5
    terminal direction, which the structured fields cannot (Decision 11).
    Where it is set, providers send it verbatim and the structured fields
    document what went into it.
    """

    system: str
    passages: tuple[Mapping[str, Any], ...]
    question: str
    history: tuple[str, ...] = ()
    state: Any | None = None  # StateSnapshot-shaped; never citable (8.6)
    max_words: int = MAX_WORDS
    user: str | None = None


@dataclass(frozen=True)
class ProviderStatus:
    """What every read path may see. `masked` is the last-4 form or None —
    there is deliberately no field that can hold a full key (6.13)."""

    kind: ProviderKind
    configured: bool
    masked: str | None = None
    model: str | None = None
    # Visible cache loss (design §Anthropic provider specifics): a model
    # whose cache minimum the system prompt does not clear reports
    # "unavailable" rather than silently losing the cache.
    prompt_cache: Literal["available", "unavailable"] | None = None
    requires_disclosure_ack: bool = False  # 6.15, shared backend only


@dataclass(frozen=True)
class ProbeResult:
    """test-provider (9.4): reachability only, no synthesis."""

    reachable: bool
    detail: str | None = None


FailureKind = Literal["unreachable", "rate-limited", "auth", "error"]


class ProviderFailure(Exception):
    """The four failure kinds the engine maps onto §6. `timeout` is not
    here — the 10 s first-token watchdog is the engine's own (4.9)."""

    def __init__(
        self,
        kind: FailureKind,
        *,
        retry_after: float | None = None,  # as the provider stated it; never rounded
        detail: str | None = None,  # engine wording only; filtered, never parsed
    ) -> None:
        super().__init__(kind if detail is None else f"{kind}: {detail}")
        self.kind: FailureKind = kind
        self.retry_after = retry_after
        self.detail = detail


@runtime_checkable
class Provider(Protocol):
    kind: ProviderKind

    def status(self) -> ProviderStatus:
        """Never carries credential material (6.13)."""
        ...

    async def probe(self) -> ProbeResult:
        """Reachability only; no synthesis (9.4)."""
        ...

    def stream(self, req: SynthesisRequest) -> AsyncIterator[str]:
        """Text deltas only. Raises ProviderFailure; the engine classifies."""
        ...


def user_text(req: SynthesisRequest) -> str:
    """The varying half of the prompt, rendered once for every provider —
    a second per-provider renderer is exactly the drift Decision 4 forbids.
    A pre-assembled `user` is returned verbatim (Decision 11); the fallback
    rendering below serves requests built without prompt assembly, in the
    same cache layout: passages → state → history → question."""
    if req.user is not None:
        return req.user
    blocks: list[str] = []
    if req.passages:
        lines = ["## Passages", "Cite with the marker exactly as given."]
        for passage in req.passages:
            lines.append(f"\n[[p:{passage['passage_id']}]]")
            lines.append(passage["text"])
        blocks.append("\n".join(lines))
    if req.state is not None and getattr(req.state, "values", ()):
        lines = ["## Session state", "Observed values — not passages, never citable."]
        for value in req.state.values:
            lines.append(f"- {value.key} = {value.value} (origin: {value.origin})")
        blocks.append("\n".join(lines))
    if req.history:
        blocks.append("## History (context only — not citable)\n" + "\n\n".join(req.history))
    blocks.append(f"## Question\n{req.question}")
    return "\n\n".join(blocks)


def scripted_stream(script: Sequence[str]) -> AsyncIterator[str]:
    """A deterministic delta stream — the stub every non-network test and
    the shared-backend placeholder drive the engine with."""

    async def _stream() -> AsyncIterator[str]:
        for delta in script:
            yield delta

    return _stream()
