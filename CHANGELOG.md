# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- **`data/symptom-triage` Phase 3 — the term check.** `triage/terms.py` implements design §The term
  check (2.6): extraction over the cause statement plus its `check:` value and nothing else — the
  deliberate narrowing that keeps 2.5's causal assertions out of a factual check — of capitalised
  runs and numeric literals, and containment against the passages the cause's pointers resolve to.
  Containment is case-sensitive at word boundaries for the capitalised class, because casefolding
  would make `Off`, `Monitor` and `MIDI` match almost any prose, and casefolded for numerics,
  because unit case varies between manuals; `0` never satisfies `10`. Any one pointer's resolution
  set satisfies a term, and a split section is seen as its concatenation. A miss is a
  `term-not-in-passage` flag naming the term and the section and never sets `unbacked` (Decision 5)
  — 2.4 and 8.5 stay the only two producers of that mark. Phase 3 is now complete: scope validation
  landed with tasks 11–12.

- **`data/symptom-triage` Decision 10 — a sentence-initial capital is discounted per token, not per
  run.** The design states the rule for a single-token run at a sentence start. Applied literally,
  an author writing the design's own worked example — "The Track Activator is off" — yields the term
  `The Track Activator`, which is in no manual, so the example flags and §Testing Strategy's
  term-check soundness property breaks for any statement opening with an article. Discounting the
  token before runs are formed yields `Track Activator`, leaves every case the design names
  unchanged (`Live` alone still drops; `DIRECT MONITOR` still stands, ALL-CAPS being evidence a
  sentence start does not explain), and keeps one justification covering both cases.

- **`data/symptom-triage` Phase 2 — pointer resolution and the ledger.** `SectionIndex` builds the
  two maps of design §Fix pointers in one pass over a view's `passages.jsonl`, and `resolve` returns
  a section's passage ids in section order or an `Unresolved` naming why, with nearest-section
  candidates for the 5.3 message. Reading passages and nothing else is what makes 8.3 hold:
  `doc_version` lives on the `SourceRecord`, so a new document version of the same passages cannot
  move a pointer. `pointers.Ledger` is the committed NDJSON memory that separates 2.2's rejection
  from 8.4's flag — keyed on the pointer alone (Decision 4), sorted, never pruned, and written only
  on transition so an unchanged run leaves the file byte-identical. `.gitattributes` sets
  `merge=union` on it.

- **The section fixtures, cut from a real index.** `tests/fixtures/sections/` holds the 21 Live
  sections the starter set points at (including §18.1.1, which prints the `0 dB` requirement 7.3
  depends on), the Scarlett's Direct Monitor sections, the APC guide's unnumbered regions, §28.24
  chunked into three, and the `drift/` before-and-after pair. They are slices of a view built once
  locally by `tools/extract_section_fixtures.py` and committed, so the suite runs with `manuals/`
  absent and no embedding model loaded — the arrangement `data/manual-corpus` already uses for its
  extraction snapshots. `tests/fixtures/README.md` documents each; it sits above both fixture roots
  because every `.md` file under an entry store is an entry, so a README beside one would be
  discovered and rejected as a malformed entry.

- **`tools/check_spelling.sh` skips `tests/fixtures/`.** Those files quote the vendor's own words
  verbatim so a stage can be tested against what the manual actually says; correcting a manual's
  spelling would make the fixture a document nobody shipped. `orbit-impl-1/manual-corpus` already
  carries the identical exclusion for the identical reason, so the two copies agree rather than
  conflicting on merge.

- **`data/symptom-triage` Decision 9 — a ledger transition is detected by comparing passage ids.**
  The design requires `resolved_at` move only on transition but does not say how a run recognises
  "resolution after a drift", and the ledger deliberately carries no drifted marker. Comparing the
  row's `passage_ids` against what the pointer resolves to now settles it from the row itself: a
  renumbered, rewritten section produces different passages, while a manual restored to exactly its
  previous state produces the previous ids and so writes nothing at all.

### Changed

