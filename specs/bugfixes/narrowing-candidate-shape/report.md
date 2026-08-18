# Bugfix Report: narrowing-candidate-shape

**Date:** 2026-08-18
**Status:** Fixed

## Description of the Issue

The narrowing renderer was broken end to end. `needs-narrowing` is one of the four content outcomes
with its own renderer (ui §6): the engine asks the one question that separates the causes and offers
2–4 candidates, each selectable with a single digit. Against a real engine every candidate control
rendered the literal text `[object Object]`, and selecting one threw
`TypeError: text.trim is not a function` inside `ThreadStore.submit` rather than submitting the
follow-up turn.

**Reproduction steps:**

1. Configure any provider and ask a question that matches an authored triage entry with 2–4 causes,
   so the engine returns `needs-narrowing` on the entry path.
2. Observe the candidate list: each control reads `1 [object Object]`, `2 [object Object]`.
3. Press `1` or `2`, or click a control. Nothing is submitted; the console carries
   `TypeError: text.trim is not a function`.

**Impact:** ui 6.1–6.4 unsatisfiable. A whole outcome renderer produced unreadable controls and no
working selection, so the narrowing loop — the feature that makes a vague symptom answerable in one
keystroke — could not be used at all. The screen-reader announcement (13.5) read the same
`[object Object]` text. The engine, the triage entries and the narrowing construction were correct
throughout; only the browser half was affected.

## Investigation Summary

Found by auditing the rest of the engine/browser seam after the `gap-reports-field-names` fix, whose
report flagged the remaining `client.ts`/`records.ts` boundary types as unverified.

- **Symptoms examined:** the `narrowing` SSE event's payload as the engine serialises it, against the
  type and the consumers on the browser side.
- **Code inspected:** `src/dawmans/answer/narrow.py::build_narrowing`,
  `src/dawmans/answer/envelope.py` (`Narrowing`, `NarrowingCandidate`),
  `src/dawmans/answer/http/app.py::_event_payload`, `web/src/lib/engine/records.ts`,
  `web/src/lib/components/NarrowingView.svelte`, `web/src/lib/components/ThreadView.svelte`, and
  every fixture that emits a `narrowing` event.
- **Confirmed empirically** rather than by reading alone: `asdict(Narrowing(...))` returns
  `{'question': …, 'candidates': ({'label': …, 'value': …},)}`, so the wire payload carries objects.
- **Hypotheses tested and ruled out:**
  - *The engine is the defect.* Ruled out. The `{label, value}` split is specified, not incidental:
    `api/answer-engine` design §Narrowing step 3 fixes "Candidate label is the cause's `check` — an
    observable the user can look at — and its value is the cause `statement`", and decision_log
    Decision 9 records why candidates are engine-built from the triage entry rather than taken from
    model output. Collapsing them to one string would lose the distinction the design exists to
    carry, and would break 7.8's suppression, which matches on a candidate's *value*.
  - *A spec pins `candidates[]` as strings.* Ruled out. `CONTRACTS.md` §4 line 239 gives the payload
    as `{question, candidates[]}` and does not constrain the member shape, so the producer is the
    only authority. The browser had guessed, exactly as it had for the gap reports.
  - *Only the display is wrong.* Ruled out — it is both halves. Display used the whole object, and
    selection passed the whole object to `ThreadStore.submit`, which calls `.trim()` on it.

## Discovered Root Cause

`web/src/lib/engine/records.ts` declared `Narrowing.candidates` as `string[]`. The engine sends
`{label, value}` records. `NarrowingView.svelte` therefore interpolated an object into the button's
text and passed an object to `thread.submit`.

**Defect type:** Interface contract mismatch across a process boundary, masked by self-consistent
test doubles. Same class and same root cause as `gap-reports-field-names`.

**Why it occurred (five whys):**

1. Why did the controls read `[object Object]`? `NarrowingView.svelte` interpolated the candidate
   object directly into the template.
