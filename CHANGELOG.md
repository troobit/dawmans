# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- **`web/src/lib/keys.ts` — the keyboard router and arming registry** (`ui/ask-and-source-picker`
  Phase 4, Decision 5). One `keydown` listener on `window` with the design's decision table:
  modifiers and foreign text-entry targets pass through; `Escape` dismisses the topmost overlay
  region, returning focus to its opener (13.3); digits 1–4 activate an armed entry (1.11); any
  other printable focuses the question input and inserts the character manually — `preventDefault`
  then append, because the keydown already happened elsewhere (1.2). The registry enforces at most
  one armed set by throwing on a second registration, and window focus restores the input unless a
  region holds it (1.1). One recorded deviation: an armed digit fires even when the target is the
  question input, since focus rests there and arming exists only while it is empty — a literal
  pass-through would defeat 1.10/6.3's one-keypress rule.
- **`web/src/lib/state/thread.svelte.ts` — the thread store** (Phase 4). The conversation on
  screen: the composed draft, the turns oldest first, and submission through the scope store's
  block and the turn state machine — whitespace submits contact no engine (1.5), zero scope blocks
  (3.1), the 1000-character limit is enforced client-side (9.15), and the turn is acknowledged
  synchronously before any fetch (8.7). A user stop retains what arrived and ends the turn as
  cancelled, distinct from an engine abandonment (1.9, 8.6, 9.16); a mid-stream transport failure
  is `incomplete` (9.14); request rejections are kept for the broken-state renderer with no
  outcome synthesised. Conversation ids are minted client-side after the first turn of a thread
  (decision log Decision 8); nothing listens to window focus, so leaving costs nothing (1.12).
- **`web/src/lib/components/AskSurface.svelte` — the ask input and symptom shortcuts** (Phase 4).
  Focus lands in the input on load and window focus (1.1); unmodified Enter submits and
  Shift+Enter breaks the line (1.3); the four symptom shortcuts — no sound, distorting, latency,
  wrong drum sound — render on an empty idle input with their armed digits printed, each
  submitting in one keypress via the registry and equally by pointer (1.10, 1.11). A follow-up is
  indicated with a single new-question control that starts a context-free thread (1.7, 1.8); a
  stop control restores the question for re-editing (1.9, 8.6); the zero-scope state offers
  select-all preserving the typed text (3.2) and the over-limit notice states limit and length
  while the question stays editable (9.15).
- **`web/src/lib/components/ThreadView.svelte` — the thread shell** (Phase 4). Turns oldest
  first, each question inspectable and re-editable in one activation (1.4), with a textual
  working/stopped/abandoned/incomplete/broken/finished state line and a plain-text body
  placeholder until the Phase 5 answer renderer.
- **`web/src/lib/testing/turn-channel.ts`** — the stubbed engine shared by the thread and
  component tests: controllable SSE channels carrying the turn-stream version header, wired to
  the abort signal the way a real fetch is.
- **`ui/ask-and-source-picker` decision log Decision 8** — the thread mints its conversation id
  client-side; the engine issues none and `null` remains the specced way to start a conversation.

- **`web/src/lib/state/sources.svelte.ts` — the sources store** (`ui/ask-and-source-picker`
  Phase 3). Available sources of both kinds plus both gap reports from `GET /sources` — no fixed
  source count anywhere, an added or removed source reflected on the next load (2.1, 2.3). Carries
  the owned-but-undocumented report (empty is the live case; the populated path is exercised
  against a fixture, per CONTRACTS §5), the documented-but-unconfirmed report, assumed
  `hardware_applicability` with the revision it describes, and `low_text` (2.9, 2.10). A failed
  `GET /sources` is an `engine-unreachable` state that blocks submission, distinct from
  `corpus-empty` — the engine answering that nothing is ingested (9.13) — and never renders as an
  empty picker.
