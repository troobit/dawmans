"""The incremental line-oriented parser for dawmans/answer-framing/1.

Total over bytes: any input yields a well-formed ParsedAnswer, never
raises, and never emits a partial Citation — no Citation at all, in fact:
the parser carries markers, and ground.py resolves them against the
supplied set (which is what makes 3.6 airtight).

Line 1 is validated against the seven-member content enum. Anything else
is the unparsed path: the whole stream becomes body, direct_answer is the
first sentence, the outcome comes from the engine's coverage signal alone
(answered / refused-not-covered — the one overlap Decision 3 permits),
and nothing is hoisted, because an envelope field read out of a stream
that ignored the framing could contradict the outcome it arrived with.

Block classification is CONTRACTS §4d at column 0. An unknown first line
becomes a paragraph, never dropped (§4b rule 2 applied engine-side), and
!conflict's two-reading arity is a producer obligation checked and
reported through framing — a block already emitted is never re-typed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from dawmans.answer.envelope import (
    Cause,
    Narrowing,
    NarrowingCandidate,
    Outcome,
    SourceRef,
)

# The model-chosen half of CONTRACTS §6 — seven members, validated on
# line 1. outcome.py reuses this set for the same validation.
CONTENT_OUTCOMES = frozenset(
    {
        "answered",
        "partially-answered",
        "needs-narrowing",
        "ranked-causes",
        "refused-not-covered",
        "out-of-domain",
        "no-manual-for-device",
    }
)

SUGGESTIONS_MAX = 3  # 2.3: at most 3, ordered by likelihood

MARKER = re.compile(r"\[\[p:([^\]\s]+)\]\]")
_STEP = re.compile(r"^(\d+)\.\s+(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def markers_in(text: str) -> tuple[str, ...]:
    """Every citation marker's passage_id, in appearance order."""
    return tuple(MARKER.findall(text))


def _without_markers(text: str) -> str:
    return re.sub(r"\s{2,}", " ", MARKER.sub("", text)).strip()


@dataclass(frozen=True)
class Heading:
    text: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderedStep:
    number: int
    text: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Bullet:
    text: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Paragraph:
    text: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Caveat:
    text: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reading:
    text: str
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Conflict:
    text: str
    readings: tuple[Reading, ...] = ()
    markers: tuple[str, ...] = ()  # lead text and readings, in order


Block = Heading | OrderedStep | Bullet | Paragraph | Caveat | Conflict


@dataclass(frozen=True)
class ParsedAnswer:
    """What the parser read out of one provider stream.

    `required_device` is the raw @device name — outcome.py resolves it
    against gaps.owned_but_undocumented. `causes` is the fallback path's
    ?cause hoist; on the entry path the engine builds causes[] from the
    sidecar and the model is not asked (Decision 9).
    """

    outcome: Outcome
    framing: Literal["parsed", "unparsed"]
    direct_answer: str | None
    body: tuple[Block, ...]
    uncovered_parts: tuple[str, ...] | None = None
    narrowing: Narrowing | None = None
    causes: tuple[Cause, ...] | None = None
    required_device: str | None = None
    suggested_sources: tuple[SourceRef, ...] | None = None


