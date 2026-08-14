# Triage entry grammar (`dawmans.triage`)

How the `authored-triage` entry format is parsed. Spec: `specs/data/symptom-triage/`.
Phase 1 of that ledger is implemented — the model, the grammar and the canonical
rendering — plus device scope validation (tasks 11–12, stream 2). Pointer
resolution, the ledger, the term check, emission and the loader are still
outstanding.

**Phase 2 is blocked on `data/manual-corpus`**, not deferred: task 4 extracts the
section fixtures from a locally built index, and 5–8 are blocked on 4. The gate
is a committed `views/<hex>/passages.jsonl` — `manual-corpus` task 37, the atomic
view commit — plus the human prerequisites in its `prerequisites.md` (the one-off
`make fetch-model`, and the Scarlett mapping in `rig.yaml`). A task count is the
wrong thing to check here; check for that file. Scope validation was reachable
because it reads the rig and the corpus's identity vocabulary, neither of which
needs a built index.

**Phase 4 is blocked too, and `rune` does not show it.** Its blocked-by names only
task 3, so `rune streams --available` reports task 13 ready; in fact it needs
`corpus.passage_id` and `manual-corpus` 12.5's `SourceRecord` constructor, which
CONTRACTS §1 forbids this spec redefining. Cross-spec dependencies are not
expressible in the ledger — every remaining task here has one. `corpus/passage_id.py`,
`corpus/chunk.py`, `records.py` and the loader seam types do now exist, but on the
unmerged `orbit-impl-1/manual-corpus` branch; Phase 4 becomes reachable when that
merges, ahead of Phase 2 and without waiting for an index.

## Modules

| Module | Holds |
|---|---|
| `model.py` | the five frozen dataclasses of design 'Components and Interfaces', plus `RejectionReason`, `FlagName`, `EntryRejection` and `Flag` |
| `parse.py` | `parse_entry(source_file, data) -> ParseResult`, and `render(entry) -> str` |
| `pointers.py` | `parse_pointer(text, line) -> Pointer \| None`. `SectionIndex` and `resolve` are Phase 2 |
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
  exempt, for unavoidable external identifiers only.
- The full package scaffold (whole module tree, `fetch-model`, `bench`, PyMuPDF
  confinement) is `data/manual-corpus` task 1 and is still outstanding. What is
  here is only what Phase 1 needed.
