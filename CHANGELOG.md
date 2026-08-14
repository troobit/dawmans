# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- **The local HTTP surface** (`api/answer-engine` phase 8, `dawmans/answer/http/guard.py` and
  `dawmans/answer/http/app.py`). `guard.py` holds the two 9.1–9.3 guards: `ensure_loopback_bind`
  refuses a non-loopback bind before uvicorn exists — exiting non-zero naming the address and the
  constraint, no fallback bind — and `HostOriginGuard` is the pure-ASGI middleware rejecting any
  request whose `Host` is not the loopback service with the port (the check that closes DNS
  rebinding) or whose `Origin` falls outside the same set, including `null` and the cross-port
  dev-server origin; rejection is 403 with a machine-readable reason and no `outcome`. `app.py`
  carries the design's route table: `GET /passages/{id}` as a dict lookup routed on the source_id
  prefix running the same stat change check as a turn (3.4), `GET /sources` relaying every 9.5
  field for both kinds plus both gap reports verbatim — owned-but-undocumented as an empty list,
  never an omission (9.6–9.7) — and reporting an unreadable new manifest as a fixed notice with no
  filesystem path in any payload; the five provider operations over a new `ProviderRegistry`
  (masked-only throughout per 9.8, shared-backend selection recording nothing until the 6.15
  disclosure is acknowledged, credential changes re-constructing the keyed provider so 6.3 holds,
  test-provider probing reachability without synthesising a turn); serve-document rebuilding
  `<vendor>_<product>_<doctype>_v<doc_version>_<lang>.pdf` from the record's own fields,
  realpath-confined to the manuals root, served inline with Range honoured and no
  Content-Disposition filename so `#page=N` survives (9.4); and `POST /turn` streaming the
  CONTRACTS §4b sixteen-event set over SSE with per-event payload mapping, `done` carrying
  `{"complete": true}` (9.14), the `dawmans/turn-stream/1` version header plus the minted
  conversation id readable before the first body byte (9.15), the 9.12 over-length rejection as a
  422 with no outcome and no turn started, and the `web/build` static mount that makes the surface
  same-origin. A caller disconnect now cancels the turn deterministically (9.10): the response
  finalises its body iterator, the encoder closes the turn generator, `TurnPipeline._run` closes
  its inner event generator, and the provider release cancels an in-flight `anext` before
  `aclose` — previously the provider stream was only released at garbage collection. Tests cover
  the guard matrix, the gap relay, credential masking against captured logs, filename round-trip
  and confinement probes, stream completeness against the pipeline's own event sequence, §4b
  ordering on the wire, and incremental delivery and disconnect at the raw ASGI layer.
- **Conversation and the turn pipeline** (`api/answer-engine` phase 7,
  `dawmans/answer/conversation.py` and `dawmans/answer/turn.py`). `conversation.py` holds one
  conversation's in-memory state: the last 6 content-outcome turns rendered for the prompt's
  context-only history block (10.1), the carried scope with display names captured at set time so
  5.11's turn-time prune can report a source the view no longer names, the per-symptom
  consecutive-narrowing counter that 7.5's terminal direction rides on (incremented by
  needs-narrowing, reset by an answer, untouched by engine failures), and 7.4's follow-up query
  assembly — a turn answering a narrowing question retrieves with the original symptom question
  plus the answer, never the previous turn's passages, and there is structurally nowhere to retain
  a passage. `turn.py` is the pipeline the design pins there: retrieval under `asyncio.to_thread`
  gathered with `StateSource.snapshot` under `wait_for(0.100)` so the state task genuinely runs
  alongside synchronous numpy work (4.4, 8.9), the pre-flight and in-flight gates, engine-side
  narrowing/`causes[]` construction on the entry path with back-filled citations and the per-turn
  `unbacked` reading, prompt assembly carried to providers as the new pre-rendered
  `SynthesisRequest.user` (Decision 11 — the roster and the terminal direction reach every
  provider through the one renderer), the 10 s first-token watchdog naming the provider (4.9),
  supersede-based per-conversation cancellation whose old stream emits `outcome: cancelled` then
  `done` before the new one opens with the provider released by a close, not a drain (4.10, 9.13),
  incremental §4b event emission with unresolvable markers stripped from the streamed text,
  mid-stream failure degrading to `incomplete` with the partial retained (6.10), state faults
  degrading to manual-only with the note logged (8.8 — the closed event set has no field for it),
  supplied-derived `contributing_sources[]` (5.9), and `timings` as durations only for the five
  stages (4.11). `parse.py` gains the streaming seam (`on_body_line` plus read-only header
  properties) so deltas can flow without envelope fields leaking into `body`. Tests cover the
  concurrency shape by wall clock, every degradation path, the watchdog, the cancellation
  property over arbitrary stream prefixes, provider switching without restart, cross-source
  citation with the small guide under the floor, and the scope prune to `no-sources-selected`.
