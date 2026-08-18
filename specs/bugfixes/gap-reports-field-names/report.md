# Bugfix Report: gap-reports-field-names

**Date:** 2026-08-18
**Status:** Fixed

## Description of the Issue

The browser surface never rendered either gap report. `GET /sources` carries the
owned-but-undocumented and documented-but-unconfirmed reports of `CONTRACTS.md` §5, and the picker
is required to surface both — owned hardware with no ingested manual as a known, non-selectable gap
(ui 2.9), and a source whose `hardware_applicability` is `assumed` as a marked source (ui 2.10).
Against a real engine both arrays arrived `undefined`, so the known-gaps block never appeared and
the unconfirmed mark never rendered.

**Reproduction steps:**

1. Ingest a corpus in which `rig.yaml` declares a device with no manual (the shipped rig declares
   the Akai APC Key 25 mk2 against a Manual Version 1.0 guide, giving a populated
   documented-but-unconfirmed report).
2. `make serve`, open `http://127.0.0.1:8722`, expand the source picker.
3. Observe: no known-gaps block, no unconfirmed mark on the APC source. `curl
   http://127.0.0.1:8722/sources` shows both reports populated in the response body.

**Impact:** Silent, permanent loss of two required UI affordances. No error surfaces anywhere —
the two arrays are read off a parsed JSON object, so a missing key is `undefined` rather than a
throw, and `SourcePicker.svelte:161` guards on `.length > 0`, which `undefined` fails without
complaint. Nothing else on the surface degrades, so the omission is invisible unless the
`/sources` payload is compared against the picker by hand. The engine, the corpus and the rig join
were all correct throughout; only the browser half was affected.

## Investigation Summary

Found while verifying field names for the README rewrite, by reading the producer and the consumer
side by side rather than by a failing test.

- **Symptoms examined:** the response `answer/http/app.py::list_sources` builds versus the object
  `web/src/lib/state/sources.svelte.ts::load` reads.