class FramingParser:
    """Feed text chunks in arrival order; every complete line is handled
    as it lands, so the turn pipeline can stream deltas while this class
    accumulates the structure. close() flushes, result() reads out.

    `on_body_line` is the streaming seam: it is called with every line that
    lands in `body` — including blank separators and the continuations of a
    multi-line block — and never with a hoisted sigil line or the framing
    header, so a delta emitter built on it cannot leak an envelope field
    into `body_delta`.
    """

    def __init__(self, on_body_line: Callable[[str], None] | None = None) -> None:
        self._on_body_line = on_body_line
        self._buffer = ""
        self._raw: list[str] = []
        self._line_number = 0
        self._hoisting = False  # parsed path only
        self._line_one: str | None = None
        self._direct_answer: str | None = None
        self._blocks: list[Block] = []
        self._uncovered: list[str] = []
        self._suggest_ids: dict[str, None] = {}
        self._device: str | None = None
        self._narrow_question: str | None = None
        self._narrow_candidates: list[str] = []
        self._causes: list[Cause] = []
        self._conflict_violation = False
        self._closed = False
        # Open-block state, exactly one active at a time.
        self._paragraph: list[str] = []
        self._caveat: list[str] | None = None
        self._conflict: tuple[str, list[Reading]] | None = None
        self._collecting_narrow = False
        self._pending_cause: str | None = None

    # -- streaming reads -------------------------------------------------

    @property
    def line_one(self) -> str | None:
        """Line 1 once complete — the outcome token, or the unparsed tell."""
        return self._line_one

    @property
    def hoisting(self) -> bool:
        """Whether line 1 named a content outcome (the parsed path)."""
        return self._hoisting

    @property
    def line_count(self) -> int:
        return self._line_number

    @property
    def direct_answer_line(self) -> str | None:
        return self._direct_answer

    @property
    def raw_text(self) -> str:
        """Everything fed so far — the unparsed path's whole-stream body."""
        return "".join(self._raw)

    # -- feeding ---------------------------------------------------------

    def feed(self, chunk: str) -> None:
        self._raw.append(chunk)
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._line(line.rstrip("\r"))

    def close(self) -> None:
        if self._closed:
            return
        if self._buffer:
            self._line(self._buffer.rstrip("\r"))
            self._buffer = ""
        self._flush_open()
        self._closed = True

    def _line(self, line: str) -> None:
        self._line_number += 1
        if self._line_number == 1:
            self._line_one = line.strip()
            self._hoisting = self._line_one in CONTENT_OUTCOMES
            if self._hoisting:
                return
            # Unparsed path: line 1 is body like everything after it.
            self._body_line(line)
            return
        if self._hoisting and self._line_number == 2:
            self._direct_answer = line.strip() or None
            return
        if self._hoisting and self._line_number == 3 and line.strip() == "---":
            return
        self._body_line(line)

    # -- block machinery -------------------------------------------------

    def _body_line(self, line: str) -> None:
        if not line.strip():
            self._flush_open()
            self._emit_body(line)
            return

        # Continuations of the open multi-line forms come ahead of
        # classification: a `- ` reading belongs to its !conflict, never
        # to a new bullet.
        if self._conflict is not None:
            if line.startswith("- "):
                text = line[2:]
                self._conflict[1].append(Reading(text=text, markers=markers_in(text)))
                self._emit_body(line)
                return
            self._flush_open()
        if self._collecting_narrow and line.startswith("* "):
            self._narrow_candidates.append(line[2:].strip())
            return
        if self._pending_cause is not None and line.startswith("check: "):
            self._close_cause(check=line[len("check: ") :])
            return
        if self._caveat is not None and line.startswith("  "):
            self._caveat.append(line.strip())
            self._emit_body(line)
            return

        if line.startswith("## "):
            self._flush_open()
            text = line[3:].strip()
            self._blocks.append(Heading(text=text, markers=markers_in(text)))
            self._emit_body(line)
            return
        step = _STEP.match(line)
        if step:
            self._flush_open()
            self._blocks.append(
                OrderedStep(
                    number=int(step.group(1)),
                    text=step.group(2).strip(),
                    markers=markers_in(step.group(2)),
                )
            )
            self._emit_body(line)
            return
        if line.startswith("- "):
            self._flush_open()
            text = line[2:].strip()
            self._blocks.append(Bullet(text=text, markers=markers_in(text)))
            self._emit_body(line)
            return
        if line.startswith("!caveat "):
            self._flush_open()
            self._caveat = [line[len("!caveat ") :].strip()]
            self._emit_body(line)
            return
        if line.startswith("!conflict "):
            self._flush_open()
            self._conflict = (line[len("!conflict ") :].strip(), [])
            self._emit_body(line)
            return
        if self._hoisting and self._sigil_line(line):
            return
        # Anything else — including an unknown wrapper, and every sigil on
        # the unparsed path — is paragraph prose, never dropped.
        self._paragraph.append(line.strip())
        self._emit_body(line)

    def _emit_body(self, line: str) -> None:
        if self._on_body_line is not None:
            self._on_body_line(line)

    def _sigil_line(self, line: str) -> bool:
        if line.startswith("~uncovered "):
            self._flush_open()
            self._uncovered.append(line[len("~uncovered ") :].strip())
            return True
        if line.startswith("?narrow "):
            self._flush_open()
            if self._narrow_question is None:
                self._narrow_question = line[len("?narrow ") :].strip()
                self._collecting_narrow = True
            return True
        if line.startswith("?cause "):
            self._flush_open()
            self._pending_cause = line[len("?cause ") :]
            return True
        if line.startswith("@device "):
            self._flush_open()
            if self._device is None:
                self._device = line[len("@device ") :].strip()
            return True
        if line.startswith("!suggest "):
            self._flush_open()
            self._suggest_ids.setdefault(line[len("!suggest ") :].strip())
            return True
        return False

    def _flush_open(self) -> None:
        if self._paragraph:
            text = " ".join(self._paragraph)
            self._blocks.append(Paragraph(text=text, markers=markers_in(text)))
            self._paragraph = []
        if self._caveat is not None:
            text = " ".join(self._caveat)
            self._blocks.append(Caveat(text=text, markers=markers_in(text)))
            self._caveat = None
        if self._conflict is not None:
            lead, readings = self._conflict
            if len(readings) != 2:
                self._conflict_violation = True
            all_markers = markers_in(lead) + tuple(
                marker for reading in readings for marker in reading.markers
            )
            self._blocks.append(Conflict(text=lead, readings=tuple(readings), markers=all_markers))
            self._conflict = None
        if self._pending_cause is not None:
            self._close_cause(check="")
        self._collecting_narrow = False

    def _close_cause(self, check: str) -> None:
        statement = self._pending_cause or ""
        self._pending_cause = None
        cites = markers_in(statement) + markers_in(check)
        self._causes.append(
            Cause(
                rank=len(self._causes) + 1,  # rank equal to emitted order
                statement=_without_markers(statement),
                check=_without_markers(check),
                cites=cites,
            )
        )

    # -- reading out -----------------------------------------------------

    def result(
        self,
        *,
        covered: bool,
        sources: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> ParsedAnswer:
        """The accumulated ParsedAnswer. `covered` is the engine's own
        coverage signal — did anything pass τ — which decides the outcome
        on the unparsed path and nowhere else."""
        self.close()
        if self._hoisting:
            return ParsedAnswer(
                outcome=Outcome(self._line_one),
                framing="unparsed" if self._conflict_violation else "parsed",
                direct_answer=self._direct_answer,
                body=tuple(self._blocks),
                uncovered_parts=tuple(self._uncovered) or None,
                narrowing=self._narrowing(),
                causes=tuple(self._causes) or None,
                required_device=self._device,
                suggested_sources=self._suggestions(sources),
            )
        return ParsedAnswer(
            outcome=Outcome.ANSWERED if covered else Outcome.REFUSED_NOT_COVERED,
            framing="unparsed",
            direct_answer=_first_sentence("".join(self._raw)),
            body=tuple(self._blocks),
        )

    def _narrowing(self) -> Narrowing | None:
        if self._narrow_question is None or not self._narrow_candidates:
            return None
        # The fallback path has no statement/check split to draw on: the
        # model's candidate line is both the label and the value.
        return Narrowing(
            question=self._narrow_question,
            candidates=tuple(
                NarrowingCandidate(label=text, value=text) for text in self._narrow_candidates
            ),
        )

    def _suggestions(
        self, sources: Mapping[str, Mapping[str, Any]] | None
    ) -> tuple[SourceRef, ...] | None:
        # A model-invented id is not an addressable value: anything that
        # does not resolve against sources.json is dropped, and where
        # nothing survives the field is absent — never an empty array (2.5).
        resolved = [
            SourceRef(source_id=source_id, display_name=sources[source_id]["display_name"])
            for source_id in self._suggest_ids
            if sources is not None and source_id in sources
        ]
        return tuple(resolved[:SUGGESTIONS_MAX]) or None


def _first_sentence(text: str) -> str | None:
    flat = re.sub(r"\s+", " ", text).strip()
    if not flat:
        return None
    return _SENTENCE_END.split(flat, 1)[0]


def parse(
    data: bytes | str,
    *,
    covered: bool,
    sources: Mapping[str, Mapping[str, Any]] | None = None,
) -> ParsedAnswer:
    """One whole stream through the incremental parser — total over bytes."""
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    parser = FramingParser()
    parser.feed(text)
    return parser.result(covered=covered, sources=sources)
