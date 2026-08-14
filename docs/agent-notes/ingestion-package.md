# The `dawmans` ingestion package

Python side of the repo: `src/dawmans/`, one installable package, managed with uv.
Implements `specs/data/manual-corpus`. SvelteKit owns the browser surface and is a
separate tree.

## Layout and tooling

- `src/` layout, `pyproject.toml` at the repo root, hatchling build backend. Everything
  runs through the Makefile: `build` (`uv sync`), `test` (`uv run pytest`), `lint`
  (spelling + `ruff check` + `ruff format --check`), `clean`, `fetch-model`, `fixtures`,
  `bench`.
- uv resolved to Python 3.12 (`requires-python = ">=3.12"`).
- Dependencies arrive with the code that uses them. Declared so far: `pymupdf` (task 1,
  for the AGPL rule to have something to bite on), `fastembed` (needed by
  `make fetch-model`), and `fonttools` + `lingua-language-detector` (phase 4, glyph repair
  and English selection). `bm25s` and `pyyaml` come with their phases.
- `ruff format` rewrites Python code blocks **inside Markdown**, which would reflow the
  deliberately aligned samples in `specs/`. `extend-exclude = ["*.md"]` in `pyproject.toml`
  stops it; do not remove that line.
- `tools/check_spelling.sh` scans every git-tracked file, source included, and is
  case-sensitive. Write `normalised`, `initialise`, `serialise` in Python too — a
  banned word in a docstring fails `make lint`. `tests/fixtures/` is skipped: those files
  quote vendor manuals verbatim, and "correcting" a manual's spelling would make the
  fixture a document nobody shipped.

## The AGPL confinement

PyMuPDF is AGPL-3.0-or-later, so publishing this repository conveys a combined work
under the same licence (`decision_log.md` Decision 6). It may be imported **only** under
`src/dawmans/corpus/pdf/`, which keeps the constraint on the ingestion tool and away
from the process `api/answer-engine` runs. Two mechanisms enforce it, deliberately:

- `[tool.ruff.lint.flake8-tidy-imports.banned-api]` bans `fitz` and `pymupdf`, with a
  per-file-ignore for `src/dawmans/corpus/pdf/*`. Fast, but it reads one file at a time.
- `tests/test_agpl_confinement.py` walks the package AST, so `make test` catches it too,
  including `importlib.import_module("fitz")`, which the linter does not see.

## Records

`records.py` is CONTRACTS §1 and §2 verbatim — no field added, none dropped, asserted by
`tests/test_records.py` against the field set itself. Both records are frozen, slotted
and keyword-only so they read in the CONTRACTS table's order.

Non-obvious constructor rules, all of them from the spec rather than from taste:

- Kind-dependent fields are enforced **both ways**: an `authored-triage` source refuses
  `vendor`/`product`/`doctype`/`lang`/`doc_version`/`page_count`/`low_text`, and a
  `vendor-manual` requires all seven. 9.1 asks for "not applicable" rather than an
  invented value, and a `None` on a manual would be exactly such an invention.
- An `authored-triage` record is pinned to `source_id == "authored/triage"` and
  `hardware_applicability.status == "assumed"` (CONTRACTS §1).
- `hardware_applicability` is a small record of `(status, device, revision)` — the shape
  of a `rig.yaml` `source_applicability` entry, which is where it comes from.
