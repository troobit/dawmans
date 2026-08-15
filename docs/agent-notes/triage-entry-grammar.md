# Triage entry grammar (`dawmans.triage`)

How the `authored-triage` entry format is parsed. Spec: `specs/data/symptom-triage/`.
Phases 1–7 are implemented — the model, the grammar, the canonical rendering,
pointer resolution, the ledger, device scope validation, the term check, identity
and emission, discovery, the sidecar, the run integration, the validation
messages, `dawmans validate` over the store, `dawmans coverage`, and now the five
starter entries in `triage/` with the acceptance and timing targets. `dawmans
ingest`, `validate` and `coverage` all run the real loader. Outstanding: nothing
in this spec except 7.7's end-to-end half, which waits on `api/answer-engine`.

**`data/manual-corpus` is merged into this branch** (`bd4625e`), which is what
unblocked Phase 4. Two earlier runs recorded the block and costed the merge
without taking it; what it was waiting on was a decision about whether another
spec's work belongs on this branch, and the answer taken was yes — this spec
builds on the corpus, CONTRACTS §1 forbids it redefining those types, and both
branches were local and unpushed so the merge was reversible. The seven conflicts
were all shared scaffolding the two branches grew independently; the merge commit
records how each was resolved. The one resolution worth knowing: ruff's
`extend-exclude` is now `["*.md"]` rather than the three directories this branch
listed — `specs/`, `docs/` and `manuals/` hold no `.py`, so the pattern states the
same rule over the files it actually means.

**Phase 2's block was a different one and is also cleared.** It needed a locally
built index, which needed both human prerequisites in `manual-corpus`'s
`prerequisites.md`. Both are met: `rig.yaml` carries the Scarlett mapping and
`make fetch-model` has been run once on this machine. See §Building the index for
what remains a one-off by hand. Scope validation had been reachable before all
this because it reads the rig and the corpus's identity vocabulary, neither of
which needs an index.

**Cross-spec dependencies are still not expressible in the ledger.** `rune`'s
`blocked-by` names only tasks in this file, so a task can read ready while
needing a module another spec owns. Every remaining task here has one; check the
imports before trusting `rune streams --available`.

## Modules

| Module | Holds |
|---|---|
| `model.py` | the five frozen dataclasses of design 'Components and Interfaces', plus `RejectionReason`, `FlagName`, `EntryRejection`, `Flag`, `normalised_symptom` and `entry_key` |
| `parse.py` | `parse_entry(source_file, data) -> ParseResult`, `render_blocks(entry) -> Rendering`, and `render(entry) -> str` |
| `loader.py` | `TriageLoader`, `CorpusView`, `source_record`, `entry_location`, `emit`, the `StoreOutcome`/`EntryOutcome`/`CauseOutcome` types, and discovery — `entry_files`, `skipped_files`, `store_fingerprint`, `scan_store` |
| `pointers.py` | `parse_pointer`, `normalise_title`, `SectionIndex`, `resolve`, `title_disagrees`, and the ledger — `pointer_key`, `Ledger`, `check_pointer` |
| `scope.py` | `validate_scope(entry, rig, indexed) -> ScopeResult`, and the sidecar — `sidecar(outcome, passage_ids, report=…)` and `report(outcome, ledger_missing=…, coverage=…)` |
| `terms.py` | `terms`, `device_vocabulary`, `contains`, `Resolution`, `check_terms`, `TermMiss`, `term_flag` — design 'The term check (2.6)' |
| `messages.py` | `lines(rejection or flag)`, `header`, `counts`, `counts_of`, `store_lines` — the 5.3 rendering and nothing else |
| `coverage.py` | `coverage(outcome, rig) -> Coverage`, its four row types, `Coverage.lines()` and `Coverage.to_dict()` — the §6 report |

