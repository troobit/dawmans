# Triage entry grammar (`dawmans.triage`)

How the `authored-triage` entry format is parsed. Spec: `specs/data/symptom-triage/`.
Phases 1 and 2 are implemented — the model, the grammar, the canonical rendering,
pointer resolution and the ledger — plus device scope validation (tasks 11–12,
stream 2). The term check, emission and the loader are still outstanding.

**Phase 2 is no longer blocked, and the block it was under is worth knowing how
to clear.** It needed a locally built index, which needed both human
prerequisites in `manual-corpus`'s `prerequisites.md`. Both are met: `rig.yaml`
now exists in that spec's worktree carrying the Scarlett mapping, and
`make fetch-model` has been run once on this machine. See §Building the index for
what remains a one-off by hand. Scope validation had been reachable before all
this because it reads the rig and the corpus's identity vocabulary, neither of
which needs an index.

**Phase 4 is blocked too, and `rune` does not show it.** Its blocked-by names only
task 3, so `rune streams --available` reports task 13 ready; in fact it needs
`corpus.passage_id` and `manual-corpus` 12.5's `SourceRecord` constructor, which
CONTRACTS §1 forbids this spec redefining. Cross-spec dependencies are not
expressible in the ledger — every remaining task here has one. `corpus/passage_id.py`,
`corpus/chunk.py`, `records.py` and the loader seam types do now exist, but on the
unmerged `orbit-impl-1/manual-corpus` branch; Phase 4 becomes reachable when that
merges, ahead of Phase 2 and without waiting for an index.

That merge is available now and does not wait on the corpus agent. Everything Phase 4
needs is already committed at `4f0ea7c` — `records.py` `SourceRecord` (its
`authored/triage` arm enforcing 12.5) and `passage_id(source_id, text)`; the work still
uncommitted in that worktree is all under `index/`, which Phase 4 never touches. The
merge is not clean, but nothing in it is a semantic clash: `git merge-tree` reports seven
files where the two branches independently grew the same shared scaffolding — `.gitignore`,
`CHANGELOG.md`, `Makefile`, `pyproject.toml`, `specs/OVERVIEW.md`, `src/dawmans/__init__.py`,
`uv.lock`. Both rewrote the Makefile's `$(error unconfigured)` stubs and both created
`__init__.py` with a different docstring; PROCESS.md §9 already rules `OVERVIEW.md`
(regenerate, never hand-merge) and `uv.lock` is `uv lock`. So the block on Phase 4 is a
decision about what belongs on this branch, not a missing artefact — worth resolving once
rather than re-checking each run. Phase 2 stays blocked either way: its two prerequisites
are human-only.

## Modules

| Module | Holds |
|---|---|
| `model.py` | the five frozen dataclasses of design 'Components and Interfaces', plus `RejectionReason`, `FlagName`, `EntryRejection` and `Flag` |
| `parse.py` | `parse_entry(source_file, data) -> ParseResult`, and `render(entry) -> str` |
| `pointers.py` | `parse_pointer`, `normalise_title`, `SectionIndex`, `resolve`, `title_disagrees`, and the ledger — `pointer_key`, `Ledger`, `check_pointer` |
| `scope.py` | `validate_scope(entry, rig, indexed) -> ScopeResult` — design 'Device scope' |

The design's 'Module placement' names only behaviour modules. `model.py` is an
addition, and it earns its place: the rejection and flag vocabularies are needed
by `parse`, `pointers`, `scope` and `coverage` alike, and putting them in
`parse.py` would make `pointers.py` import the module that imports it.

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
  does not round-trip through `parse_entry`. Phase 4's canonical-idempotence
  property will have to reconcile that; the design states there is no second
  canonical form.

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

## Building the index, and the fixtures cut from it

`tests/fixtures/sections/*.json` are slices of a **real** view, cut once by
`tools/extract_section_fixtures.py` and committed, so the whole suite runs with
`manuals/` absent, no PDF opened and no embedding model loaded — the same
arrangement `manual-corpus` uses for its extraction snapshots.
`tests/fixtures/README.md` says what each one asserts.

Refreshing them needs an index, which today means the `manual-corpus` worktree,
because that spec's `cli.py` — its task 44, the run orchestration — is still a
bare docstring. There is no `dawmans ingest` to call. The stages are all finished
and compose directly:

```
PdfLoader(root=manuals/).scan()      -> discovery, per source
loader.load(discovered)              -> LoadResult(record, regions)
chunk_source(record, regions)        -> chunks
build_shard(index/, record=..., chunks=..., store=..., fingerprint=..., embedder=...)
commit_view(index/, shards=read_shards(index/), embedding=embedder.descriptor)
```

Roughly forty lines, run once with `uv run python` from that worktree; a real
build over the four manuals took about a minute and produced 1431 passages under
`index/views/<hex>/`. Both `index/` and `models/` are gitignored, so nothing of
this lands in a commit. Write the driver as a throwaway and delete it — it is
task 44's job, and leaving a second orchestration behind is how two of them drift
apart.

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
