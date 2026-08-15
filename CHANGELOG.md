# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- **`data/symptom-triage` Phase 5 — discovery, the sidecar and the run integration.** `dawmans
  ingest` now runs both stores with the real `TriageLoader`. Discovery is a recursive scan of
  `triage/**/*.md` (1.6): a subdirectory entry is found, a non-`.md` file beside one gets a report
  line — the opposite of `manuals/`, where the skip is silent — and dotfiles are exempt so the
  machine's own `.pointer-ledger.jsonl` never warns about itself. The store is one source however
  many files it holds, and its fingerprint is sha256 over the sorted (store-relative path, file
  digest) pairs. `load()` runs on **every** ingest regardless of that fingerprint, because 2.1 asks
  for every fix pointer to be re-checked on every run and a digest of the store's own bytes cannot
  answer a question about the manuals. An absent or unreadable store is an unknown discovery set
  that removes nothing; an existing empty one removes its shard; a store in which no entry survives
  is `authored-invalid`, which deletes the shard rather than letting the previous run's passages
  keep being served.

- **The per-`passage_id` sidecar (`triage/scope.py`).** `LoadResult.sidecar` lands at
  `views/<hex>/reports/authored_triage.json` — the corpus's slug rule, underscore and not hyphen,
  inside the view so it swaps atomically with the passages it keys. Each row carries the entry's
  declared devices (4.3, the input to `api/answer-engine` 5.13's per-passage predicate), the
  `source_file` and `line` halves of CONTRACTS §2 `entry_location`, an `entry_key` annotation, and
  the causes in declared order with their checks, resolved fix passage ids and flags — the source of
  CONTRACTS §4c's `Cause` records. Every passage of a split entry carries the whole cause list,
  because which passage holds which cause is an artefact of the 350-word cap. The report block
  carries 2.8's pointer counts and one row per rejection and per flag with its reason (5.5), and is
  written to `index/audits/authored_triage.json` as well so a rejected store's reasons survive.

- **The term check and `title-number-disagreement` joined the run.** `CorpusView` now carries
  passage text, so `check_terms` runs during evaluation and a factual claim no cited section prints
  is flagged (2.6) — never setting `unbacked`, which keeps 2.4 and 8.5 its only two producers
  (Decision 5). A view read without passage text checks nothing rather than flagging everything.

- **The pointer ledger is written by the run.** `load()` records every pointer that resolved and
  writes only on transition, so a second run over an unchanged store leaves
  `triage/.pointer-ledger.jsonl` byte-identical and the working tree clean. Recording happens in
  `load()` alone, which is what will let `dawmans validate` run the same checks without promoting a
  broken pointer to "previously fine" (5.4). An unparseable ledger reaches the run as a failure:
  non-zero exit, previous shard intact.

- **`data/symptom-triage` Decision 13 — the run's `CorpusView` is read from the committed shards,
  not the committed view.** The design required both "the authored load runs after every vendor
  shard has committed" and "`CorpusView` never opens a shard", and `manual-corpus` merges shards
  into a view only at the end of a run — so at authored-load time the view named by
  `manifest.view_dir` is the *previous* run's. Reading it would reject a new entry pointing into a
  manual the same run ingested, and would detect drift one run late. The shards hold the passages
  the merge concatenates, so 5.7 is untouched: no PDF, no vector file, no extraction, chunking or
  embedding. `CorpusView.of` takes the published JSON shapes, so `dawmans validate` will read the
  same rows out of `views/<hex>/` with no second reader. The design's `CorpusView` row is marked
  superseded in place.

- **`data/symptom-triage` Phase 4 — identity, emission and the loader.** `triage/loader.py` puts the
  entry store behind `manual-corpus`'s `SourceLoader` seam. `source_record` is design §Identity's
  table applied literally — the constant `authored/triage`, `My Triage Notes`, `assumed`
  applicability that nothing in configuration can raise, and not one of the seven vendor-manual
  fields, which 12.5's constructor refuses rather than defaults. `emit` turns one entry into one
  `Region`: the symptom, its `also:` phrasings and its preamble first as a `repeat_on_split` unit,
  then each cause `atomic` in declared order (1.5 — that order becomes CONTRACTS §4c's rank), then
  the closing statement. `passage_id` is minted by the corpus chunker and nowhere else, so an
  authored passage is identified by the same function over the same canonical form as a manual
  passage (3.9); `parse.render_blocks` is the one construction of that form, joined with a blank
  line for the reader and with `UNIT_JOIN` by the chunker, which hash alike because `passage_id`
  collapses whitespace before hashing.

- **`data/symptom-triage` Decision 12 — the authored overlap suppression is `manual-corpus`'s rule,
  not an edit here.** Task 16 reserved a keyed change to `dawmans/corpus/chunk.py` as the one edit
  this spec makes to the chunking pipeline. That edit has since been made upstream and made more
  general: `manual-corpus` Decision 15 states it as "a repeat replaces overlap rather than joining
  it", which reaches the authored case without the chunker knowing what kind of source it has
  (12.2). Making it again would be two rules that must agree in one function. The outcome is
  asserted from this spec instead — `Chunk.carried` equals the symptom block's word count on every
  continuation — so a relaxation upstream fails a test here rather than quietly putting the symptom
  into hashed, user-visible text twice.

- **`data/symptom-triage` Decision 11 — canonical idempotence is stated over a parse–rebuild round
  trip.** Task 13's literal `render(parse(render(parse(f)))) == render(parse(f))` cannot hold:
  `render` excludes the frontmatter, the fix pointers and the filename by design, so its output is
  not an entry file and the inner parse rejects with `frontmatter-missing`. `render ∘ parse ∘
  rebuild` is asserted instead, `rebuild` being a test-support writer that re-supplies exactly what
  the rendering drops — which keeps the property passing through the real parser and the real
  rendering without shipping a second definition of the entry format.

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

- **`normalised_symptom` and a new `entry_key` moved to `triage/model.py`.** Both are functions of
  the model's own fields, and `loader` needs the first for 1.9's duplicate test while `scope` needs
  the second for the sidecar — with `loader` importing `scope`, `model` is the only home that is not
  a cycle. `loader` still re-exports `normalised_symptom`. `scope.RigDevice` gained `display_name`,
  which the term check reads, so the protocol states what this spec reads of a rig device rather
  than what one module does.

- **A rejected entry's flags no longer appear in the run's flag list.** Parse flags are collected
  before anything can reject an entry, so an entry excluded for being malformed was contributing
  remarks beside the reason it went. They are dropped, which also keeps the report's `flagged` count
  and its `flags` rows describing the same entries.

- **The triage tests share one store builder.** `tests/triage/stores.py` holds the on-disk store,
  the `CorpusView` over the committed section fixtures and the loader that reads them, extracted
  from `test_emission.py` when the discovery and sidecar tests needed the same fixtures.
  `tests/triage/test_ingest_wiring.py` runs the real loader through `cli.ingest` with a stub vendor
  store rebuilt from those same fixtures; `tests/test_run.py` deliberately keeps a *stub* authored
  store, because a run that only ever saw the real one would prove nothing about 12.2.

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

- **The rig inventory and the two gap reports** (`dawmans/corpus/rig.py`, `rig.yaml`,
  `data/manual-corpus` phase 8, requirements 11.1-11.7). `rig.yaml` is hand-maintained and
  committed — it says what the owner **holds**, while `manuals/` says what is **documented**, and
  11.3 keeps them apart on purpose. The join runs through `hardware_applicability.device` and never
  through `source_id` (Decision 9), which looks like a nicety until the Focusrite: the filename's
  product carries the generation marker (`scarlett-solo-4g`) and the rig's device id does not
  (`scarlett-solo`), so a join on the ID would report the device undocumented with its manual
  sitting in `manuals/`. `gaps.json` carries owned-but-undocumented and documented-but-unconfirmed,
  **both members always present even when empty** (11.4) — a consumer distinguishing absent from
  empty breaks on the day it fills. indexed-but-not-owned (11.7) stays in the run report and out of
  `gaps.json`: a manual for gear the owner does not hold is not a gap in the rig, and CONTRACTS §5
  governs two reports rather than three.
- **The per-run report and the per-source ingestion audits** (`dawmans/report.py`, 1.5-1.7, 4.4,
  5.4, 9.1, 9.5, 11.7). Every source is reported as ingested, skipped as unchanged, or rejected with
  its reason — and for a malformed filename, the pattern it should have matched. The six rejection
  reasons are closed **at construction** rather than checked at rendering: a rejection reports the
  run as succeeded, so a disk error dressed as one is a run that indexed nothing and exited zero,
  which is exactly what 1.7's failure path exists to prevent. The audit at `index/audits/<slug>.json`
  is written as each source finishes, committed shard or rejection, and always carries a `rejection`
  key — `null` where there is none, because absent and null are different to a reader. The 9.1
  inventory derives its fields from `SourceRecord` itself rather than a hand-written list, so it
  cannot drift from the CONTRACTS §1 table it is required to reproduce.
- **`dawmans ingest`, `dawmans validate`, `dawmans inventory`** (`dawmans/cli.py`, 8.6, 9.1, 9.6,
  12.2, 12.7). The whole stage order behind one command: collect superseded views, discover both
  stores, load the embedding model once, ingest the vendor sources and commit their shards, then the
  authored load, then the merge, `gaps.json` and the manifest rename. The vendor and authored
  loaders are separate parameters rather than a list, because their order is a constraint and not a
  convention — `TriageLoader` resolves each fix pointer against a vendor passage, so loading it
  earlier would resolve against the *previous* run's text. A rejection deletes the source's shard,
  since 1.6's "exclude that source from the index" is the passages going rather than a line in a
  report; a failure keeps the previous shard, is collected, and the run continues to the next source
  with no abort-on-first-failure path. Against the real corpus: 4 sources, 1431 passages, a full
  cold rebuild in ~43 s.
- **The timing tests and the `bench` target** (`tests/test_timing.py`, 8.1, 8.2, 8.4). 8.2 and 8.4
  run in CI against synthetic PDFs generated at test time; 8.1 needs the gitignored manuals and runs
  under `make bench`. 8.4 is measured with the model **resident**, exactly as the CLI arranges it,
  and the cold load is asserted separately in a fresh process and through to a first vector —
  `fastembed` builds no ONNX session until something is embedded, so a test that stopped at
  construction would time an import and pass however slow the real load became.

### Changed

- **The rig is joined at the merge, not written into the shard** (Decision 18). A shard is a cache
  of what the *document* said, keyed by the document's bytes; `rig.yaml` is what the *owner* says,
  and editing it changes no byte of any PDF. Applied at shard-build time, a new
  `source_applicability` declaration was invisible until something unrelated changed the manual —
  every cache key still matched, no loader ran, and the reports kept describing the last rig the
  corpus happened to be rebuilt under. Found by running the real corpus and seeing the Focusrite
  reported under owned-but-undocumented *and* indexed-but-not-owned at once, which is the pairing
  11.7 uses to signal a missing declaration that was not missing.
- **The authored store is exempt from fingerprint-based shard skipping**, per
  `data/symptom-triage` §Discovery. Its validity is a function of the manuals as well as its own
  text, so a fingerprint over its own bytes cannot say whether a fix pointer still resolves;
  skipping it left `unbacked` describing the run before last.
- `pytest` now runs with `-m 'not bench'` by default. The marker alone deselected nothing, so
  `make test` was running the full-corpus 8.1 benchmark.
- `AUDIT_DIR` is declared once, in `corpus/discover.py`. It had been defined in two modules and
  hardcoded in a third.

### Fixed

- `Rejection` now refuses a reason outside requirement 1.6's closed set. The `Literal` type
  documented the set; nothing enforced it at runtime.

### Added

- **The embedding wrapper and its offline pin** (`dawmans/index/embed.py`, `data/manual-corpus`
  phase 7). `fastembed` is the only network-capable dependency in the package, so ingestion pins
  `HF_HUB_OFFLINE=1` in its **own process environment** — not as a library argument — and then
  checks the `models/` cache, in that order: pinning afterwards would leave a run that recovered
  from the failure able to reach the network next time. An absent cache raises a **failure**, not a
  rejection (1.6's list has no member for it: no source is at fault and nothing can be embedded),
  naming the model, the directory and `make fetch-model`. The model is loaded **once per run** and
  passed to the shard build, because the ~7.2 s cold load against 8.4's 10 s budget for a whole new
  source leaves nothing if it is paid per source. The wrapper owns float32, 384-wide and
  L2-normalised output and rejects a backend of another width — vectors from a second model reaching
  the view under a manifest declaring 384 change nothing about the on-disk shape, so `index_version`
  cannot catch it.
- **The lexical index and its tokeniser** (`dawmans/index/lexical.py`, requirement 8.8,
  Decision 2). A `bm25s` index over the same passage ordering as the dense one, so document `i`,
  row `i` and line `i` are one passage. The tokeniser keeps a compound **whole and then in parts** —
  `Dry/Wet` yields `dry/wet`, `dry`, `wet` — which is the failure Decision 2 names and the one that
  is otherwise silent: a default tokeniser drops the compound, nothing errors, and the query a user
  is most confident about stops working. The tests assert the default *does* lose `Dry/Wet`,
  `4th-gen` and `bge-small-en-v1.5` before asserting ours keeps them, so a regression to the default
  cannot pass. No stopword list is applied: `bm25s`'s English list holds `on` but not `off`, which
  would make one half of every On/Off control unretrievable and leave the other.
- **The per-source shard and its four-part cache key** (`dawmans/index/build.py`, 8.3, 8.7, 9.3,
  9.4). A shard is reused only when **all four** of fingerprint, `ingestion_version`,
  `embedding.model` and `embedding.dim` match. Both failures the fingerprint alone allows are
  asserted, and both are silent: changing the embedding model would concatenate vectors from two
  models under a manifest declaring one, and a fix to table assembly or chunking changes no PDF byte
  and would reach nothing. The authored shard carries a `passage_id` → row map so editing one entry
  re-embeds that entry alone, while the shard is still rewritten wholesale (9.4). Artefacts are
  written to `.tmp` beside their destinations and moved with `os.replace`, **meta last**, so a
  partly committed set reads as no shard; a failed source's temporaries are deleted, its previous
  shard is untouched, and a source that succeeded in the same run stays queryable.
- **The merge, the manifest and the atomic view commit** (`dawmans/index/build.py`,
  `dawmans/index/manifest.py`, 8.6, 8.8–8.11, 9.6, 11.6, 12.7). The view is a plain concatenation of
  the committed shards **sorted by `source_id`** — filesystem order could otherwise shift
  `row_start` offsets between two runs over an identical source set while `corpus_revision`, hashed
  over sorted triples, stayed the same, leaving a consumer slicing the wrong rows. It is built into
  a directory no reader can be holding and `manifest.json` is renamed into place last, so that
  rename is the only switch; superseded views are collected at the **start** of the next run, so a
  reader working from the previous manifest keeps its files. Each shard's sidecar is copied into
  `views/<hex>/reports/<slug>.json` — a reused shard runs no loader, so a sidecar written only by
  `load()` would be absent from every later view — while ingestion audits stay outside the views,
  which is the two lifetimes the split exists for. A reader whose `index_version` differs refuses
  to load rather than interpreting the files.
- **The incremental-equivalence property** (`tests/test_incremental_equivalence.py`). A random
  add/edit/remove script over a random source set, one ingestion per step, must produce the same
  `passages.jsonl` bytes and the same `vectors.npy` rows as a full rebuild of the final state. This
  is the test that catches an incremental path quietly diverging from the rebuild it is supposed to
  be an optimisation of — a class of fault that produces no error, only a wrong index, and which
  every single-run test is blind to.
- **Passage identity** (`dawmans/corpus/passage_id.py`, `data/manual-corpus` phase 6). The digest
  covers the chunk's body text and nothing else (6.1, Decision 5), with `source_id` carried as a
  visible prefix rather than hashed, so cross-source collisions are impossible by construction and a
  fetch routes on the prefix without a lookup. Whitespace and Unicode composition are normalised
  away — a re-extraction differing only in line wrapping must not orphan every citation in the
  retained UI history at once — and case is kept, because two chunks differing only in case are
  different text. Where chunks share a digest the **first in document order keeps the unsuffixed
  identifier**; suffixing all of them would destroy the stable identifier of a copy whose text did
  not change. Determinism is asserted end to end over the same PDF bytes, not by re-hashing one
  string.
- **The chunker and the citation header** (`dawmans/corpus/chunk.py`). Greedy packing to the
  350-word cap within one region, so no chunk spans two sections (6.7) and the blast radius of a
  vendor edit stays inside one. Pages come from the chunk's **own** units, so a split table's
  continuation chunk records p26 rather than the p25 of the heading copied onto it (6.8); flags are
  the OR over every unit it holds, copied ones included, so a chunk of degraded rows stays degraded
  under a clean heading (5.3). An atomic unit that fits is never split (6.10, 7.4), one that does
  not is split with every part marked, and a split table repeats its joined heading — its own, never
  a previous table's (7.5). The citation header is embedded and BM25-indexed but is never part of
  `Passage.text`, and the section marker is omitted entirely rather than rendered as `§None`. A
  chunk page outside the source's range is a **failure**, not a rejection (6.11), and the check is
  skipped for a pageless source (12.8).
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
- **`Region` carries `entry_location`** (`data/manual-corpus` Decision 14, design §The loader
  protocol). CONTRACTS §2 requires the field on every authored passage and `records.py` refuses to
  construct one without it, but the seam had nowhere for it to travel. The sidecar cannot supply it:
  it is keyed by `passage_id`, which the chunker is the stage that mints. A region is exactly one
  authored entry, so the field is region-scoped; `TriageLoader` sets it and the chunker copies it,
  never deriving, clearing or hashing it (12.6). `data/symptom-triage` §Passage emission still has
  to name it in its own `Region` construction table.
- **A repeat replaces overlap rather than joining it** (`data/manual-corpus` Decision 15, design
  §Chunking). `data/symptom-triage` needs overlap suppressed for its regions, because a split entry
  would otherwise carry its symptom statement twice in hashed, user-visible text. Stated as "overlap
  is taken only where the continuation copies no `repeat_on_split` unit", the rule reaches that case
  without the chunker knowing what kind of source it has (12.2), and it keeps a split table's full
  room for rows.
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
