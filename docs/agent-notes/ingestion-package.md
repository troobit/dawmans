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
  and English selection), and `bm25s` + `numpy` (phase 7, the two index artefacts).
  `numpy` is a transitive dependency of `fastembed` and is declared anyway, because
  `index/build.py` writes `vectors.npy` itself. `pyyaml` comes with phase 8's `rig.yaml`.
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

## Section map and regions — `corpus/pdf/sections.py`

Stage 5. Three structure paths tried in order (embedded outline, printed contents page,
heading styles), then anchoring, then regions.

- **Path C's gate fails closed.** A style qualifies only when its spans start a line, run
  under 60% of the modal line length, do not end in a full stop, and number ≥4 spread over
  ≥40% of pages at ≥1 per ten pages. `cover_only` is the fixture: a title plus a strapline
  clearing a naive "≥2 large spans" test yields two regions spanning 1009 pages, and every
  citation inside them names a wrong section.
- A document is *numbered* only when ≥60% of entries carry a parsed section number;
  otherwise every region is unnumbered and no number is invented (6.4).
- Anchoring resolves each entry to the line its heading is printed on: normalised prefix
  match on the target page **at or after the previous entry's position**, then the page
  either side, then top-of-page with `page-only` recorded. Without the "at or after" bound
  two sections can start on the same line. Anchors are clamped monotonic, because regions
  are half-open intervals between successive anchors.
- A `Position` is `(page index, top, left)` — geometric, not an index into a list, because
  stage 5 orders lines by reading order and stage 7 by row, and both must agree.
- `RegionSpan.page_start/page_end` are the pages the region's **own lines** occupy, not the
  pages its half-open span touches. A region ending at the next section's heading, printed
  as the topmost line of a page, does not reach that page.
- Anchoring clears `Line.furniture` on the line it resolves to — the stage-5 half of
  mark-then-clear.

## Layout — `corpus/pdf/layout.py`

Stage 7's geometry half: `segments(page, lines=…)` returns `Table`s and `Prose` runs in
printed order. It reads furniture marks not at all; `units.py` clears and drops them.

- Rows cluster by top edge within 0.5 × the region's median line height. On Nitro Max p25
  that separates the three-line heading (4.8pt apart, median 8.7) while keeping a row whose
  cells sit 0.35pt apart. It is a genuinely tight margin — if a fixture ever regresses here,
  this is why.
- Columns cluster x0 within 0.02 × page width. Blank lines are dropped before either step:
  the spacer between Nitro Max's panels is a blank span on every row and would otherwise
  become a column with an empty heading, which breaks the panel repeat.
- **Cells are placed by nearest column, never by index** (7.6), which is the whole point of
  the ragged fixture.
- A table run is seeded by ≥3 consecutive rows occupying ≥3 of the same columns with short
  (≤6-word) cells, then grown over neighbouring rows holding **≥2** cells. The ≥2 bound is
  what stops the section title printed above the table — one cell, and within column
  tolerance of column 0 — being swallowed as a heading row.
- Heading rows are the leading rows with no numeric cell (stopping at the first row matching
  the majority occupied-column pattern where the table has no numeric column), joined per
  column with a space: `MIDI Note` + `Number` → `MIDI Note Number`.
- Panels come from the repeated heading sequence — the smallest divisor of the heading tuple
  that tiles it — and never from an x. A table with no heading has one panel, so Nitro Max's
  kit table on p26 serialises as four columns of one panel; only the note table on p25 gets
  a `‖`.
- Prose is ordered by (column, y) only where ≥2 columns each cover ≥60% of the run's height.
  That threshold is what keeps a procedure's gutter of enumerators from being lifted out of
  its steps and read as a column.

## Unit assembly — `corpus/pdf/units.py`

Stage 7 proper: `assemble(document, mapping)` → `Region[]`. The last stage that can discard
anything.

- Order inside the stage: segment the page (furniture marks still in place), clear the mark
  inside every detected table, then drop what is still marked. A table cannot be detected
  from what is left after its rows have been dropped.