The design's 'Module placement' names only behaviour modules. `model.py` is an
addition, and it earns its place: the rejection and flag vocabularies are needed
by `parse`, `pointers`, `scope` and `coverage` alike, and putting them in
`parse.py` would make `pointers.py` import the module that imports it.
`normalised_symptom` and `entry_key` moved there for the same reason —
`loader.py` needs the first for 1.9 and `scope.py` the second for the sidecar,
and `loader` imports `scope`. `loader.py` still re-exports `normalised_symptom`.

## Things that are not obvious

- **Parsing is total.** `parse_entry` takes bytes and never raises: it decodes
  with `errors="replace"` and catches every exception out of `yaml.safe_load`,
  not just `YAMLError`. The property test drives it with `st.binary()`. The
  contract is exactly one of `entry` and `rejection`, never both and never
  neither, and never a half-built entry.

- **Two continuation rules, not one** (Decision 7). `check:` and `why:` continue
  until a blank line, a heading or another keyed line. `fix:`, `undocumented:`
  and `also:` end at their own line — see `SINGLE_LINE_KEYS`. Under one uniform
  rule, a note written beneath a fix pointer is swallowed into it and the cause
  rejects with a message naming a line the author wrote correctly. The property
  test found this; no example test would have.

- **Every closing statement flags, including a genuine one.** The parser cannot
  tell an intended closing statement from a cause that lost both its keys — that
  is the whole of Decision 6 — so `closing-statement-inferred` fires on every
  final section carrying neither. The flag is an inventory line, not a warning.
  The invariant that follows is `len(causes) + closing_flags == H2 count`.

- **The rule is positional.** Only the *final* section can be demoted. A section
  missing both keys in the middle of the document is a cause and rejects under
  `cause-missing-check`.

- **Forgiving in the body means retained, not accepted.** A second `check:` line,
  a stray `also:` inside a cause, and a `fix:` line naming neither a section
  number nor a title are all folded into the cause's notes carrying the
  *normalised* marker. Nothing the author typed disappears, and the rejection set
  stays closed at the fifteen constants of design 'Error Handling' — there is no
  `cause-multiple-checks`.

- **A `fix:` line that addresses nothing is not a pointer.** `parse_pointer`
  returns `None` rather than building a `Pointer` with both `section_number` and
  `section_title` unset. If the cause has nothing else backing it the rejection
  is `cause-missing-fix`, and the message quotes what the author wrote.

- **Headings beat keyed lines at levels 1 and 2 only.** `#` is in the keyed-line
  strip set, so `### check: x` *is* a check line while `## check: x` is a cause
  heading whose statement is `check: x`.

- **`render()` is the passage text, not an entry file.** It excludes the
  frontmatter, the fix pointers and the filename by design (§Identity), so it
  does not round-trip through `parse_entry` — feeding it back in rejects with
  `frontmatter-missing`. The canonical-idempotence property is therefore stated
  over `render ∘ parse ∘ rebuild`, `rebuild` being the test-support writer that
  re-supplies exactly what the rendering drops. Decision 11.

## Identity and emission (`loader.py`)

- **The loader mints no `passage_id`.** `chunk_source` assigns every identifier
  from the packed text, so an authored passage is identified by the same function
  over the same canonical form as a manual passage (3.9). A second minting here
  would be a second rule to keep in step with the chunker's packing.

- **`render` and the emitted text hash alike.** `render` joins the blocks with a
  blank line for the reader; the chunker joins the same blocks with `UNIT_JOIN`
  (`"\n"`). `passage_id` canonicalises NFC and collapses whitespace runs before
  hashing, so the two carry one identifier — which is what makes the design's
  "the hashed text is `passage_text` itself" true of an unsplit entry.
  `render_blocks` exists so both readers get the blocks from one construction.

- **No edit was made to `corpus/chunk.py`, and task 16 asked for one.** The
  overlap suppression §Passage emission needs is already `manual-corpus`
  Decision 15 — "a repeat replaces overlap rather than joining it" in
  `_continuation` — which reaches the authored case without the chunker knowing
  the source kind (12.2). Decision 12. The dependency is asserted here rather than
  assumed: `Chunk.carried` must equal the symptom block's word count on every
  continuation, so a relaxation upstream fails a test in this spec.

