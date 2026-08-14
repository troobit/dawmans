# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- **Sectioning, layout and region assembly** (`dawmans/corpus/pdf/`, `data/manual-corpus` phase 5).
  The stages that turn an annotated span model into the shared `Region[]`/`Unit[]` shape.
  `sections.py` builds the section map from the document's own structure — embedded outline, printed
  contents page, then heading styles, in that order and none of it per-manual configuration (6.6) —
  and anchors each entry to the line its heading is printed on, so a page shared by two sections
  splits between them rather than being attributed whole to one of them. Path C's quality gate fails
  closed, because a title plus a strapline clearing a naive test yields two regions spanning 1009
  pages and a wrong section on every citation inside them. A region carries its nearest two
  ancestors, so `§28.21.1 Sidechain Parameters` — one of eight in Live's TOC — renders under the
  device that owns it.
- **Row, column and table assembly** (`dawmans/corpus/pdf/layout.py`). Rows cluster by y, columns by
  x0, and every cell is placed by its horizontal position rather than by its index in the row (7.1,
  7.6): Nitro Max p25 prints two ragged panels of 11 and 8 rows, and index placement mis-pairs the
  tail. A heading printed across three physical lines is joined per column into
  `Trigger | MIDI Note Number | Trigger | MIDI Note Number`; panel boundaries come from that repeated
  heading sequence and never from a hardcoded x; and the page is never de-interleaved into per-panel
  runs, which 7.2 forbids. All 19 trigger-to-note pairs are recoverable with their printed pairings.
- **Unit assembly and the furniture drop** (`dawmans/corpus/pdf/units.py`). Stage 7 clears the
  furniture mark inside detected tables, then drops what is still marked, ending the mark-then-clear
  ordering: a numeric line inside Nitro Max's note table survives while the repeated page number does
  not, and text is discarded exactly once. Table rows and numbered procedures are emitted `atomic`
  (6.10, 7.4) and the joined heading `repeat_on_split` (7.5); a procedure broken across a page break
  stays one unit carrying both page numbers; `has_figures` is set only where a placed image covers at
  least 2% of the page (10.3); printed contents pages and non-English blocks contribute nothing.
- **The vendor-manual load path** (`dawmans/corpus/pdf/loader.py`). `PdfLoader` behind the
  `SourceLoader` protocol (12.4), running the stages in the order the design calls load-bearing —
  extract, furniture mark, glyph repair, section map, language selection, unit assembly — and
  deciding the three rejections that need a source to have been read: no text layer (3.3), over the
  unmappable-character threshold (5.5), no English content (4.5). A rejected source still yields a
  `SourceRecord` and an ingestion audit.
- **Text conditioning: furniture, glyph repair and English selection** (`dawmans/corpus/pdf/`,
  `data/manual-corpus` phase 4). Three stages that annotate the span model rather than rewrite it.
  `furniture.py` marks running headers, running footers and standalone page numbers in the top and
  bottom 8% bands (3.6) and deletes nothing — the mark is cleared again by sectioning and by table
  detection, and the drop is the chunker's. `glyphs.py` repairs the APC Key 25's Clip Stop arrows,
  which its `Wingdings3` ToUnicode CMap mangles into `ð, ñ, ô, õ`: detection is font-keyed, so the
  genuine French `ô` printed two lines away in the body face survives, and so do the `Symbol`
  bullets on the same page. What cannot be mapped becomes U+FFFD and sets `degraded` (5.3), and over
  2% of the extracted text layer is the `unreadable-text` rejection (5.5). `language.py` scores
  blocks with `lingua` where the declared language is `multi`, and does not score a source declared
  with one code at all — Live's 3,979-word keyboard-shortcut chapter has 24 full stops in it and no
  identifier calls it English.
- **PDF extraction and the span model** (`dawmans/corpus/pdf/extract.py`, `data/manual-corpus`
  phase 3). `page.get_text("dict")` per page into `Page`/`Block`/`Line`/`Span`, each span keeping its
  bbox, font name, size and flags so glyph repair can key on the font, row assembly on geometry and
  language selection per block. The dict flags clear `TEXT_PRESERVE_IMAGES`: PyMuPDF's default
  materialises every image's bytes into type-1 blocks, which is both 10.1's "image content is not
  extracted" and, against Live 12's 96 MB of screenshots, a seventeen-fold cost on the page measured.
  Images survive as placement rectangles only, which is what 10.3's figure test needs and all it
  needs. Page numbers are physical 1-based indices. `has_text_layer` (3.3) and `low_text` (3.4) are
  derived from the model, the latter over the whole text layer **before** language selection — after
  it, every multilingual guide would be flagged for having translations.
- **The committed extraction fixtures** (`tests/fixtures/`, `tools/capture_fixture.py`,
  `make fixtures`). `manuals/` is gitignored, so no test may open a reference PDF: the nine vendor
  fixtures are snapshots of what the extractor returned for a named page range, which also pins its
  output as an explicit input to every downstream stage. The APC guide is committed redacted — text
  masked to its character classes, one language label per block — because 24 pages of it verbatim
  would be substantially the whole guide, and because the measurements the language stage makes are
  measurements of shape. Three synthetic rejection fixtures cover no-text-layer, over-threshold
  unmappable characters, and the two filename rejections.