2. Why did it interpolate an object? It was written against a type declaring `string[]`.
3. Why did the type say `string[]`? It was authored from `CONTRACTS.md` §4's `{question,
   candidates[]}`, which does not state the member shape; the member shape is fixed only in the
   `api/answer-engine` design and in `envelope.py`, neither of which the browser side consulted.
4. Why did no test catch it? Every fixture that emits a `narrowing` event — `narrowing.test.ts`'s
   `CANDIDATES`, `answer.test.ts`, `waiting.test.ts`, `turn.test.ts`, `page.test.ts`, and
   `e2e/stub-engine.mjs` — supplied strings, because each was written from the browser's own type.
   The e2e stub is the closest thing to a real engine in the tree and it carried the same error, so
   even the browser suite ran against a fiction.
5. Why is that possible at all? Nothing in the repository compares a browser-side type against a
   payload the engine actually produces. The engine's side of this seam is pinned by its own tests;
   the browser's side is pinned only by fixtures the browser wrote.

**Contributing factors:**

- `string[]` is the shape a reader expects for a list of selectable options, so the type reads as
  correct in isolation.
- Interpolating an object into a Svelte template is not an error — it stringifies — so the failure
  surfaced as content rather than as a crash at the point of the defect.
- The crash it did cause happened one layer away, inside `ThreadStore.submit`, which makes the
  symptom point at submission rather than at the type.

## Resolution for the Issue

**Changes made:**

- `web/src/lib/engine/records.ts:187-203` — `NarrowingCandidate` added as an exported type and
  `Narrowing.candidates` retyped to it, with the label/value contract stated and its source cited.
- `web/src/lib/components/NarrowingView.svelte:37,52` — the control renders `candidate.label`; both
  the digit path and the pointer path submit `candidate.value`.
- `web/src/lib/components/ThreadView.svelte:103-105` — the 13.5 announcement names each candidate's
  `label`, which is what is on screen; announcing the `value` would name text that is not rendered.
- Fixtures corrected to the engine's shape: `narrowing.test.ts`, `answer.test.ts`,
  `waiting.test.ts`, `turn.test.ts`, `page.test.ts`, `e2e/stub-engine.mjs`. In every one the label
  and the value are deliberately *different* strings, so a renderer that confused them fails.
- `web/e2e/surface.spec.ts:54-60` — the browser suite now asserts the control's text as well as the
  submitted question, pinning display-and-submit end to end.

**Approach rationale:** The engine is the producer and its shape is specified by the design and a
decision-log entry; the browser side was unpinned and unspecified, so the browser moves. Rendering
`label` and submitting `value` is the design's own assignment of the two fields, not a choice made
here.

**Alternatives considered:**

- **Flatten to a string in the engine** (send `check` only, or `statement` only). Rejected: it
  destroys a distinction the design requires — the user picks by an observable and the follow-up
  turn re-asks with the cause — and breaks 7.8, whose suppression predicate matches a candidate's
  value.
- **Render `value` on the control and submit it too**, the smallest change that removes
  `[object Object]`. Rejected: it shows the cause statement where the design specifies an
  observable, so the list stops being answerable by looking at the rig — the point of the feature.
- **Accept both shapes** (`typeof candidate === 'string' ? candidate : candidate.label`). Rejected
  for the same reason as in `gap-reports-field-names`: it makes the wire shape permanently
  ambiguous and hides the next drift.

## Regression Test

**Test file:** `web/src/lib/components/narrowing.test.ts`
**Test names:** `renders each candidate by its label, never as a stringified object (6.2)` and
`submits the selected candidate's value as the follow-up question (6.4)`

**What it verifies:** that a `narrowing` event carrying the engine's `{label, value}` members
renders each control with its `label` and never with `[object Object]`, and that selecting the
second candidate submits that candidate's `value` as the follow-up question. Both are written
against an inline engine-shaped payload rather than the module's `CANDIDATES` fixture, since that
fixture is what concealed the drift.

Before the fix the first failed with `expected '1 [object Object]' to contain 'The kick channel
meter is clipping'`, and the second brought down the run with
`TypeError: text.trim is not a function`.

**Run command:** `cd web && pnpm vitest run src/lib/components/narrowing.test.ts`

## Affected Files

| File | Change |
|---|---|
| `web/src/lib/engine/records.ts` | `NarrowingCandidate` added; `Narrowing.candidates` retyped |
| `web/src/lib/components/NarrowingView.svelte` | Renders `label`, submits `value` |
| `web/src/lib/components/ThreadView.svelte` | Announcement names each candidate's `label` |
| `web/src/lib/components/narrowing.test.ts` | Fixture corrected; two regression tests added |
| `web/src/lib/components/answer.test.ts` | Fixture corrected |
| `web/src/lib/components/waiting.test.ts` | Fixture corrected; announcement assertion follows the labels |
| `web/src/lib/engine/turn.test.ts` | Fixture corrected |
| `web/src/routes/page.test.ts` | Fixtures corrected |
| `web/e2e/stub-engine.mjs` | Stub emits the engine's candidate shape |
| `web/e2e/surface.spec.ts` | Asserts the control's label as well as the submitted value |