- **The `unbacked` mark has exactly two producers**, and they are per cause:
  2.3's `undocumented:` and a drifted pointer (8.5). A term miss never sets it
  (Decision 5). Because the flag is on the `Unit`, a split entry marks only the
  passage carrying the cause and an unsplit one marks the whole thing — the
  over-marking 2.4 chose.

- **`normalised_symptom` is not `normalise_title`.** The title form strips a
  leading section number, which a symptom may legitimately carry: "0 dB is never
  reached" and "dB is never reached" are two symptoms. It is casefold plus
  whitespace collapsing and nothing else.

- **Duplicate detection compares device sets by intersection, not equality.**
  `overlapping_scopes/` is the fixture that discriminates: `[live-12]` and
  `[live-12, apc-key-25]` are unequal, and both are retrievable in any
  Live-scoped turn. Both entries are rejected, because nothing says which the
  author meant to keep.

- **`UNCHUNKED = 0` is restated rather than imported.** The corpus's copy lives
  in `corpus/pdf/loader.py`, which imports PyMuPDF; importing it here would pull
  an AGPL dependency out of the `corpus/pdf/` confinement Decision 6 sets.

- **`StoreOutcome` is separate from `LoadResult` on purpose.** The rejections and
  flags outlive emission — the sidecar's report block and `dawmans validate` both
  read them, and `validate` emits no passages at all. `evaluate()` is the whole
  verdict; `load()` is `evaluate()` plus `emit()`.

## Discovery, the sidecar and the run (Phase 5)

- **The view the ingest run reads comes from the committed *shards*, not from
  `views/<hex>/`** — decision_log Decision 13, and the one place this
  implementation departs from the design's own words. At authored-load time this
  run's view does not exist: the merge happens after every loader. Reading the
  previous view would reject a new entry pointing into a manual the same run
  ingested. A shard's `passages.jsonl` holds the passages the merge concatenates,
  so nothing is re-extracted and 5.7 is untouched. `CorpusView.of(passages,
  sources)` takes the **published JSON shapes**, so `dawmans validate` will read
  the same rows out of `views/<hex>/` with no second reader.

- **`CorpusView.indexed` is derived, not passed.** `of()` builds it from the
  source records: each `vendor-manual` `source_id` plus the device id its
  `hardware_applicability` declares (Decision 8). An `authored-triage` record is
  excluded — an entry may not cite the notes (2.7).

- **A view carrying no `texts` term-checks nothing.** `check_terms` over an empty
  passage would report every term missing, so a pointer whose passages the view
  has no text for contributes no `Resolution` at all. Silence is not evidence.

- **Discovery is three module-level functions, not methods.** `scan_store`,
  `entry_files` and `store_fingerprint` read the store's directory and nothing
  else — no corpus, no rig, no ledger — which is what lets `cli.TriageStore.scan`
  answer without assembling what only `load()` needs.

- **A non-`.md` file is reported as `filename-invalid`.** That is `manual-corpus`
  1.6's reason for a file whose name does not admit it as a source; the rejection
  set is closed, so inventing a second spelling would put a reason outside 1.6 on
  a path 1.7 reserves for failures. The line reads
  `no-sound.txt  rejected: filename-invalid — …`, which is the report line the
  design asks for.

- **The dotfile rule is applied below the store**, not over the absolute path:
  `triage/` may itself sit under `.orbit/` in a worktree, and that says nothing
  about the files inside it.

- **`authored-invalid` is only "no entry survived".** An existing empty `triage/`
  is an *empty discovery set* — the shard is removed by `remove_absent_sources` —
  and an absent or unreadable one is an *unavailable store*, whose shard stands.
  Three different outcomes that all look like "there is nothing there".