- **`web/src/lib/state/history.svelte.ts` — the history store** (Phase 3). Persisted exchanges in
  `localStorage`, read lazily on first access so nothing parses on boot inside 8.7's
  acknowledgement budget (12.1). An entry stores the question, the envelope, the citation records,
  the scope at ask time and a timestamp — never passage text; trimmed to the most recent 50 on
  settle, with a `QuotaExceededError` dropping oldest entries until the write succeeds rather than
  failing the turn (12.9). Cancelled and failed exchanges are not retained as answers; a partial
  kept under 9.14 is marked incomplete (12.7).
- **`web/src/lib/engine/client.ts` — the engine client** (`ui/ask-and-source-picker` Phase 2). The
  nine `api/answer-engine` operations as stateless typed wrappers over relative routes — no host,
  no port, no retries. Non-envelope HTTP failures (422 question-too-long, 403 host/origin) throw a
  typed `EngineRejection` carrying the engine's machine-readable `rejected` name, distinct from any
  outcome (9.15). `serveDocumentHref` builds the open-at-source link as the serve-document route
  plus `#page=N` and nothing else (5.5).
- **`web/src/lib/engine/sse.ts` — the SSE turn-stream reader.** Incremental UTF-8 decoding
  (`TextDecoder` with `{stream: true}`) so a multi-byte character split across network chunks never
  paints as U+FFFD; frames reassembled across arbitrary chunk boundaries; a data-less event never
  dispatched. `turnEvents` checks the `dawmans-turn-stream` version header before reading a single
  body byte, refusing an unknown version by naming both (9.19), and reports end-of-stream without
  `done` as an explicit incomplete signal — never a settled turn (9.14). No reconnection and no
  resumption exist.
- **`web/src/lib/engine/blocks.ts` — the append-only block parser** over CONTRACTS §4d's closed
  set (Decision 2). A block's type is fixed by its first line within at most 10 characters and
  never revised across any chunk split; an unknown first line degrades to a paragraph and never
  emits nothing (4.4); a `!conflict` with other than two readings stays the conflict it declared
  itself. Citation markers `[[p:<passage_id>]]` are buffered from `[` until complete or disproved
  and painted immediately as their first-appearance integer, so late citation resolution cannot
  reflow the line (Decision 3); backtick spans become discrete key-term elements.
- **`web/src/lib/engine/turn.svelte.ts` — the event → Turn reducer.** Fills
  `Partial<AnswerEnvelope>` append-only from CONTRACTS §4b's sixteen events, with the citation map
  keyed by `passage_id` and the marker order list. Two compile-time totality guards: every §6
  outcome maps to a renderer (`Record<Outcome, TurnRenderer>`) and every §4b event has exactly one
  handler (a mapped type over `TurnEvent`); an unknown outcome renders broken carrying `detail`
  (9.4) while an unknown event is ignored (9.19) — deliberately opposite rules. End of stream
  without `done` marks the turn incomplete, retaining the partial text.
- **`web/src/lib/state/scope.svelte.ts` — the scope store** (Phase 3, carried with this change):
  selection, persistence and decay per §3, with `sessionStorage` presence as the session boundary
  and the 8-hour clause on `lastQuestionAt` (Decision 4), silent load-time pruning of stale ids
  (3.8), release-with-reinstate (3.6) and the 2.4 admission rule for newly reported sources.

### Fixed

- **`web/vite.config.ts`** — vitest now resolves Svelte's browser entry
  (`resolve.conditions: ['browser']` under `VITEST`), without which component tests fail with
  `lifecycle_function_unavailable`.
- **Web Storage in vitest under Node ≥ 22.** Node's experimental `localStorage`/`sessionStorage`
  globals (lazy getters, undefined without `--localstorage-file`) shadow jsdom's in vitest, which
  skips keys the Node global already owns — so storage was undefined in every test. A
  `vitest-setup.ts` installs an in-memory `Storage` over both globals.