- **Code inspected:** `src/dawmans/answer/http/app.py` (producer),
  `src/dawmans/corpus/rig.py::GapReports.to_dict` (the corpus's own publication),
  `src/dawmans/answer/scope.py` and `outcome.py` (the engine's other readers of the same keys),
  `web/src/lib/engine/client.ts` (`SourcesResponse`), `web/src/lib/state/sources.svelte.ts`,
  `web/src/lib/components/SourcePicker.svelte`, and every fixture that stubs `GET /sources`.
- **Hypotheses tested and ruled out:**
  - *The engine is the defect.* Ruled out. `rig.py` publishes `owned_but_undocumented` and
    `documented_but_unconfirmed` into `gaps.json`; `app.py` relays those keys verbatim, which is
    the documented intent ("relayed from the corpus's own publication, never derived here"); the
    engine's other readers (`scope.py:31`, `outcome.py:151`) use the same names; and
    `tests/answer/test_http_sources.py` already pins the response keys. Renaming the engine would
    have required a translation layer at the relay and a change to the corpus's published
    `gaps.json`, breaking three passing test modules to accommodate one unverified type.
  - *A spec pins the shorter names.* Ruled out. Neither `CONTRACTS.md` §5, the `api/answer-engine`
    design route table (line 795), nor the `ui/ask-and-source-picker` design names the JSON keys —
    they name the reports in prose only. The producer is therefore the only authority, and the
    consumer had simply guessed.
  - *A recent rename broke it.* Ruled out. `git log -S owned_undocumented -- web` bottoms out at
    `c018a7f` ("Implement the engine client and the turn stream", ui phase 2); the engine's names
    arrived in `16bed48` (answer-engine phase 8). The two never agreed — this is original, not
    regression.

## Discovered Root Cause

`web/src/lib/engine/client.ts` declared the `GET /sources` gap reports as `owned_undocumented` and
`documented_unconfirmed`. The engine emits `owned_but_undocumented` and
`documented_but_unconfirmed`. `SourcesStore.load` therefore assigned `undefined` to both fields on
every load.

**Defect type:** Interface contract mismatch across a process boundary, masked by self-consistent
test doubles.

**Why it occurred (five whys):**

1. Why did the gap reports not render? The store's `ownedUndocumented` and `documentedUnconfirmed`
   were `undefined`.
2. Why were they `undefined`? `SourcesStore.load` read keys the response does not carry.
3. Why did it read the wrong keys? `SourcesResponse` in `client.ts` declared the abbreviated names,
   and TypeScript validates a `fetch` result against a declared type by assertion, not by checking
   it — a JSON body is `any` at the boundary, so a wrong key is not a compile error.
4. Why did no test catch it? Every fixture that stubs `GET /sources` — `fake-server.ts`,
   `e2e/stub-engine.mjs`, and the `payload()` helper in three separate test modules — was written
   from `SourcesResponse` rather than from the engine's payload. The doubles agreed with the type
   that was wrong, so all 425 unit tests and 11 browser tests passed over the defect.
5. Why was there no test against the real payload? The two halves are developed and tested
   independently by design (separate suites, separate languages, a stub engine for e2e), and
   nothing existed to pin the wire shape at the seam. The engine's side was pinned
   (`tests/answer/test_http_sources.py`); the browser's side was not.

**Contributing factors:**

- Both spellings read naturally, and the shorter one is the more idiomatic identifier — the drift
  is not visible on inspection of either file alone.
- The failure mode of a mismatched key in JS is `undefined`, not an error, and both consumers of
  these values are `.length > 0` guards, which absorb `undefined` silently.
- The reports are legitimately empty in the reference rig's owned-but-undocumented arm, so "nothing
  rendered" was an expected sight for one of the two.

## Resolution for the Issue

**Changes made:**

- `web/src/lib/engine/client.ts:70-74` — `SourcesResponse` renamed to the engine's field names,
  with a comment stating that the names are the engine's and that abbreviating either yields
  `undefined`.
- `web/src/lib/state/sources.svelte.ts:74-75` — reads the corrected fields.
- `web/src/lib/testing/fake-server.ts:40-41`, `web/e2e/stub-engine.mjs:56-57` — the stub engines now
  answer with the field names the real engine sends.
- `web/src/lib/state/sources.test.ts`, `web/src/lib/components/picker.test.ts`,
  `web/src/routes/page.test.ts`, `web/src/lib/engine/client.test.ts` — fixture payloads corrected.
- `web/src/lib/state/sources.test.ts` — regression test added (below).
- `docs/agent-notes/web-surface.md` — records the drift, and that any `client.ts` field name not
  compared against an engine-shaped payload is unverified.

**Approach rationale:** The engine is the producer, its names come from the corpus's own published
`gaps.json`, three engine modules read them, and an existing test pins them. The browser half was
the only unpinned side, so it is the side that moves. This also keeps the relay honest: `app.py`
passes the corpus's keys through untouched rather than renaming at a boundary.

**Alternatives considered:**

- **Rename in the engine to the shorter form.** Rejected: it would require renaming
  `GapReports.to_dict`'s keys in `gaps.json` (a persisted, versioned artefact read back by
  `scope.py` and `outcome.py`), or introducing a translation in `list_sources` that contradicts the
  route's documented "relayed verbatim, never derived here" property.
- **Accept both spellings in the store** (`response.owned_but_undocumented ?? response.owned_undocumented`).
  Rejected: it makes the wire shape permanently ambiguous, hides the next drift instead of failing
  on it, and there is no deployed client needing compatibility — the surface is served by the engine
  it talks to.
- **Generate the TypeScript types from the Python records.** Rejected as disproportionate for a
  two-field defect and a larger change than the bug warrants, though it remains the systemic answer
  if the seam drifts again (see Prevention).

## Regression Test

**Test file:** `web/src/lib/state/sources.test.ts`
**Test name:** `reads both reports under the field names the engine actually emits`

**What it verifies:** that a `GET /sources` body written in the engine's own field names populates
`store.ownedUndocumented` and `store.documentedUnconfirmed`. The payload is constructed inline
rather than through the module's `payload()` helper — the helper is the fixture that concealed the
drift, so the pin has to state the wire names itself. Before the fix it failed with
`expected undefined to deeply equal [ { device: 'roland/tr-8s', … } ]`.

**Run command:** `cd web && pnpm vitest run src/lib/state/sources.test.ts`

## Affected Files

| File | Change |
|---|---|
| `web/src/lib/engine/client.ts` | `SourcesResponse` field names corrected; comment added naming the trap |
| `web/src/lib/state/sources.svelte.ts` | Reads the corrected fields |
| `web/src/lib/testing/fake-server.ts` | Stub payload uses the engine's names |
| `web/e2e/stub-engine.mjs` | Stub payload uses the engine's names |
| `web/src/lib/state/sources.test.ts` | Fixtures corrected; regression test added |
| `web/src/lib/components/picker.test.ts` | Fixtures corrected |
| `web/src/routes/page.test.ts` | Fixtures corrected |
| `web/src/lib/engine/client.test.ts` | Fixtures corrected |
| `docs/agent-notes/web-surface.md` | Records the drift and the unverified-field-name rule |

## Verification

**Automated:**

- [x] Regression test passes (failed before the fix, passes after)
- [x] Full test suite passes — `uv run pytest`: 1399 passed, 7 deselected;
      `cd web && pnpm vitest run`: 426 passed across 23 files;
      `cd web && pnpm test:e2e`: 11 passed
- [x] Linters/validators pass — `make lint`: spelling clean, ruff check and format clean,
      `svelte-check` 427 files, 0 errors, 0 warnings

**Manual verification:**

- Read the producer (`app.py::list_sources`) and consumer (`sources.svelte.ts::load`) against each
  other after the change; the four key names now agree.
- `grep -rn "owned_undocumented\|documented_unconfirmed" web/src web/e2e` returns only the comment
  in `client.ts` that names the abbreviated form as the mistake.
- The Playwright browser had to be installed on this machine (`pnpm exec playwright install
  chromium`) before the e2e suite could run at all; its 11 failures before that were the missing
  executable, not this change.

## Prevention

**Recommendations to avoid similar bugs:**

- **A test double is not evidence.** Any assertion about the engine's wire shape that is satisfied
  only by a fixture this side wrote proves the fixture, not the engine. Pin at least one payload per
  route in the engine's own terms, written by reading the producer.
- **Audit the rest of the seam.** This fix pins one route. `TurnRequest`, `ProviderStatus`,
  `ProviderTest`, `Passage` and `SourceRecord` in `client.ts` and `records.ts` carry the same class
  of risk, and `manifest_fault` is a live instance of the adjacent problem: the engine emits it on
  `GET /sources` and the browser declares no field for it and renders nothing, so an unreadable new
  manifest is currently invisible to the user. Worth its own spec item rather than a silent
  addition here.
- **Consider generating the boundary types.** The systemic fix is one source of truth for the wire
  records — records generated from the Python dataclasses, or a shared JSON fixture both suites
  load. Disproportionate for this defect; the right response if the seam drifts a second time.
- **Prefer a shape that fails loudly.** A parse step that rejects an unexpected `GET /sources` body
  would have turned this into an `engine-unreachable` state on the first run instead of two silently
  absent features.

## Related

- `specs/CONTRACTS.md` §5 — the two gap reports.
- `specs/ui/ask-and-source-picker/requirements.md` 2.9, 2.10 — what the picker must render.
- `specs/api/answer-engine/requirements.md` 9.6, 9.7 — what the engine must report.
- `tests/answer/test_http_sources.py::TestListSources` — pins the engine's field names.
- `docs/agent-notes/web-surface.md` — the store's entry now records this.