- **The loader chunks its own regions to build the sidecar.** `LoadResult.sidecar`
  is keyed by `passage_id` and the seam has no post-chunk hook, so `load()` calls
  `chunk_source` over the regions it just emitted; `cli` calls it again. Same pure
  function, same inputs, same ids. Chunks are grouped back to entries by
  `entry_location`, which is unique per entry — `section_title` is not, because
  1.9 permits a shared symptom in disjoint scopes.

- **Every passage of a split entry carries the entry's whole cause list.** Which
  passage holds which cause is an artefact of the 350-word cap, so truncating the
  list per passage would make a citation's `Cause` records (CONTRACTS §4c) depend
  on where the cap fell. `unbacked` on the `Passage` stays per unit.

- **Per-cause flags live on `CauseOutcome`.** Filtering the entry's flags by cause
  statement would misattribute them: `test_emission` has an entry with two causes
  worded identically, and 1.5 forbids deduplicating them.

- **The ledger is written by `load()` and by nothing else.** `load()` is called
  under `dawmans ingest` alone, which is what keeps `dawmans validate` — which
  goes through `evaluate()` — from promoting a broken pointer to "previously
  fine" (5.4). `record` writes only on transition, so a second run over an
  unchanged store leaves the file byte-identical; there is a test for it.

- **An unparseable ledger reaches the run as a `Failure`.** `Ledger.read` raises
  inside `TriageStore.load`, `_ingest_source` catches it, the previous shard
  stands and the run exits non-zero (1.7). The ledger is deliberately *not* read
  in `scan()`, where an exception would escape `ingest()` as a traceback.

- **`title-number-disagreement` is raised in `_evaluate`.** `title_disagrees` has
  existed since Phase 2 with no caller; the flag joins the run beside the drift
  and term flags.

## Messages, validate and coverage (Phase 6)

- **The words are written where the fault is found; `messages.py` only lays them
  out.** `parse`, `scope`, `pointers`, `terms` and `loader` each phrase their own
  `detail` in the entry's terms, because that is where the entry's terms are
  known. What the module adds is the header — `triage/x.md — "Symptom"` — and
  `rejected:` against `flagged:`. A reason constant is never printed; 5.3 forbids
  a message that is an internal error name, and the closed set is the taxonomy's
  shape rather than something to show an author.

- **`test_messages.py` restates the fifteen constants.** The store it builds holds
  one malformed file per constant plus 1.9's second file, and asserts the reason
  set is *exactly* those fifteen. A reason added to `model.py` with no fixture and
  no message fails there rather than passing unnoticed.

- **The flagged count is by `source_file`, not by `EntryOutcome.flags`.** Parse
  flags — `unknown-frontmatter-key`, `closing-statement-inferred` — are collected
  before any entry outcome exists, so counting entry outcomes reported an entry as
  unflagged while printing its flag row underneath. Both `messages.counts` and
  `scope.report` count the same way now.

- **`dawmans validate` exits non-zero on a rejection as well as a term miss**
  (Decision 14), and on neither under `ingest`. Flags never fail it: `pointer-drifted`
  and `unbacked-cause` are states the design chose over withdrawing working triage,
  and failing on them would pressure an author into deleting it.

- **Validate writes nothing, and the test snapshots the whole tree** rather than
  the files this implementation happens to touch. It goes through `evaluate()`,
  which never calls `_record_resolutions`, and `cli` never loads an embedder on
  that path — there is a `monkeypatch` asserting the second, because "we do not
  call it" is exactly the kind of claim a later refactor breaks silently.

- **`CorpusView.read(view_dir)` is validate's reader**, and it takes the same two
  published shapes `of()` does. Decision 13 split *where the rows come from*
  between the two commands; it did not split the reader.

- **8.7's orphaned entries are a coverage row, not a flag** (Decision 15). The
  design lists `orphaned-scope` among the flags while its own device-scope table
  says a documented device absent from `rig.yaml` scopes with no flag. The
  constant stays in `FlagName` as the row's name with nothing raising it.
  **An empty rig produces no rows at all** — an absent `rig.yaml` is "nothing is
  declared owned", not "everything has been taken away", and without the guard
  every entry on a machine with no rig file reports as orphaned.