- **`web/` — the browser surface scaffold** (`ui/ask-and-source-picker` Phase 1). A SvelteKit SPA
  built to static assets with `adapter-static` (`ssr = false`, `prerender = true`), for the engine
  to mount at `/` so the page shares its origin (Decision 1). The Vite dev proxy forwards `/turn`,
  `/passages`, `/sources` and `/provider` to `$ENGINE_ORIGIN` and rewrites `Origin` as well as
  `Host` in a `proxyReq` hook, since the engine's rebinding guard rejects a forwarded
  `localhost:5173` origin. Test tooling installed: vitest, @testing-library/svelte, Playwright,
  axe-core. Makefile gains `web-install` / `web-build` / `web-test` and a `make dev` pairing.
- **`web/src/lib/engine/records.ts` — CONTRACTS §1–§4e, §6 and §6a as types**, the only place this
  surface writes them down: `SourceRecord`, `Passage` and `Citation` (the source-kind variants as
  discriminated unions), `AnswerEnvelope`, `Cause`, `required_manual`, the 16-event turn stream,
  the §4d block set, `outcome` as the union of §6's 17 members and `reason` as §6a's five. Absent
  is absent — never empty string, zero or empty array.
- **Design tokens and their enforced floors** (Decision 6). One CSS file of custom properties —
  background, surface, body/secondary text, accent with its 13.8 interactive-state variants, focus
  ring, the four state colours, and the 11.1 type scale — with a unit test computing WCAG contrast
  and luminance from the declared values: body ≥ 7:1, every other text element ≥ 4.5:1, non-text
  indicators and focus ring ≥ 3:1, background luminance ≤ 0.08, and the 11.3-versus-11.5
  resolution held as two enforced bounds (background ≥ 0.03, body text short of maximal white).

- **`data/manual-corpus` task ledger and prerequisites.** 45 tasks over 8 phases, test-then-implement
  throughout, two work streams. `prerequisites.md` records the three things no task can do for
  itself: place the four gitignored PDFs, run `make fetch-model` once, and declare the Focusrite
  applicability mapping.
- **`data/manual-corpus` 11.7 — indexed-but-not-owned.** The ingestion run report names every
  vendor-manual source whose resolved applicability device is not in the rig inventory. Not an
  error: holding a manual for gear you do not own is legitimate. It exists because it is the only
  signal separating that from an **undeclared generation marker**, which puts the device on
  owned-but-undocumented and the source on this line at the same time. That pairing is the
  diagnosis. Recorded as `data/manual-corpus` Decision 9.

### Changed

- **The last corpus gap is closed, and four mechanisms went dormant with it** (DECISIONS Decision
  12). The Focusrite Scarlett Solo 4th Gen guide is ingested, so every device in the rig is
  documented and the owned-but-undocumented report is empty. Nine files still said otherwise:
  - `data/manual-corpus` 11.4, `api/answer-engine` 2.10 / 5.12 / 9.6, `data/symptom-triage`
    2.3–2.4 and `CONTRACTS.md` §2 / §5 each named the Scarlett as the standing undocumented case.
    All four mechanisms stay implemented and are now exercised against a **fixture rig** declaring
    a device with no indexed source; an empty report is emitted as an empty member, never omitted.
  - `required_manual` (§4e) is the sharpest case: its canonical id resolves *only* through that
    report, so the field Decision 11 added to close defect 6 has never been emitted. Governed,
    implemented, unverified against a real payload — and reachable again the moment a device is
    declared ahead of its manual.
  - `symptom-triage`'s worked example illustrated an unbacked cause with "check DIRECT MONITOR",
    a control the newly ingested guide documents. That cause moves from the unbacked side of the
    rule to the backed side, and the payload example, scope table and fixture list move with it.
- **DECISIONS Decision 2 resolved against itself.** It said `product` "carries the generation where
  that distinguishes the hardware" and then gave `apc-key-25` — whose mk1 and mk2 differ exactly
  there — as an example. The rule now follows the *vendor*: the marker appears where the vendor
  sells it as part of the name (`scarlett-solo-4g`) and not otherwise (`apc-key-25`). Putting the
  generation in the id instead was rejected because it breaks Decision 9: an mk1 guide and an mk2
  device would hold different ids, never meet, and documented-but-unconfirmed could not fire on the
  mismatch it exists to catch.