- `Passage` has no `kind` field, so the pageless rule keys on
  `source_id == AUTHORED_SOURCE_ID`: no `section_number`, `page_start` or `page_end`,
  and `entry_location` required. A paged passage is the mirror image — pages required,
  `entry_location` refused — because CONTRACTS §2 makes them alternatives ("absent on a
  `vendor-manual`, which has a page instead"). If a second pageless kind ever appears,
  this is the line to revisit.
- `ingested_at` is an ISO-8601 UTC **string**, not a `datetime`: it goes straight into
  `sources.json` and the shard meta, and a string needs no encoder.

`version.py` holds `INGESTION_VERSION`, bumped by hand whenever anything from extraction
through chunking could change a chunk's text or metadata. It is a shard cache-key
component: without a bump, a fixed ingestion bug reaches nothing, because no PDF byte
changed and every shard is reused.

## The loader seam

`corpus/loader.py` is interfaces only — no behaviour and no validation, on purpose, so
there is no test task in front of it. `SourceLoader` is the protocol both stores
implement; `data/symptom-triage` supplies `TriageLoader` and it is not written here.
Everything downstream of `Region` is shared code, which is what makes requirement 12.2
structural rather than a set of `if kind ==` branches.

`Unit` carries `page_start` **and** `page_end` because a procedure that fits the chunk
cap may still span p11–p12, and 6.10 forbids splitting it.

## Discovery — `corpus/discover.py`

Stage 1. Reads directories and hashes bytes; opens no PDF. Two halves, one module:

**The filename grammar.** `FILENAME_PATTERN` is one anchored expression and
`SourceIdentity.filename` is its exact inverse, because `api/answer-engine` rebuilds the
name from a `SourceRecord`'s own fields (CONTRACTS §3a, §4e). Two details that look like
nits and are not:

- `doc_version` is stored **without** the leading `v`, so the inverse is
  `_v{doc_version}_` and never `_vv1.0_`.
- Digits are `[0-9]`, not `\d`. Python's `\d` matches Arabic-Indic and other scripts'
  digits, which would admit a name two other specs must rebuild byte for byte.
- `display_name` is mechanical title-casing of vendor + product: `akai_apc-key-25` →
  `Akai Apc Key 25`. Ugly on acronyms and deliberate — the version is never appended,
  because CONTRACTS §3 already shows `doc_version` inline on the citation.

A file whose suffix is not `.pdf` (case-insensitively) is skipped silently per 1.3;
`FOO.PDF` therefore reaches the grammar and is *rejected*, rather than vanishing. That is
the intended reading: silently skipping a mis-named PDF loses it with no report line.

**Store scanning.** `StoreScan.available` is the whole point of the type. An absent,
unreadable or not-a-directory store returns `available=False`, meaning its discovery set
is **unknown**, and `remove_absent_sources` removes nothing for it. Only an existing,
empty store yields an empty set and removes its shards. Without that split an unmounted
volume deletes every authored passage and reports success.

Other non-obvious rules here:

- Removal is keyed on the `store` recorded in `shards/<slug>.meta.json`, not on which
  scan is running, so 9.5's "never test a source of one kind against the other kind's
  store" holds by construction. A shard from a store this run did not scan at all is
  kept, same as an unavailable one.
- A shard goes with its `.sidecar.json` and its `audits/<slug>.json`.
- A **rejected** source is not in `source_ids`, so its shard is removed — otherwise an
  answer could cite a source the run refused to index.
- An unparseable shard meta is skipped, never deleted: it names no store and no source,
  so nothing can tell whether its shard is stale.
- `discover_stores()` is the run-level pass, and it exists for exactly one case:
  `authored_triage_notes_v1_en.pdf` is legal grammar and lands on the authored store's
  constant `authored/triage`. Neither store's own scan can see that, and the slug rule
  cannot either (both sides form `authored_triage`), so the collision is caught on
  `source_id` and rejected in both stores under 2.6.
- `fingerprint_changed()` is only the **fingerprint** component of the shard cache key.
  `index/build.py` owns the other three (`ingestion_version`, embedding model, dimension)
  at task 34/35; a fixed ingestion bug changes no PDF byte and must still re-ingest.

`data/symptom-triage` owns the authored store (`triage/` at the repo root) and supplies
its own `StoreScan`; tests here build one by hand to stand in for `TriageLoader`.

## `make bench`

`bench` guards on `manuals/*.pdf` (gitignored, so a fresh clone has none) and runs
`pytest -m bench`. Pytest exits 5 when no test matches the marker; the target treats
that as "no benchmark registered yet" and succeeds. Requirement 8.1 needs the real
PDFs, so CI cannot verify it.

## Extraction — `corpus/pdf/extract.py`

Stage 2, and the **only** module that opens a PDF. Everything after it annotates the
model it returns rather than re-reading the document, so `Line.furniture`,
`Span.unmappable` and `Block.lang`/`Block.english` are extraction-time defaults that
later stages set. That is why `Span`, `Line`, `Block` and `Page` are mutable dataclasses
and only `TocEntry` is frozen.

- `EXTRACT_FLAGS = TEXTFLAGS_DICT & ~TEXT_PRESERVE_IMAGES`. Not tidiness: with the
  default set, PyMuPDF decodes every image into a type-1 block carrying an `image` key of
  raw bytes. Measured on Live's p471, 52 ms with the flag against 3 ms without.
  `PRESERVE_IMAGES` is re-exported so a test can name the bit without importing PyMuPDF,
  which the AGPL rule bans outside this package.
- Images are still recorded, as `Page.images` — placement rectangles from
  `page.get_image_info()`, which reports geometry without decoding pixels. The 2%-of-page
  figure threshold (10.3) is **not** applied here; it belongs to the stage that needs it.
- `Document.has_text_layer` counts non-blank spans on **non-furniture** lines, so its
  value changes once stage 3 has run. That is deliberate — it is the 3.3 definition, and
  the case it catches is a scanned manual whose only extractable text is a stamped page
  number.
- `Document.low_text` divides by the document's own `page_count`, which is preserved even
  when only a page range was extracted (fixture capture does exactly that).
- `Document.to_dict`/`from_dict` is the fixture format. Annotations are written only when
  set, so a fresh extraction snapshot carries none of them and a hand-written fixture can
  set them. `SNAPSHOT_SCHEMA` is checked on load.

Measured against the real corpus (2026-08-15): 1107 pages in 3.99 s, of which Live 12 is
3.45 s. Requirement 8.2 allows 5 s for the corpus, so the headroom is 25% and it slopes
with page count — the design's ~1 s estimate was extrapolated from a *layout* extraction
and is corrected in §Build budget.

## Furniture — `corpus/pdf/furniture.py`

Stage 3, and it **only marks**. `Line.furniture` is cleared again by sectioning (a chapter title
printed in the header band) and by table detection (a table reaching into the band), and the drop
happens at the end of stage 7. Nothing here deletes text, and a test asserts the whole span model
is byte-identical afterwards but for the marks.

- Candidates are lines lying wholly inside the top or bottom 8% of the page box, non-blank.
- The key is casefold + collapsed whitespace + digit runs to `#`, which is what makes `471` on
  p471 and `472` on p472 one key. Digits are `[0-9]`, not `\d`.
- Two rules: a key on ≥60% of pages (or ≥5 pages of a document of ≤10) **at a consistent y-band**,
  and a digits-only line, which skips both the threshold and the band test.
- **Both stop at more than one page.** The design states the digits-only rule with no repetition
  bound, but the furniture-safety property forbids suppressing a key that occurs on exactly one
  page, so the bound applies to both. That property is the only real guard here: suppressed text
  produces no diff and no error.
- Consistency is measured from the *nearer* page edge, so a header and a footer are never one key
  at one height, and pages of different sizes still compare.
- On this corpus the digits-only rule does all the work — all three guides print a bare page
  number — and the repeated-key rule is for the next manual that prints a running title.

## Glyph repair — `corpus/pdf/glyphs.py`

Stage 4. The APC Key 25's four Clip Stop arrows are `Wingdings3` with a ToUnicode CMap that maps
the font's 0x70/71/74/75 into Latin-1 (+0x80), so they extract as `ð, ñ, ô, õ`. **Repair cannot
come from ToUnicode: ToUnicode is the fault.**

- Detection is font-keyed **and** letter-keyed: a symbol family emitting a non-ASCII *letter*. The
  letter half matters — the same page sets its bullets in `Symbol`, and `•` is a symbol that
  arrived intact. Repairing it would be the corruption.
- The corruption table is keyed on `(family, code point the extractor returned)` — 0xF0/F1/F4/F5,
  **not** the published Wingdings 3 codes. The four characters are `▲▼◀▶`, read off the rendered
  page rather than from a chart; the fixture pins them.
- Path 1 (embedded glyph names) is implemented and, on this corpus, returns nothing: the APC's
  Wingdings3 subset has **no `post` table at all**. `glyph_names()` accepts only `post` format 2.0
  — fontTools will otherwise invent an order from the `cmap`, and those names are not evidence.
- `embedded_names(doc, families)` takes the families `document_symbol_families()` found in the span
  model. Passing them is not an optimisation: walking Live 12's 1009 pages' resources to discover
  there is no symbol font measured **5.2 s**; with the families it is 0.03 s.
- The module imports no PyMuPDF. It calls `get_fonts`, `get_texttrace` and `extract_font` on
  whatever it is handed, which is what lets the wiring be tested with a stub.
- The 5.5 denominator is every extracted character **after furniture marking, before language
  selection**. Repair itself runs over furniture too, because the mark can still be cleared.
- Measured: APC 60 spans repaired, none degraded; Live nothing to do.

## English selection — `corpus/pdf/language.py`

Stage 6, `lingua` (models bundled in the package, so offline), constrained to `en/es/fr/it/de`.

- **A source declared with one ISO 639-1 code is never scored.** The detector is not called at all,
  4.5 cannot fire, and the 4.4 audit lists every page as included.
- Scoring is per block. A block under 8 words, or one the identifier is under 0.5 confident about,
  inherits: nearest scored block above on the page, else below, else the page's own decision. Pages
  resolve the same way — predecessor, else successor, else included.
- The `and predominantly non-alphabetic` half of the design's guard is **superseded** (Decision 12):
  it let `• Mac OS X : Live > Preferences` on the French page be trusted at 0.42, and the French
  step below inherited from it. Confidence alone is a strict superset, so the tables the guard was
  written for are still kept.
- `partial_pages` ⊆ `english_pages`. The design's illustrative audit puts page 1 in both `excluded`
  and `partial`, which cannot both hold; the property in §Testing Strategy governs.
- Measured on the real APC guide: `english [[1,6],[23,24]]`, `excluded [[7,22]]`, no partial pages,
  0.05 s. Pages 1, 2 and 24 are cover and back matter with nothing scorable on them, so they
  inherit and are included.
- `lingua`'s `IsoCode639_1` is a Rust-backed class: attribute access works, subscripting and
  iteration do not.

## Fixtures — `tests/fixtures/`, `tools/capture_fixture.py`, `make fixtures`

The vendor PDFs are gitignored, so the guides enter the test suite as committed extraction
snapshots. `capture_fixture.FIXTURES` is the record of which pages of which guide each
fixture is and what it asserts; the same note is copied into each file's header.
`tests/test_pdf_fixtures.py` asserts every fixture still holds what it was captured for,
which matters because the stages that consume them are phases 4 and 5.

Things that are not obvious:

- **Every manual in the corpus has an embedded outline** — Live 1054 entries, APC 38,
  Nitro Max 28, Scarlett 72 — so section-map paths B and C have no live instance. The
  design said the APC had neither outline nor contents page; it was wrong. `apc_no_toc`
  and `cover_only` are captured with `--toc none` (decision_log Decision 10).
- **Live's contents pages have no dot leaders.** The page numbers are a separate
  right-hand column of bare numerals, extracted ahead of the titles. Path B's grammar
  detects the Nitro Max contents page and not Live's, and the exclusion of contents pages
  from chunking cannot rest on leaders alone.
- **`live_procedure_pagebreak` (Live pp158–159) extracts its enumerators after the step
  text.** `1.`–`4.` are set in a left gutter and come out as their own lines at the end of
  the page. Any chunker reading extraction order alone loses the pairing; only row
  assembly on geometry recovers it.
- **`apc_p14_arrows`, not `apc_p3_arrows`.** p3 of the v1.0 guide carries no symbol font,
  and no page holds both the Wingdings3 run and a genuine Spanish `ñ`. p14 is better than
  what the design asked for: U+00F4 appears on it twice, once as a Wingdings3 arrow and
  once inside a French word in the body face, so character-keyed repair provably corrupts
  the second.
- **Redaction masks character classes** (letters → `x`/`X`, digits → `0`) rather than
  dropping the text, and the test is `str.isalpha()` so accented characters go too —
  `[a-zA-Z]` would leave the very characters that identify a line's language. The
  language labels in a redacted fixture are hand-written ground truth, so it exercises the
  *selection* machinery and never the language identifier (Decision 11).
- Fixture JSON is written with leaf objects on one line, which halves the file against
  `indent=1` while staying diffable. `tests/test_pdf_fixtures.py` caps a fixture at 1 MB.

## Synthetic PDFs — `tests/pdfgen.py`

The extraction tests cannot open a reference PDF and cannot build one with PyMuPDF (the
AGPL ban applies to `tests/` too), so `pdfgen.py` writes minimal PDFs by hand:
uncompressed streams, base-14 fonts, one xref table. Text is positioned from the **top**
of the page, the way PyMuPDF reports bboxes, with a `Text`'s `y` being its baseline.
`Image(resolution=N)` writes N×N uncompressed RGB pixels, which is how the 10.4 test makes
one file a hundred times larger than another with the same text layer. Task 45's timing
tests want synthetic PDFs too.