- **Source discovery and identity** (`dawmans/corpus/discover.py`, `data/manual-corpus` phase 2).
  The filename grammar of 2.1–2.3 as one anchored expression, with `SourceIdentity.filename` as its
  exact inverse: `api/answer-engine` rebuilds a name from a `SourceRecord`'s own fields to serve the
  PDF behind a citation (CONTRACTS §3a) and to assemble `required_manual` (§4e), so `doc_version` is
  stored without its leading `v` and the round trip is asserted as a property. `source_id` is
  `<vendor>/<product>` with the version deliberately outside it, and the shard slug maps `/`→`_`
  rather than `/`→`-`, which would fold `a/b-c` and `a-b/c` onto one shard.
- **Both source stores scanned in one run, and a missing store distinguished from an empty one.**
  An absent, unreadable or not-a-directory store reports as unavailable and its discovery set is
  *unknown*, so no shard from it is removed; only an existing, empty store removes its shards. That
  is what stops an unmounted volume deleting every authored passage and reporting success. Removal
  is keyed on the store recorded in the shard's own meta, so 9.5's "never test a source of one kind
  against the other kind's store" holds by construction, and a removed source takes its view sidecar
  and its ingestion audit with it.
- **Discovery rejections, per 1.3, 2.5 and 2.6.** A malformed filename is reported with the offending
  name and the expected pattern; two files resolving to one `source_id` reject both rather than
  silently indexing one, and a shard standing under a rejected identity is removed. A non-PDF in
  `manuals/` is skipped with no report line. The run-level pass also catches the one collision no
  single store can see — a vendor manual named `authored_triage_*.pdf` lands on the authored store's
  constant identity, which the slug rule cannot distinguish.
- **The `dawmans` Python package, scaffolded** (`data/manual-corpus` phase 1). `src/` layout managed
  with uv, the module tree of the design's Module placement, and the Makefile targets that were
  still erroring: `build`, `test`, `lint`, `clean`, plus `fetch-model` (the one-off model cache
  population that keeps requirement 8.5's ingestion offline) and `bench` (the 8.1 full-corpus
  timing, which skips when `manuals/` is empty). `index/` and `models/` are gitignored.
- **The AGPL confinement is enforced, not just documented.** PyMuPDF may be imported only under
  `dawmans/corpus/pdf/` (`data/manual-corpus` Decision 6). A ruff banned-api rule catches the import
  form and `tests/test_agpl_confinement.py` walks the package AST, so `make test` catches the
  dynamic form the linter cannot see.
- **`SourceRecord` and `Passage` — CONTRACTS §1 and §2 as code.** Frozen, keyword-only records whose
  field set is asserted against the contract tables. The constructors refuse a field the record's
  kind marks not applicable rather than defaulting one into place (9.1, 12.5), pin an
  `authored-triage` source to the constant `authored/triage` and `assumed` applicability, and keep a
  pageless passage's section and page fields absent while requiring its `entry_location` (12.8).
- **The loader seam** (`dawmans/corpus/loader.py`): `SourceLoader`, `Discovered`, `LoadResult`,
  `Region`, `Unit`, `UnitFlags` and the closed `Rejection` reason set. Interfaces only —
  `TriageLoader` is `data/symptom-triage`'s to write, and everything from `Region` onwards is the
  shared code that makes 12.2 structural.
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

- **Stage 7 and the load path are their own modules** (`data/manual-corpus` Decision 13, design
  §Module placement). The design's module tree stopped at `pdf/layout.py`, leaving `Region[]`
  assembly and the loader that sequences the stages without a home. `pdf/units.py` and
  `pdf/loader.py` are added to the tree: `layout.py` keeps to geometry, so a table-detection
  regression is not read against a page-break join in the same file, and `corpus/loader.py` stays
  interfaces only — putting a PyMuPDF-importing class in the module `data/symptom-triage` imports
  would breach the Decision 6 confinement outright.
- **The language-neutral guard is confidence alone** (`data/manual-corpus` Decision 12, design
  §English selection). The design wrote it as low confidence *and* predominantly non-alphabetic
  tokens; run against the real APC guide, that conjunction selected its French and Italian pages as
  partly English. `• Mac OS X : Live > Preferences` scores English at 0.42 with alphabetic tokens,
  so it was trusted, and the short French step below it inherited from it — requirement 4.1 failing
  on the corpus's only multilingual source. Confidence alone covers strictly more than the pair did,
  so the MIDI note table and the specifications table the guard was written for are unaffected.
- **The spelling check skips `tests/fixtures/`.** The fixtures quote vendor manuals verbatim, and
  correcting a manual's spelling would make the fixture a document nobody shipped.
- **The design's account of the corpus, corrected against the corpus** (`data/manual-corpus`
  design §Section map and §Build budget, Decisions 10 and 11). Capturing the fixtures read the PDFs
  rather than describing them, and three claims did not survive: every manual carries an embedded
  outline, so paths B and C of the section map have no live instance and the APC Key 25 is not the
  outline-less document the design took it for; Live's printed contents pages carry no dot leaders,
  so path B's grammar does not detect them; and extraction of the full corpus measures 3.99 s
  against 8.2's 5 s budget, not the ~1 s the estimate extrapolated from a layout extraction. Neither
  path is dropped — they are what the next manual needs — and their fixtures are captured with the
  outline withheld.
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