- The consequence is that `<vendor>/<product>` is **not reliably the rig's device id**. The gap
  reports already joined on a declared `source_applicability.device` rather than on the id, so this
  works — but the 11.2 default does not, and an undeclared Focusrite resolves to a device no rig
  entry holds. Declaring the mapping is now mandatory, and 11.7 catches the omission.
- `manuals/README.md`: the "adding a manual" walkthrough said version 3 where the table says v4.0,
  and omitted the `rig.yaml` step that a generation-marked filename requires.
- `prerequisites.md` listed three PDFs and the Alesis at v1.0 where the tracked record says v1.1.
- **`specs/CONTRACTS.md` amended to close all six open cross-spec defects** (DECISIONS
  Decision 11). Each had been found from both ends of its seam. New governing sections:
  - §3a **Open at source** — the action is mediated by the engine, never by the browser's
    own filesystem access, because a tab served over `http://` cannot navigate to `file://`
    in any current engine and the refusal is silent, making such a control dead rather than
    unavailable. A vendor manual is served same-origin and opened at `#page=N` and nothing
    else; an authored entry is revealed in place through the existing fetch-passage
    operation, with `entry_location` copyable. The engine resolves every target from
    `source_id` — no caller supplies a path, and the index is the allowlist.
  - §4b **the turn stream** — sixteen named events with ordering, a version token, and both
    halves of the unknown-member rule, so a streamed seam is governed like a record.
  - §4c `Cause`, §4d `body` block types, §4e `required_manual`, §6a **reason vocabulary**.
  - §6 gains `ranked-causes` (17 members) with an explicit rule: the taxonomy may be amended
    but never grown to encode a *refinement* of an existing member — that is what `reason` is
    for.
- `Passage` and `Citation` gain `entry_location`; `AnswerEnvelope` gains `reason`,
  `retry_after`, `detail`, `framing`, `causes[]`, `required_manual` and `scope_dropped[]`.
  Each has a named consumer criterion, so none repeats the produced-but-unconsumed defect
  the amendment exists to close.
- All four specs reconciled against the amended contract — 10 new criteria across
  `api/answer-engine` (111), `ui/ask-and-source-picker` (154) and `data/manual-corpus` (83).
- The triage sidecar now lives at `views/<hex>/reports/<slug>.json`, inside the view, so it
  and the passages it keys always share a revision. Ingestion audits stay at
  `index/audits/<slug>.json`: an audit describes a *run* and must outlive the view it
  accompanied, whereas a sidecar describes *the passages in a view*. The run-side directory
  is renamed to avoid two files at the same basename differing only in parent, which fails
  silently rather than erroring. This discharges the blocking prerequisite on the answer
  engine (manual-corpus Decision 8).

### Added

- `ui/ask-and-source-picker` design and decision log (7 ADRs) — the fourth and last design.
  A SvelteKit SPA served same-origin by the answer-engine process; append-only streaming
  with block type fixed by a block's first line (4.2); one window-level keyboard router
  owning the 1–4 arming rule (1.11); numeric citation markers with detail in a list, so
  CONTRACTS §3's five inline obligations fit inside the 25-word reading budget (11.7).
- `data/manual-corpus` criteria 8.8–8.11 defining what "a queryable index" means — both
  kinds of matching over the same passages, every `Passage` and `SourceRecord` field
  readable without a source PDF, restriction to a chosen subset of sources, and
  self-describing artefacts. Closes the requirements gap that design named as defect 3.
- `api/answer-engine` decision log entries 8–10: count the history token budget locally
  rather than with a provider endpoint; build narrowing candidates in the engine from the
  triage entry rather than from model output; filter triage fix pointers through the turn's
  source scope, carrying an out-of-scope cause as `unbacked`.