- Lines in non-English blocks and every line on a printed contents page contribute nothing.
  The contents-page rule is what makes `live_contents_p13` yield no chunks while staying in
  `page_count` and the 4.4 audit.
- A table row and a numbered procedure are `atomic`; the joined heading is `repeat_on_split`
  and `atomic`. Prose paragraphs are neither.
- A paragraph runs to the end of its extracted block. A numbered procedure overrides that:
  it runs while the enumerators count up, taking in continuation lines set at or right of
  the first step's text indent. Two blocks per procedure is normal — Live extracts the step
  text and the gutter enumerators separately.
- A procedure broken by a page break is rejoined when the next unit's first step is the
  previous unit's last + 1, giving one unit with `page_start` 158 and `page_end` 159 on
  `live_procedure_pagebreak`. That is why `_Built` carries the step numbers alongside the
  `Unit`.
- `has_figures` is per page, from `Page.images` filtered to ≥2% of the page area. Unfiltered
  it sets nearly everywhere on a screenshot-dense manual; chunk scope comes later, by OR
  over the chunk's units.
- A `Region`'s page range is the min/max over its **units**, falling back to the span's own
  range when the region kept nothing.

## The load path — `corpus/pdf/loader.py`

`PdfLoader` is the `vendor-manual` half of the seam (12.4) and the one place the stage order
is written down: extract → furniture mark → glyph repair → section map → language selection
→ unit assembly. Glyph repair precedes language because mojibake skews the identifier;
sectioning precedes selection because anchoring needs the whole document before anything is
dropped.

- Three rejections are decided here — `no-text-layer` (3.3), `unreadable-text` (5.5),
  `no-english-content` (4.5). Each still returns a `SourceRecord` and an audit: the audit is
  written whether a source committed a shard or was rejected.
- `extract_document` opens and closes the PDF itself, so path 1 of glyph repair reopens it —
  but only when the span model actually holds a symbol family, which is the 5.2 s the
  `families` argument exists to avoid.
- `chunk_count` is `UNCHUNKED` (0) and `ingested_at` is load time. The shard build owns both
  final values; `now` is injectable so a test need not freeze the clock.
- `hardware_applicability` is `assumed` for the filename's own product. 11.2 forbids
  inferring it from content, and `rig.py` replaces it where `rig.yaml` declares one.
- `assemble(…, spans=…)` takes stage 5's output back from the loader so the anchor-quality
  audit does not cost a second walk over every line.

## Passage identity — `corpus/passage_id.py`

`passage_id(source_id, text)` = `f"{source_id}#{sha256(canonical(text))[:16]}"`. `canonical` is
NFC, whitespace runs collapsed, stripped — and nothing else. Case is **not** folded.

- `source_id` is a visible prefix, not hashed. Cross-source collisions are impossible by
  construction and `fetch-passage` routes on the prefix.
- `assign_ids(source_id, texts)` owns the duplicate rule and it is **asymmetric on purpose**:
  the first of k identical chunks keeps the bare ID, the rest take `.2`…`.k`. Suffixing all k
  would mean a source newly acquiring a second copy of some boilerplate destroys the stable ID
  of the first copy, whose text did not change. The cost of the asymmetry is pinned by a test:
  a duplicate inserted *before* an existing one does promote.
- `unicodedata.normalize` is imported as `normalised` with a `spelling-ignore` marker.
  `tools/check_spelling.sh` bans the American spelling and cannot tell a stdlib name from
  prose. Note the checker scans **git-tracked files only**, so `make lint` says nothing about a
  new file until it is `git add`ed.
- Determinism is a property of the pipeline, not of this function, and is tested by ingesting
  the same synthetic PDF bytes twice and comparing the whole `(passage_id, text)` sequence.

## The chunker — `corpus/chunk.py`

`chunk_source(record, regions)` → `list[Chunk]`, where `Chunk` is the passage plus what only
the chunker knows: its `header`, the `units` that contributed (copies included), how many words
it `carried` in, and whether it is a marked part of an over-cap atomic unit.

- Packing restarts at every region, so the coverage round-trip, region purity and the overlap
  rules are all region-local. Identifiers are assigned across the **whole source** afterwards,
  because 6.1's duplicate rule is source-scoped.
