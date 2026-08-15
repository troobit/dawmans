"""Term extraction — `data/symptom-triage` 2.6, §The term check.

Two term classes, extracted exactly as that design states them:

- Capitalised runs: maximal sequences of consecutive Capitalised or
  ALL-CAPS tokens (`Track Activator`, `DIRECT MONITOR`).
- Numeric literals with an optional unit (`0 dB`, `44.1 kHz`).

These are the extraction primitives both consumers share, which is what
keeps them from drifting on what counts as a product term: the triage
loader builds its containment check (device-term discards, the
sentence-start rule, case-sensitive matching) on top of them, and
`dawmans.answer.ground` reads them as the fact-shaped signal of its
ungrounded rule. Policy belongs to the callers; extraction lives here.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[A-Za-z0-9][\w.'/-]*")
# Capitalised (Track, Activator) or ALL-CAPS of at least two letters
# (MIDI, DIRECT) — a lone capital is an initial, not a term token.
_CAPITALISED = re.compile(r"[A-Z][a-z0-9'-]*$")
_ALL_CAPS = re.compile(r"[A-Z][A-Z0-9'-]+$")
# A number, not embedded in a word or a dotted identifier, with an
# optional unit token attached (`0 dB`, `44.1kHz`, `-12 dB`).
_NUMERIC = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:\s?[A-Za-z%]+)?")


def capitalised_runs(text: str) -> list[str]:
    """Maximal runs of consecutive Capitalised or ALL-CAPS tokens, in
    order, each returned as its tokens joined by single spaces."""
    runs: list[str] = []
    current: list[str] = []
    for token in _TOKEN.findall(text):
        if _CAPITALISED.fullmatch(token) or _ALL_CAPS.fullmatch(token):
            current.append(token)
        elif current:
            runs.append(" ".join(current))
            current = []
    if current:
        runs.append(" ".join(current))
    return runs


def numeric_literals(text: str) -> list[str]:
    """Numeric literals with any attached unit, in order."""
    return [match.strip() for match in _NUMERIC.findall(text)]