- **Providers, credentials and the state seam** (`api/answer-engine` phase 6,
  `dawmans/answer/provider/` and `dawmans/answer/state/`). `provider/base.py` defines the seam:
  `ProviderKind` with `requires_key` derived from the kind (6.4), the verbatim `SynthesisRequest`
  with `max_words` fixed at 400, the masked-only `ProviderStatus` (no field can hold a full key),
  the four-kind `ProviderFailure`, the `Provider` protocol whose `stream()` yields text deltas and
  nothing else (Decision 4), and the single shared user-prompt renderer that keeps 6.2 structural.
  `provider/anthropic.py` drives `AsyncAnthropic` against `claude-opus-5` with the pinned settings
  table — thinking disabled at effort low, `max_retries=0`, a 30 s / 2 s-connect timeout so the
  engine's watchdog fires first, `cache_control` on the last system block — the single-retry
  rate-limit policy (retry only a stated interval ≤ 3 s, before any output, the value unrounded on
  both branches and absent when unstated), connection/auth/status errors mapped to the failure
  kinds, and `prompt_cache: unavailable` reported for models whose cache minimum the system prompt
  does not clear. `provider/local.py` is an OpenAI-compatible httpx client that refuses any
  non-loopback base URL at construction, so 6.14 holds by construction; `provider/shared.py` is
  the stub behind the 6.15 disclosure gate. `provider/credentials.py` stores keys in the macOS
  Keychain via keyring under service `dawmans`, account `anthropic` (Decision 6), returns only the
  last-4 masked form on every read path but the client constructor, and ships the secret-dropping
  `logging.Filter` whose predicate also scrubs CONTRACTS §4 `detail`. `state/base.py` and
  `state/null.py` land the flat `StateValue` triple (Decision 7), `StateSnapshot`, the
  `StateSource` protocol and the immediate-empty `NullStateSource` (8.3). Tests cover the pinned
  SDK settings, the rate-limit branches, failure-kind mapping, loopback-by-construction with
  networking poisoned, the disclosure gate, the same envelope shape through all three provider
  classes, and credential storage/masking with keyring stubbed (the live Keychain path runs on a
  developer machine only, per `prerequisites.md`). `httpx` is now an explicit member of the
  `serve` extra.