- `carried` is a **word count**, and it is what makes the round-trip property checkable:
  `chunk.passage.text.split()[chunk.carried:]` concatenated over a region gives the region's
  own words back, in order.
- Pages are the min/max over `_Part.own` — the units whose text originates in this chunk. A
  copied heading and overlap contribute words but not pages. Flags are the OR over
  `_Part.units`, which is copies **plus** own units; the overlap's source unit is deliberately
  not in it, since only a fragment of it is present.
- **A repeat replaces overlap** (Decision 15). Overlap is taken only where the continuation
  copies no `repeat_on_split` unit, which is how `data/symptom-triage`'s "suppress overlap for
  authored regions" is satisfied without an `if kind ==`.
- The repeat run is tracked at *placement* time, not when a unit is popped: a unit that does
  not fit is pushed back and seen twice, and counting it twice copies one heading in twice.
  Repeats are dropped when the next queued unit is itself `repeat_on_split` — that is a second
  table in the same region, and naming columns a row is not in is worse than naming none.
- `partial_unit` marks 7.4's case only: a split of an **atomic** unit. Splitting long prose is
  ordinary 6.8 chunking and is not marked.
- Splits snap to a sentence boundary where one falls inside the room, and fall back to a word
  cut where the first sentence already exceeds it. Overlap snaps the same way, with the same
  fallback bounded to `OVERLAP_WORDS`.
- `check_pages` raises `PageRangeError` for 6.11 — a **failure**, not a rejection — and returns
  immediately for a pageless source. `token_budget(chunks, count)` takes the tokeniser as a
  callable, because the model is loaded by `index/embed.py` and this module must not import it;
  the real-tokeniser test skips unless `models/` has been populated.
- `Region.entry_location` (Decision 14) is the only route CONTRACTS §2's field has to a
  `Passage`: the sidecar is keyed by `passage_id`, which this stage mints.

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

## Embedding — `index/embed.py`

`load_embedder()` is the only thing that touches the model, and it is called **once per
run**, before iterating sources. The cold load is ~7.2 s against 8.4's 10 s budget for a
whole new source, so `build_shard` takes an `Embedder` and never makes one.

- Order inside `load_embedder`: `pin_offline()` (sets `HF_HUB_OFFLINE=1` in the process
  environment), *then* the cache check, *then* `from fastembed import TextEmbedding`.
  Pinning after the check would leave a run that recovered from the failure able to reach
  the network on its next attempt.
- `cache_is_populated` looks for any `tokenizer.json` under `models/`. The snapshot
  directory carries a content hash, so the file is found rather than spelled — and it is
  the same file `count_tokens` loads, so a cache that passes the check serves both halves.
- A missing cache raises `ModelCacheMissing`, a **failure**: 1.6's rejection list has no
  member for it, because no source is at fault and nothing can be embedded.
- The wrapper owns float32, 384 wide and L2-normalised rather than trusting the backend,
  and raises on a wrong width. A backend of another dimension reaching the view under a
  manifest declaring 384 is invisible: the on-disk shape is unchanged.
- `count_tokens` loads `tokenizers.Tokenizer` from the cache directly and lazily.
  `fastembed`'s own tokeniser is not published surface, and laziness is what lets a test
  construct an `Embedder` against a fake cache.
- `Embedding` (model, dim, normalised) is the manifest block **and** three of the four
  shard cache-key components. `Embedding.from_dict({})` is `None`, not a default: a shard
  predating the block cannot be shown to match, so it is rebuilt.

## Lexical index — `index/lexical.py`

`bm25s` over the same passage ordering as `vectors.npy`. Document `i`, row `i` and line
`i` are one passage, which is what lets `api/answer-engine` fuse the two rankings.

- `tokenise` keeps a compound **whole and then in parts**: `Dry/Wet` → `dry/wet`, `dry`,
  `wet`. Separators are `-/._`. A run of them collapses to the first, so `mid--side` is
  what a user typing `mid-side` reaches.