- **Costed the `data/manual-corpus` merge that unblocks `data/symptom-triage` Phase 4.**
  `docs/agent-notes/triage-entry-grammar.md` said Phase 4 becomes reachable when that branch merges,
  but not that the merge is already available: everything Phase 4 needs — `SourceRecord` and
  `passage_id` — is committed at `4f0ea7c`, and the work still uncommitted in that worktree is all
  under `index/`, which Phase 4 never touches. The note now records that `git merge-tree` reports
  seven conflicting files, all of them the shared scaffolding the two branches grew independently
  (`.gitignore`, `CHANGELOG.md`, `Makefile`, `pyproject.toml`, `specs/OVERVIEW.md`,
  `src/dawmans/__init__.py`, `uv.lock`) with no semantic clash among them, and two already ruled by
  PROCESS.md §9. Phase 4 is therefore blocked on a decision about what belongs on this branch, not
  on a missing artefact — worth settling once instead of re-deriving each run. Phase 2 is unaffected:
  its two prerequisites are human-only.

- **Corrected the `data/symptom-triage` blocked-work note.** `docs/agent-notes/triage-entry-grammar.md`
  claimed `data/manual-corpus` was complete only through its task 17 and that no chunker or
  passage-id scheme existed; both now exist. The note names the real gate for Phase 2 — a committed
  `views/<hex>/passages.jsonl` from that spec's task 37, plus its human prerequisites — rather than a
  task count that goes stale, and records that Phase 4 is blocked too even though `rune` reports its
  first task ready: cross-spec dependencies are not expressible in the ledger, and every remaining
  task in this spec has one.

### Added

- **`data/symptom-triage` device scope validation (tasks 11–12).** `dawmans.triage.scope` applies the
  six rows of the design's Device scope table: a declared device in the rig inventory with no
  ingested manual scopes and reports `undocumented-device-scope` (4.4); one the corpus documents but
  the rig does not scopes silently, because 4.5's condition is "neither"; an unrecognised identity
  flags `unknown-device` and still ingests, unless *every* declared device is unrecognised, which is
  the `all-devices-unrecognised` rejection — the recorded deviation from 4.5, since a flag would
  leave the entry embedded and reachable by no turn. Identities are matched exactly (4.2), and
  `@revision` is compared after casefolding and stripping non-alphanumerics, quoting the rig's value
  verbatim on a mismatch (4.6). The 2.3 `undocumented:` claim rejects where it names a device absent
  from the rig, or one the corpus documents. Recorded as Decision 8: "indexed" means every identity
  the corpus documents — source ids **and** the device ids they declare under
  `source_applicability` — not source ids alone, or today's `focusrite/scarlett-solo` declaration
  would be reported as undocumented while its guide sits in the corpus.
- **`data/symptom-triage` Phase 1 — the entry model and the entry grammar.** `dawmans.triage.model`
  holds the frozen `Entry`, `Cause`, `DeviceRef`, `Pointer` and `Unresolved` records of the design's
  Components and Interfaces, together with the closed rejection and flag vocabularies of its Error
  Handling section. `dawmans.triage.parse` reads an entry file into an `Entry` and produces the
  canonical rendering: strict about the frontmatter, forgiving in the body, and **total** — every
  byte string yields an entry or a rejection naming the file, and never a half-built entry.
  `dawmans.triage.pointers` carries the fix-pointer grammar the parser needs; its `SectionIndex` and
  resolution are Phase 2.
- **The Python package, cut to what Phase 1 needs.** `pyproject.toml` with a `src/` layout, uv for
  dependencies, and pytest + hypothesis + ruff for development; `make test`, `make lint` and
  `make format` replace three of the unconfigured targets. The full scaffold — the whole module
  tree, `fetch-model`, `bench`, and the PyMuPDF confinement rule — remains `data/manual-corpus`
  task 1.

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

- **Keyed-line continuation now splits by value kind** (`data/symptom-triage` Decision 7). `check:`
  and `why:` are free text and continue until a blank line, a heading or another keyed line;
  `fix:`, `undocumented:` and `also:` are complete on their own line. Under the single rule the
  grammar previously carried, an ordinary note written under a fix pointer was folded into the
  pointer, which then addressed nothing and rejected the cause with a message naming a line the
  author had written correctly. Found by the cause-conservation property, not by an example.
- **Cause conservation is stated over the total H2 count**, not over the H2s that were not the
  author's closing statement. Decision 6 turns on the parser being unable to tell a genuine closing
  statement from a demoted cause, which is why it flags every inferred one — so the identity that
  actually holds, and the one that makes 1.5 auditable, is causes plus flags equals sections.
  Corrected in the design's Testing Strategy and in the task ledger.
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
