# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Changed

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