- `tests/test_lexical.py` asserts the *default* `bm25s.tokenize` loses `Dry/Wet`,
  `4th-gen` and `bge-small-en-v1.5` before asserting ours keeps them. Without that half,
  a regression to the default would pass a test written only against our own output.
- **No stopword list**, deliberately: `bm25s`'s English list holds `on` but not `off`, so
  applying it makes one half of every On/Off control unretrievable and leaves the other.
- `bm25s` cannot index an empty vocabulary — `index([])` and `index([[]])` both raise — so
  an empty corpus is indexed as one `\x00empty` placeholder document. No tokeniser output
  can equal it (every real token starts alphanumeric) and `document_count`, stored beside
  the index, keeps it out of every result.
- `search` drops zero-scoring hits: `retrieve` pads its top-k, and padding is
  indistinguishable from a match otherwise. Ranking beyond that ordering is Decision 2's
  hand-off to `api/answer-engine`.

## Shard build, merge and commit — `index/build.py`, `index/manifest.py`

- **The shard's `passages.jsonl` is a cache, not the view's contract.** Its lines are
  `{"passage": …, "header": …}`; the view's are the bare CONTRACTS §2 record. The header
  has to be on disk somewhere — Decision 2 indexes it with the text, it contains
  `Region.section_path`, and §2 has no field for that — and a reused shard runs no loader,
  so it could not otherwise be re-indexed. `Shard.entries()` reads both, `passages()`
  projects.
- Reuse is `Shard.reusable(CacheKey)`: all four of fingerprint, `ingestion_version`,
  `embedding.model`, `embedding.dim`. `read_shard` returns `None` for an absent *or
  unparseable* meta — both mean "cannot be shown to match", and neither is fatal.
- The `vectors` map (`passage_id` → row) is written for the **authored** shard only, by
  the `vector_map` argument defaulting off the record's kind. The mechanism is kind-neutral;
  the default follows the design's granularity note. `_embed` checks the three
  non-per-passage components *before* consulting the map, so a model change re-embeds
  everything.
- Write order inside `build_shard`: passages, vectors, sidecar, meta — each to `.tmp`
  beside its destination — then `os.replace` in that order, **meta last**. A partly
  committed set carries no meta and reads as no shard. Any exception unlinks the pending
  `.tmp` files and raises `ShardWriteFailed`.
- `np.save` appends `.npy` to a filename that lacks it, which would turn
  `x.vectors.npy.tmp` into `x.vectors.npy.tmp.npy`. Every call here writes through an open
  file handle to avoid that.
- `commit_view` sorts by `source_id` and refuses to merge a shard whose embedding differs
  from the run's — the same silent failure the cache key guards, caught again where the
  concatenation happens.
- `view_name(revision, built_at, attempt)` folds in the timestamp, so two runs over
  identical content get different directories; `attempt` covers the wreckage of a run that
  died before renaming its manifest. `_fresh_view` never builds over an existing directory.
- `collect_views` runs at the **start** of a run. A missing manifest collects nothing —
  "names no view" must not mean "delete everything", or the first run after a failed one
  empties the index.
- `read_manifest` **raises** `IndexVersionMismatch` rather than returning `None`: absent
  and unreadable are different answers and only one of them is a rebuild.
- `tests/test_incremental_equivalence.py` is the test that catches an incremental path
  quietly diverging from the rebuild it optimises. Its `ingest()` helper is the run order
  `cli.py` (task 44) has to implement: collect views → discover → remove absent → ingest
  only the sources whose key does not match → merge → rename.

## Synthetic PDFs — `tests/pdfgen.py`

The extraction tests cannot open a reference PDF and cannot build one with PyMuPDF (the
AGPL ban applies to `tests/` too), so `pdfgen.py` writes minimal PDFs by hand:
uncompressed streams, base-14 fonts, one xref table. Text is positioned from the **top**
of the page, the way PyMuPDF reports bboxes, with a `Text`'s `y` being its baseline.
`Image(resolution=N)` writes N×N uncompressed RGB pixels, which is how the 10.4 test makes
one file a hundred times larger than another with the same text layer. Task 45's timing
tests want synthetic PDFs too.