- **Prompt, parser, grounding and the outcome procedure** (`api/answer-engine` phase 5,
  `dawmans/answer/prompt.py`, `parse.py`, `ground.py`, `outcome.py` and the new
  `dawmans/triage/terms.py`). `prompt.py` assembles the turn in cache order — the static system
  prompt as the cache prefix (framing spec, no-uncited-facts rule with the facts-versus-reasoning
  split, length caps, edition caveat, kind trust split, refusal and out-of-domain directions with
  2.9's authored-entry carve-out, the no-XML instruction and no "do not think" anywhere), then
  passages, the metadata-only unselected-source roster, the labelled uncitable state and history
  blocks and the question — with history bounded oldest-first to 800 tokens at a 10% margin by an
  injected local tokeniser (Decision 8, no provider SDK call before `stream()`), and the narrowing
  counter carried into assembly at the limit (7.5). `parse.py` is the incremental line-oriented
  parser for `dawmans/answer-framing/1`: total over bytes, line 1 validated against the
  seven-member content enum with the unparsed fallback restricted to the coverage pair, §4d block
  typing at column 0 with unknown lines degrading to paragraphs, `!conflict` arity reported
  through `framing` without re-typing, and sigil hoists (`~uncovered`, `?narrow`, `?cause` with
  rank from emitted order, `@device`, `!suggest` resolved against sources.json — at most 3,
  absent when none survives). `ground.py` makes 3.6 structural: citations assemble only from the
  supplied set, unknown markers are stripped and counted, the field copy emits absent as absent
  on pageless sources, and the two-arm ungrounded rule (fact-shaped tokens via the reused
  `dawmans.triage.terms` extraction primitives, plus uncited ordered steps) executes the
  CONTRACTS §8 split. `outcome.py` classifies every turn totally and disjointly: four pre-flight
  and six in-flight gates in fixed order (cancelled ahead of incomplete, incomplete ahead of
  every error kind, 401 as `authentication-failed` distinguishable from `missing-credential` by
  sub-code alone), plus the `required_device` resolver over the gaps report and `required_manual`
  assembly with named placeholders — absent where the device does not resolve. 107 tests
  including totality, disjointness, round-trip and non-citability properties.
- **Narrowing from triage entries** (`api/answer-engine` phase 4, `dawmans/answer/narrow.py`).
  The engine-built entry path of Decision 9: `matched_entry` finds the first supplied passage
  keying the triage sidecar, `expand_entry` takes the entry's first ≤ 4 causes in the author's
  order and resolves each cause's fix pointers against the view — filtered through the turn's
  source scope (Decision 10), bounded over resolved passages rather than pointers at the
  12-passage cap, with excess dropped in cause order and within a cause in section order, and
  passages retrieval already supplied cited without re-admission. `build_narrowing` constructs
  the 7.2 candidate list (label from `check`, value from `statement`, no reorder/merge/add) with
  7.8's state-value suppression behind a caller-supplied predicate, asking nothing when fewer
  than two candidates survive; `build_causes` builds the 7.6 terminal `causes[]` with positional
  ranks, the entry passage as `cites[]`, and scope-filtered `fix_cites[]` — empty `fix_cites[]`
  reads as unbacked for the turn (the engine reads the authored flag, never sets it), and
  out-of-scope holding sources are named for 2.3's suggestion path. 20 tests cover the
  provenance, scope, bound, suppression and terminal-form properties.
- **Retrieval and scoping** (`api/answer-engine` phase 3, `dawmans/answer/scope.py` and
  `dawmans/answer/retrieve.py`). `device_scope` derives the turn's device scope over source kind —
  the selected vendor manuals' `hardware_applicability.device` unioned with the
  owned-but-undocumented gaps, widening to every indexed vendor-manual device when no vendor
  manual is selected — and `in_device_scope` is 5.13's predicate: a passage declaring devices
  disjoint from the scope is excluded from the turn entirely, a filter and never a ranking input.
  `candidate_pool` runs the design's retrieval order — BGE query-prefix embed, candidate mask
  (selected row slices minus device-filtered rows), masked dense and lexical rankings, RRF fusion
  at k=10 — with masking *preceding* top-k on both retrievers so out-of-scope rows never consume
  the depth-50 slots. `retrieve` applies the two-arm relevance threshold (cosine ≥ 0.30, or BM25
  rank 1 *within its own source* sharing a query term of document frequency ≤ 5%) with both
  constants as configuration, per-source qualification, and Decision 5's allocation: one floor
  slot per qualifying source, remaining slots by fused rank, cap `max(8, |qualifying|, 12 on a
  narrowing expansion)`. No qualifying in-scope candidate means the turn is uncovered per 2.1.
  38 tests cover the scope derivation, the mask-precedes-top-k behaviour, the fusion
  monotonicity/invariance/decisiveness properties Decision 1 rests on, the threshold arms and the
  floor/cap precedence property.
- **The corpus view** (`api/answer-engine` phase 2, `dawmans/answer/view.py`). `CorpusView` loads
  one immutable revision of the merged index view in the design's load order — manifest first,
  refusing to serve on an `index_version` the engine cannot interpret — then mmaps `vectors.npy`
  and reads `passages.jsonl`, `lexical/`, `sources.json`, `gaps.json` and the triage sidecar.
  Source scoping is a row slice from `manifest.sources`, not a scan. The sidecar filename is
  derived by the slug rule from the `authored/triage` constant, never spelled; a view whose
  sidecar is missing (e.g. hyphenated) fails loudly rather than serving with no device
  declarations. `ViewWatcher` stats the manifest before each turn: a `corpus_revision` change
  discards the view wholesale so no answer can mix revisions, an in-flight turn keeps the view
  object it holds, an unreadable new manifest keeps the live view and records the fault for
  `GET /sources` (never `corpus-empty`), and the reload cost lands on the run-level
  `corpus_reload_ms`, never on a turn. 21 tests cover load, refusal, slices, the sidecar rule and
  the revision watch.
- **The `dawmans` Python package** (`api/answer-engine` phase 1). `src/` layout on uv + hatchling,
  with the `dawmans.answer` module tree from the design's module placement, a `dawmans` CLI whose
  only registered subcommand is the `serve` stub, and `make build`/`test`/`lint` wired to uv,
  pytest and ruff.
- **The ingest/serve dependency split.** `[project.optional-dependencies]` confines PyMuPDF (AGPL),
  lingua and fonttools to `ingest`; the API host syncs `serve` (fastembed, bm25s, numpy, anthropic,
  starlette, uvicorn, keyring) and never installs PyMuPDF. A subprocess test imports every
  `dawmans.answer.*` module with `fitz`/`pymupdf` poisoned on `sys.meta_path`, catching the
  accidental corpus import a dual-group dev environment hides.
- **The envelope records and outcome enums** (`dawmans/answer/envelope.py`). Frozen dataclasses
  `Citation`, `AnswerEnvelope`, `Cause` and `RequiredManual` whose field sets are exactly the
  CONTRACTS §3/§4/§4c/§4e tables, and `Outcome` (17 members) / `Reason` (5 values) StrEnums closed
  to CONTRACTS §6/§6a. Construction enforces the contract invariants: absent is `None` and never an
  empty string, an authored-triage citation cannot carry a page, section number or `doc_version`,
  `entry_location` is authored-only, a cause's `rank` equals its position in `causes[]`, and
  `retry_after` is non-negative and unrounded. 32 tests assert the field sets and invariants.

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