## Verification

**Automated:**

- [x] Regression tests pass (both failed before the fix, both pass after)
- [x] Full test suite passes — `uv run pytest`: 1399 passed, 7 deselected;
      `cd web && pnpm vitest run`: 428 passed across 23 files;
      `cd web && pnpm test:e2e`: 11 passed
- [x] Linters/validators pass — `make lint`: spelling clean, ruff clean, `svelte-check` 427 files,
      0 errors, 0 warnings

**Manual verification:**

- `asdict(Narrowing(...))` run against the real dataclasses to confirm the wire payload's member
  shape rather than inferring it from the type annotations.
- `grep -rn "candidates: \['" web/src web/e2e` returns nothing: no bare-string candidate fixture
  survives anywhere in the tree.

## Prevention

**Recommendations to avoid similar bugs:**

- **Two of two audited boundary types were wrong.** `gap-reports-field-names` and this one were
  found by reading the producer against the consumer; both were live defects that the whole browser
  suite passed over. The remaining unaudited members of `records.ts` and `client.ts` should be
  treated as suspect until each is compared against a payload the engine actually produces, not as
  probably-fine.
- **The e2e stub is the highest-value place to be correct.** `e2e/stub-engine.mjs` is the only thing
  in the tree that plays the engine for the real components; a wrong payload there makes the entire
  browser suite agree with a fiction. It should be derived from, or checked against, the engine's
  own emissions.
- **State the wire shape where the producer states it.** `CONTRACTS.md` §4's payload column gives
  `{question, candidates[]}` and leaves the member shape to the `api/answer-engine` design. Any
  record whose shape lives only in a design document is one a consumer will guess at.
- **Make a template interpolation of a non-string fail.** `{candidate}` stringifying an object to
  `[object Object]` is what turned a type error into shipped content.

## Related

- `specs/bugfixes/gap-reports-field-names/report.md` — the same root cause, found first.
- `specs/api/answer-engine/design.md` §Narrowing step 3 — label is the cause's `check`, value its
  `statement`.
- `specs/api/answer-engine/decision_log.md` Decision 9 — why candidates are engine-built.
- `specs/ui/ask-and-source-picker/requirements.md` 6.1–6.4 — what the renderer must do.
- `specs/CONTRACTS.md` §4 line 239 — the `narrowing` payload, member shape unconstrained.

## Findings not fixed here

Two further seam findings came out of the same audit. Neither is fixed by this bugfix, and neither
belongs in it.

- **`Citation.hardware_applicability` shape mismatch — a defect, but its resolution crosses the
  seam.** The engine builds a citation's `hardware_applicability` as the source's bare `status`
  string, `"confirmed"` or `"assumed"` (`envelope.py:63`; `ground.build_citation`). `records.ts`
  types it as the `{device?, status}` object that `GET /sources` carries on a *source record*, and
  `CitationEntry.svelte:111` reads `.status` and `.device` off it — both `undefined`, so the
  condition is never true and the inline mark never renders. That breaches ui 5.3. It is not a
  two-line fix: 5.3 requires stating **which hardware revision** the document describes, and the
  engine's citation carries no revision at all, so correcting the type alone would satisfy the
  status half and leave the revision half unmet. Either the engine carries the object onto the
  citation, or the surface resolves the revision from the source record it already holds. That is a
  decision for `CONTRACTS.md` §3 to record, so it wants a spec change, not a bugfix.
- **`manifest_fault` is produced and consumed by nobody — not a bug.** `GET /sources` reports it
  (`app.py:240`) and no browser type declares it, so an unreadable new manifest is invisible while
  the last good view keeps serving. No requirement is breached: ui §9 governs turn outcomes and
  request rejections, and neither design mentions the field. Surfacing it means deciding where it
  renders, what it says, what action 9.2 requires beside it and whether it blocks submission — new
  behaviour, so it belongs in a spec rather than under `specs/bugfixes/`.