- A *Requirements defects to reconcile* section in the `api/answer-engine` design, matching
  its two sibling designs. Six open contract defects, each found from both ends of its seam.

### Fixed

- `api/answer-engine` design, repaired against two independent reviews:
  - History token counting used `client.messages.count_tokens`, a provider HTTP endpoint —
    an unbudgeted round trip inside the 150 ms engine-overhead cap that also broke 6.14's
    no-outbound-request guarantee on a local provider and bypassed 6.15's disclosure gate.
  - Triage fix pointers were admitted to the grounding set with no scope check, so a
    triage-only scope injected passages from deselected sources, breaking 1.1, 2.4 and 5.1
    and corrupting `contributing_sources[]`.
  - The triage sidecar was read as `authored-triage.json`; the corpus writes
    `authored_triage.json`. `data/symptom-triage` names this exact spelling as a silent
    failure leaving every entry in scope for every turn. Now derived by the slug rule and
    failing loudly when absent.
  - `incomplete` was unreachable: a mid-stream failure matched the "any other provider
    error" gate first. Gates are now split pre-flight and in-flight, with "has any output
    been streamed" evaluated ahead of every error-kind gate.
  - The loopback `Origin` guard rejected the browser surface's own origin. Resolved by
    serving the built surface same-origin, with the dev proxy rewriting `Origin` as well
    as `Host`.
  - Retrieval masked after top-k rather than before it; the lexical relevance arm and
    per-source qualification were global, so a small guide beside the 1009-page Live manual
    could never fire 5.6's floor.
  - Device scope had no defined value for the `authored-triage` source, so a triage-only
    turn filtered out its whole starter set.
  - `GET /passages/{id}` read a stale view after a re-ingest, breaching 3.5.
  - Outcome arithmetic: sixteen outcomes, ten engine-determined and six content — not
    seventeen and eleven — in both the design and Decision 3.
  - The 3.7 ungrounded rule missed uncited procedure steps, which 3.1 counts as substantive.
  - `timings` carried a parser status; `framing` is now its own event and `timings` carries
    the five stages 4.11 names.
  - Dangling `§Outcome` reference, and the inverted claim that the state timeout was the
    shortest member of the `asyncio.gather`.
- `specs/OVERVIEW.md` regenerated: it still recorded all four specs as "requirements
  complete, design not started" when three designs existed.

### Added

- DAWMans MVP requirements: four specs totalling 398 anchored EARS criteria —
  `data/manual-corpus` (vendor PDF ingestion into a citable corpus),
  `data/symptom-triage` (an authored symptom-to-cause source), `api/answer-engine`
  (retrieval, grounding, providers, the `StateSource` seam) and
  `ui/ask-and-source-picker` (the localhost browser surface).
- `specs/CONTRACTS.md` — governing shared contracts for the spec seams: the
  `SourceRecord`, `Passage`, `Citation` and `AnswerEnvelope` records, a closed outcome
  taxonomy, and a composed end-to-end latency budget.
- `specs/DECISIONS.md` (9 ADRs) and a generated `specs/OVERVIEW.md` index.
- Research notes in `docs/agent-notes/` for Ableton state integration and the retrieval
  approach, both verified by measurement on the target machine.
- `manuals/` for the reference PDFs, with the filename convention documented; the PDFs
  themselves are gitignored as third-party and not redistributable.

### Added (template)

- Machine entry points for external tools such as sdd-ui (`specs/template-refinement/prd.md`):
  `tools/new_project.sh` / `make new-project` for non-interactive project creation from the
  template (placeholder filling, `nextup.md` intent seeding, git init, optional worked-example
  removal), and `tools/status.sh` / `make status` for a plain-English or `--json` summary of
  where a project stands.

### Changed

- `nextup.example.md` now uses the canonical `<!-- USER -->` / `<!-- LM -->` zone markers and
  documents the `act autonomously` flag; README gained a "Machine entry points" section.