- **Coverage counts a device as covered only by an entry that ingests.** A
  rejected entry declaring `akai/apc-key-25` leaves the APC uncovered: the entry
  reaches no question, so nothing triages that device.

- **The report block is built once, in `load()`, and handed to `sidecar()`.**
  `sidecar` used to call `report` itself, so the audit and the sidecar built it
  twice; the coverage rows need the rig, which `scope` does not have, so the
  block is now assembled in the loader and passed down. `report(coverage=None)`
  still writes `"coverage": {}` rather than omitting the key — absent and empty
  are different statements to a reader.

## Pointer resolution and the ledger (`pointers.py`)

- **`resolve` reads passages and nothing else.** No shard, no vector file, no
  PDF, and — the one that matters — no `SourceRecord`. That last exclusion *is*
  8.3: `doc_version` lives on the record, so replacing Live 12 with Live 12.1
  cannot move a pointer on its own. An implementation that consulted
  `sources.json` would pass every example test and quietly break the requirement.

- **The number selects; the title only corroborates.** Where both are given and
  the number names no section, the pointer is unresolved — it does *not* fall
  back to the title. Falling back would silently repair a renumbering, which is
  the event `title-number-disagreement` exists to surface.

- **`title_disagrees` is separate from `resolve` because the signature is
  pinned.** The design fixes `resolve(p, idx) -> list[str] | Unresolved`, which
  has no channel for a flag. The disagreement is a second, pure question over the
  same index rather than a wider return type.

- **Exact titles are looked up before the prefix rule.** Otherwise a title that
  *is* a section reports itself ambiguous against every longer title it happens
  to prefix. Two matches at either stage is `ambiguous-title` with the candidates
  named — never an arbitrary pick, because 54 of Live's titles are duplicated
  across its outline.

- **`normalise_title` strips a leading section number.** Live prints its titles
  with the number attached, so an author copying one out of the manual types
  `18.1 The Live Mixer` and means the section the manual calls `The Live Mixer`.

- **`AUTHORED_SOURCE` is checked before index membership.** The authored source is
  not in any view, so an implementation that tested membership first would call
  2.7's rejection `unknown-source` and hand the author the wrong message.

- **The ledger key is the pointer, and the number wins where there is one.** So
  adding a corroborating title — or letting one go stale — moves no row. Keying
  on the entry would make a cosmetic `devices:` edit withdraw a drifted entry
  under 2.2; that is Decision 4, and there is a property test for it.

- **`check_pointer` never records.** Recording is the caller's move under
  `dawmans ingest` alone, which is what lets `dawmans validate` run the same
  check over the whole store without promoting a broken pointer to "previously
  fine" (5.4).

- **`record` writes only on transition, and transition is detected by the passage
  ids.** The ledger has no "drifted" marker, so "resolved again after a drift" is
  read as "resolves to passages other than the ones the row records". A pointer
  resolving to exactly what it resolved to last time changes nothing, and the
  file written back is byte-identical — which is the only reason a committed
  machine-written file is tolerable.

- **A missing ledger is not an empty one.** `Ledger.read` returns
  `missing=True` on `FileNotFoundError` so the run can emit the one report line
  the design requires; an existing but empty file is `missing=False`. Deleting
  the file re-arms 2.2 for the whole store, and that must not be silent.

## Device scope (`scope.py`)

- **`indexed` is not a set of source ids.** It is every identity the corpus
  documents: each indexed vendor-manual `source_id` *and* the device id it
  declares under `source_applicability`. Those differ wherever a filename
  carries a generation marker the rig id does not — `focusrite/scarlett-solo-4g`
  against `focusrite/scarlett-solo` — and matching source ids alone would report
  the Scarlett as owned-but-undocumented while its guide sits in the corpus, the
  one case the design says is empty today. Decision 8 records it.

