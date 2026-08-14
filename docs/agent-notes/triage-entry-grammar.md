# Triage entry grammar (`dawmans.triage`)

How the `authored-triage` entry format is parsed. Spec: `specs/data/symptom-triage/`.
Phase 1 of that ledger is implemented — the model, the grammar and the canonical
rendering. Pointer resolution, the ledger, the term check, device scope, emission
and the loader are Phases 2–7 and are not written yet.

## Modules

| Module | Holds |
|---|---|
| `model.py` | the five frozen dataclasses of design 'Components and Interfaces', plus `RejectionReason`, `FlagName`, `EntryRejection` and `Flag` |
| `parse.py` | `parse_entry(source_file, data) -> ParseResult`, and `render(entry) -> str` |
| `pointers.py` | `parse_pointer(text, line) -> Pointer \| None`. `SectionIndex` and `resolve` are Phase 2 |

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

## Tooling

- `make test` → `uv run pytest`; `make lint` → spelling, `ruff check`,
  `ruff format --check`; `make format` applies the formatting.
- **Ruff is excluded from `specs/`, `docs/` and `manuals/`** in `pyproject.toml`.
  It formats fenced Python inside Markdown, and left unrestricted it rewrites the
  design documents under the implementation.
- `tools/check_spelling.sh` bans US spellings in every tracked file, code
  included. `normalise`, not `normalize`. Note that `\b` means an identifier like
  `normalized_title` slips through on the underscore — do not rely on that.
- The full package scaffold (whole module tree, `fetch-model`, `bench`, PyMuPDF
  confinement) is `data/manual-corpus` task 1 and is still outstanding. What is
  here is only what Phase 1 needed.
