"""The outcome classification procedure (CONTRACTS §6 totality).

§6 is closed — 17 members, 10 engine-determined and 7 content — and every
turn yields exactly one. The engine's members come from two fixed-order
gate chains, first match wins; the content members come from the model's
line 1, validated by the parser against the seven-member enum. The two
sets are disjoint on every path but one: where line 1 is invalid the
engine derives `answered` or `refused-not-covered` from its own coverage
signal, and nothing else (Decision 3).

Ordering inside the in-flight chain is load-bearing. Cancelled is asked
first — a turn both cancelled and failed after partial output classifies
cancelled. Whether output already streamed is asked next, ahead of every
error-kind gate: with the error kinds first, a mid-stream failure would
match "any other provider error" and `incomplete` would be unreachable,
violating 6.10 and leaving UI 9.14 with no producer. Whether output
exists is a property of the turn, not of the error, so it is asked first.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from dawmans.answer.envelope import Outcome, Reason, RequiredDevice, RequiredManual
from dawmans.answer.parse import CONTENT_OUTCOMES

# The provider failure kinds the engine maps onto §6. `timeout` is the
# engine's own 10 s first-token watchdog (4.9); the rest arrive as
# ProviderFailure kinds from the provider seam.
FAILURE_KINDS = frozenset({"unreachable", "rate-limited", "timeout", "auth", "error"})

FailureKind = Literal["unreachable", "rate-limited", "timeout", "auth", "error"]


@dataclass(frozen=True)
class Classified:
    """One gate's verdict: the outcome and its §4 refinements."""

    outcome: Outcome
    reason: Reason | None = None
    retry_after: float | None = None  # unrounded, as the provider stated it
    detail: str | None = None


@dataclass(frozen=True)
class GateState:
    """Everything the pre-flight chain reads, gathered before any
    provider call. `passage_count` is 0 where no manifest is loaded —
    a missing corpus and an empty one gate identically."""

    passage_count: int = 0
    unknown_source_ids: tuple[str, ...] = ()
    selected_count: int = 0  # after 5.11's turn-time prune
    provider_kind: str | None = None
    requires_key: bool = False
    credential_stored: bool = False
    requires_ack: bool = False
    acknowledged: bool = False


def pre_flight(gate: GateState) -> Classified | None:
    """The four pre-flight gates, fixed order, first match wins."""
    if gate.passage_count == 0:
        return Classified(Outcome.CORPUS_EMPTY)
    if gate.unknown_source_ids:
        # 5.3: the unknown id is identified, never silently dropped.
        named = ", ".join(gate.unknown_source_ids)
        return Classified(Outcome.UNKNOWN_SOURCE_ID, detail=f"unknown source id: {named}")
    if gate.selected_count == 0:
        return Classified(Outcome.NO_SOURCES_SELECTED)
    if gate.provider_kind is None:
        return Classified(Outcome.PROVIDER_UNCONFIGURED, reason=Reason.NO_PROVIDER_KIND)
    if gate.requires_key and not gate.credential_stored:
        return Classified(Outcome.PROVIDER_UNCONFIGURED, reason=Reason.MISSING_CREDENTIAL)
    if gate.requires_ack and not gate.acknowledged:
        return Classified(
            Outcome.PROVIDER_UNCONFIGURED, reason=Reason.DISCLOSURE_UNACKNOWLEDGED
        )
    return None


@dataclass(frozen=True)
class Flight:
    """What happened at the provider seam during one turn."""

    cancelled: bool = False
    streamed: bool = False  # ≥1 token reached the caller
    failure: FailureKind | None = None
    retry_after: float | None = None
    provider: str = "provider"
    detail: str | None = None


def in_flight(flight: Flight) -> Classified | None:
    """The six in-flight gates, fixed order, first match wins."""
    if flight.cancelled:
        return Classified(Outcome.CANCELLED)
    if flight.failure is None:
        return None
    if flight.streamed:
        # 6.10: whatever the failure kind. What was streamed is retained
        # and marked; it is never presented as finished.
        return Classified(Outcome.INCOMPLETE, detail=flight.detail)
    if flight.failure == "unreachable":
        # 6.7: the result identifies the provider as well as the kind.
        return Classified(
            Outcome.PROVIDER_UNREACHABLE,
            detail=f"{flight.provider}: {flight.detail or 'connection failed'}",
        )
    if flight.failure == "rate-limited":
        return Classified(
            Outcome.PROVIDER_RATE_LIMITED,
            retry_after=flight.retry_after,
            detail=flight.detail,
        )
    if flight.failure == "timeout":
        # 4.9: the provider is the stalled component, by name.
        return Classified(
            Outcome.TIMEOUT,
            detail=f"{flight.provider} produced no first token within 10 s",
        )
    if flight.failure == "auth":
        # Distinguishable from missing-credential by the sub-code alone
        # (6.6): a key was present and the provider rejected it.
        return Classified(
            Outcome.PROVIDER_ERROR, reason=Reason.AUTHENTICATION_FAILED, detail=flight.detail
        )
    return Classified(
        Outcome.PROVIDER_ERROR, reason=Reason.PROVIDER_REJECTED, detail=flight.detail
    )


def classify(
    gate: GateState, flight: Flight, line_one: str | None, *, covered: bool
) -> Classified:
    """Total over any gate state, any transcript and any line: exactly
    one §6 member, never raised. Content outcomes come only from a valid
    line 1; the framing-unparsed fallback is restricted to the coverage
    pair — the single overlap between the two sets."""
    gated = pre_flight(gate)
    if gated is not None:
        return gated
    flown = in_flight(flight)
    if flown is not None:
        return flown
    if line_one is not None and line_one.strip() in CONTENT_OUTCOMES:
        return Classified(Outcome(line_one.strip()))
    return Classified(Outcome.ANSWERED if covered else Outcome.REFUSED_NOT_COVERED)


def _gap_members(gaps: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    # Members arrive as bare device-id strings or {device, ...} mappings —
    # the corpus never pins the shape (same reading as scope.py).
    members = []
    for member in gaps["owned_but_undocumented"]:
        if isinstance(member, str):
            members.append((member, None))
        else:
            members.append((member["device"], member.get("display_name")))
    return members


def resolve_device(name: str, gaps: Mapping[str, Any]) -> RequiredDevice:
    """2.10: an @device name matching the owned-but-undocumented report
    substitutes the canonical id and rig display name; an unmatched name
    is carried free-form — valid output, not an error. The report is the
    only resolver, empty today and dormant, not removed."""
    wanted = name.strip().casefold()
    for device_id, display_name in _gap_members(gaps):
        if wanted == device_id.casefold() or (
            display_name is not None and wanted == display_name.casefold()
        ):
            return RequiredDevice(device=device_id, display_name=display_name)
    return RequiredDevice(device=name, display_name=None)


def required_manual_for(
    device: RequiredDevice, gaps: Mapping[str, Any]
) -> RequiredManual | None:
    """CONTRACTS §4e: present exactly where the device resolved through
    the report to a canonical <vendor>/<product> id, absent otherwise —
    vendor and product are the two fields no placeholder can stand in
    for. Unknown fields are named placeholders inside the filename, and
    placeholders[] lists exactly those fields."""
    resolved = {device_id for device_id, _ in _gap_members(gaps)}
    if device.device not in resolved or "/" not in device.device:
        return None
    vendor, _, product = device.device.partition("/")
    return RequiredManual(
        filename=f"{vendor}_{product}_<doctype>_v<version>_<lang>.pdf",
        placeholders=("doctype", "version", "lang"),
    )