- **`RigDevice` is a `Protocol`, not a record.** `rig.yaml` and its type belong
  to `data/manual-corpus` (its `corpus/rig.py`, still a stub). Stating the two
  fields read here structurally means the concrete record satisfies it on
  arrival with no adapter and no second definition of the same data.

- **Recognition and documentation are separate questions.** In the rig *and*
  indexed is silent; in the rig only is `undocumented-device-scope` (4.4) and
  still scopes; indexed only is silent too, because 4.5's condition is
  "neither"; in neither flags, unless *every* declared device is in neither,
  which is a rejection. That last row is the recorded deviation from 4.5's
  literal text — a flag would leave the entry embedded and unreachable.

- **Revision comparison strips to alphanumerics after casefolding.** Not
  either-contains: that would let `@12` and even `@s` satisfy `12 Standard`,
  which is exactly 4.6's mk1/mk2 case. The flag quotes the rig's value verbatim
  so the fix is a copy. A revision on a device the rig does not hold compares
  against nothing and never flags.

- **Two rows of the table have no live instance.** Every rig device is
  documented today, so `tests/triage/fixture_rig.py` carries an invented
  `elektron/digitakt` and a `roland/tr-8s`. Tests against the real inventory
  would also break every time a manual is added.

## The term check (`terms.py`)

- **`terms` takes the `Entry`, not just the `Cause`.** The design sketches
  `terms(cause) -> list[str]`, but two of the rules it states are properties of
  the whole entry: a sentence-start token is kept when it is capitalised
  *elsewhere in the entry*, and a term is discarded when it names one of the
  entry's *declared* devices. The signature is the sketch's, widened by exactly
  what those two rules read.

- **The sentence-start discount is per token, not per run** (Decision 10). The
  design states it for a single-token run; applied that way, an author writing
  the design's own example — "The Track Activator is off" — gets the term
  `The Track Activator`, which is in no manual, and the stated soundness property
  breaks for any statement opening with an article. Discounting the *token*
  before runs are formed yields `Track Activator` and leaves every case the
  design names unchanged. ALL-CAPS is exempt: nothing about a sentence start
  explains `DIRECT`.

- **Corroboration is read over `render(entry)`.** That is the entry as the user
  sees it — symptom, phrasings, preamble, every cause, the closing statement —
  and it deliberately excludes the frontmatter and the pointers. A source id is
  not evidence about English prose, and reading the pointers would let
  retargeting a `fix:` line change which terms a cause yields.

- **The two extractors are disjoint on their first character**, which is how
  `contains` knows which containment rule to apply without the term carrying its
  class. A capitalised run always opens with a letter; a numeric literal opens
  with a digit or a sign. Keeping `terms` returning `list[str]` was the design's
  choice, and this is what pays for it.

- **`\b` is wrong at both ends of a term.** A term may open with `-12` or close
  with `%`, and `\b` would then demand a word character beside it. `_pattern`
  uses `(?<![0-9A-Za-z])` / `(?![0-9A-Za-z])`, which asks the question actually
  meant — not part of a longer word or number — and is what keeps `0` from
  satisfying `10`. The internal gap is `\s+` (`\s*` for numerics) so a control
  name broken across two lines of the manual still counts.

- **Curly and straight apostrophes are folded together** before matching. Manuals
  typeset `Saturator’s` and authors type `Saturator's`; that is two keyboards
  spelling one word, not a relaxation of the case rule.

- **A cause with no resolutions is not checked at all.** 2.3's carve-out and a
  drifted pointer both reach `check_terms` with an empty `resolutions`, and both
  already carry `unbacked` — which says more than a list of terms found in
  nothing would.

- **Case sensitivity has a real cost and it is deliberate.** The Scarlett's front
  panel prints `DIRECT MONITOR` and its guide prints `Direct Monitor`, so an
  author copying the hardware gets a flag. Casefolding would make `Off`,
  `Monitor`, `MIDI` and `Live` match almost any prose and the check close to
  vacuous; there is a test asserting the cost rather than hiding it.

- **The soundness property uses its own extractor.** `test_terms.py` lifts
  capitalised phrases out of the fixture passages with a local regex, not with
  `terms.py`. Stating the property against the module's own extractor would
  assert only that it agrees with itself.

## Building the index, and the fixtures cut from it

`tests/fixtures/sections/*.json` are slices of a **real** view, cut once by
`tools/extract_section_fixtures.py` and committed, so the whole suite runs with
`manuals/` absent, no PDF opened and no embedding model loaded — the same
arrangement `manual-corpus` uses for its extraction snapshots.
`tests/fixtures/README.md` says what each one asserts.

Refreshing them needs an index, and since `manual-corpus` merged there is a
command for it — `uv run dawmans --root . ingest`, with the vendor PDFs in
`manuals/` and `make fetch-model` run once. A real build over the four manuals
took about a minute and produced 1431 passages under `index/views/<hex>/`. Both
`index/` and `models/` are gitignored, so nothing of it lands in a commit. The
earlier note here described hand-composing the stages in the `manual-corpus`
worktree because `cli.py` was a bare docstring; that is no longer true, and a
throwaway driver would now be a second orchestration beside the real one.

Note that `dawmans ingest` now loads the **authored store too**, so a run in a
worktree with entries in `triage/` writes `triage/.pointer-ledger.jsonl`. That is
intended — it is the machine's own committed artefact — but it is a working-tree
change to notice before committing.

Then, from this worktree:

```
uv run python tools/extract_section_fixtures.py <corpus>/index/views/<hex>
```

The extractor exits non-zero rather than writing a short fixture if any section
it names is missing from the view, so a corpus rebuild that drops a section is
caught at extraction rather than as a puzzling test failure later.

**Passage ids survive a rebuild.** The fixtures were first cut from one view and
re-cut from a later one the corpus agent built independently; every byte matched.
`passage_id` is content-derived, so an unchanged manual re-extracts to the same
identifiers — `manual-corpus`'s incremental-equivalence property, observed rather
than assumed. Re-running the extractor against a fresh view is therefore a cheap
way to confirm the corpus has not moved under the fixtures.

## The starter set (Phase 7)

`triage/` at the repository root holds the five committed entries of 7.2–7.6.
They are product content and they are also the grammar's only worked examples, so
a change to either has to satisfy the other.

- **Every pointer names a section that exists in the real index**, and the term
  check passes over the committed fixtures. The two are kept in step by hand:
  `tools/extract_section_fixtures.py`'s `LIVE_SECTIONS` and `ALESIS_SECTIONS`
  list, with a reason each, exactly the sections the starter set points at. Add a
  pointer to an entry and the fixture list needs the section, or
  `test_starter_set.py` reports a `pointer-unresolved` rejection that looks like a
  resolution bug and is not.
- **7.5 forced a fourth manual into the fixtures.** General MIDI mode and the pad
  note numbers are documented by the Nitro Max and by nothing else, so
  `alesis_sections.json` was cut and `sections.CORPUS` is now four files. Pointing
  that cause at Live's §24.6 instead would have resolved and would have passed the
  term check — §24.6 prints "standard GM drum equivalents" — while citing a manual
  about a different control. 2.6 cannot catch that; `test_starter_set.py` asserts
  the cited `source_id` instead.
- **Wording is constrained by the term check in ways worth knowing before
  editing.** Containment is case-sensitive at word boundaries over the cause
  statement plus its `check:`, so the entry has to use the manual's own
  capitalisation. Live's routing chapter prints `Audio/MIDI To` and never
  `Audio To`, which is why 7.2's routing cause is worded the way it is —
  requirement 7.2's own phrasing would flag. Runs break on anything but spaces and
  tabs, so `Track, Sync and Remote` is three terms and not one, and each is
  satisfied by its own `fix:` line under the any-pointer rule. Tokens under three
  characters are dropped, which is the only reason `GM` and `ON` may appear at
  all.
- **Each entry closes with an "Otherwise" section, so each raises
  `closing-statement-inferred`.** Five flags on a clean store is expected, not
  drift: Decision 6 identifies a closing statement by position, so it cannot tell
  an author's note from a cause that lost both its lines, and it flags every one.
  `test_starter_set.py` asserts that this is the *only* flag class, which is what
  makes a term miss or a revision mismatch visible.
- **5.6 is met warm.** 200 synthetic entries ingest and validate in well under a
  second each on this machine, against the 5 s budget. The cold arm is not met and
  is asserted structurally rather than timed:
  `test_the_cold_deviation_is_the_run_s_model_load_and_not_this_source` pins that
  `cli.run_ingest` loads the embedder before reaching any loader. That test is
  meant to fail when `manual-corpus`'s lazy-on-first-embed request lands, which is
  when 5.6's cold arm becomes claimable.
- **7.7 cannot run.** It needs `dawmans.answer`, which does not exist, and a
  configured provider. `test_acceptance.py` runs its corpus-side precondition
  under `make bench` — the five entries are in the committed view with their
  devices, causes and citations — and skips the ask itself, naming the module it
  waits on.

## Test layout

- `tests/triage/stores.py` builds an entry store on disk and the `TriageLoader`
  that reads it, over the committed section fixtures. Every triage test file uses
  it; it was extracted from `test_emission.py` when the discovery and sidecar
  tests needed the same store.
- `tests/triage/runs.py` holds the stub `manuals/` (one region per committed
  section fixture) and `run()`, which drives a real `cli.ingest` over it. Both
  `test_ingest_wiring.py` and `test_validate.py` use it: a command that reads a
  committed view has to have one to read.
- `tests/triage/test_ingest_wiring.py` is the only test that runs the **real**
  loader through `cli.ingest`, with a stub vendor store that rebuilds `manuals/`
  from the same section fixtures. `tests/test_run.py` deliberately keeps a *stub*
  authored store — a run that only ever saw the real one would prove nothing
  about 12.2 — so the two files are complements, not duplicates.
- `tests/triage/test_starter_set.py` is the only test that reads the **committed**
  `triage/` store rather than one built in `tmp_path`, and it evaluates it with an
  empty ledger — the first-ingest case, where an unresolved pointer rejects rather
  than flags.
- `tests/triage/test_acceptance.py` holds 7.7 and 5.6. Its `bench`-marked half
  reads the repository's own `index/`, so it skips wherever that has not been
  built; its timing half runs in CI on a synthetic store.

## Tooling

- `make test` → `uv run pytest`; `make lint` → spelling, `ruff check`,
  `ruff format --check`; `make format` applies the formatting.
- **Ruff is excluded from `specs/`, `docs/` and `manuals/`** in `pyproject.toml`.
  It formats fenced Python inside Markdown, and left unrestricted it rewrites the
  design documents under the implementation.
- `tools/check_spelling.sh` bans US spellings in every tracked file, code
  included — write `normalise`, never the `-ize` form. Its pattern is
  word-bounded, so an identifier burying a US spelling before an underscore
  slips through; do not rely on that. A line containing `spelling-ignore` is
  exempt, for unavoidable external identifiers only. **`tests/fixtures/` is
  skipped wholesale**: those files quote the vendor's own words verbatim, and
  correcting a manual's spelling would make the fixture a document nobody
  shipped. `orbit-impl-1/manual-corpus` carries the identical exclusion for the
  identical reason, so the two copies of this script do not conflict on merge.
- The full package scaffold (whole module tree, `fetch-model`, `bench`, PyMuPDF
  confinement) is `data/manual-corpus` task 1 and is still outstanding. What is
  here is only what Phase 1 needed.
