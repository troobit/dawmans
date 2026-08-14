---
references:
    - specs/data/manual-corpus/requirements.md
    - specs/data/manual-corpus/design.md
    - specs/data/manual-corpus/decision_log.md
    - specs/CONTRACTS.md
---
# Manual Corpus

## Phase 1: Project scaffold and shared records

- [x] 1. Scaffold the Python package and build tooling <!-- id:e7lsx1t -->
  - src/ layout, one installable package `dawmans`, managed with uv; pytest + hypothesis + ruff as dev dependencies.
  - Makefile: replace the unconfigured build/test/lint/clean targets, and add `fetch-model` (one-off model cache population) and `bench` (the 8.1 full-corpus timing, skipped when manuals/ is empty).
  - Create the package directory tree of design 'Module placement' with empty modules; gitignore index/ and models/.
  - PyMuPDF is declared here but may only be imported under dawmans/corpus/pdf/ (AGPL confinement, Decision 6) - add a lint rule or test that fails on an import elsewhere.
  - Stream: 1
  - Requirements: [8.5](requirements.md#8.5)
  - References: specs/data/manual-corpus/design.md

- [x] 2. Write tests for the SourceRecord and Passage constructors <!-- id:e7lsx1u -->
  - Assert the constructor refuses a value for a field CONTRACTS 1 marks not applicable to the record's kind: vendor, product, doctype, lang, doc_version, page_count and low_text on an authored-triage source.
  - Assert an authored-triage SourceRecord carries source_id exactly `authored/triage` and hardware_applicability `assumed`, and that a Passage from a pageless source has section_number, page_start and page_end absent rather than defaulted.
  - Assert no field outside the CONTRACTS 1/2 tables can be set - the record shape is the contract.
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1), [12.1](requirements.md#12.1), [12.5](requirements.md#12.5), [12.8](requirements.md#12.8)
  - References: specs/CONTRACTS.md

- [x] 3. Implement records.py and version.py <!-- id:e7lsx1v -->
  - dawmans/records.py: frozen dataclasses SourceRecord and Passage, CONTRACTS 1 and 2 verbatim, kind-dependent fields typed `| None`.
  - dawmans/version.py: INGESTION_VERSION integer, with a comment stating it is bumped by hand whenever extraction through chunking could alter a chunk's text or metadata.
  - Blocked-by: e7lsx1u (Write tests for the SourceRecord and Passage constructors)
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1), [12.1](requirements.md#12.1), [12.5](requirements.md#12.5), [12.8](requirements.md#12.8)

- [x] 4. Define the loader seam types <!-- id:e7lsx1w -->
  - dawmans/corpus/loader.py: SourceLoader protocol (discover/load), Discovered, LoadResult, Region, Unit, UnitFlags, Rejection - the design's Components and Interfaces section verbatim.
  - Unit carries page_start and page_end as two fields so a procedure spanning p11-p12 keeps both ends.
  - The protocol is the seam that makes 12.2 structural: everything from Region onwards is shared code. TriageLoader is implemented by data/symptom-triage and is not written here.
  - Interfaces only - no behaviour, so no preceding test task.
  - Blocked-by: e7lsx1v (Implement records.py and version.py)
  - Stream: 1
  - Requirements: [12.2](requirements.md#12.2), [12.4](requirements.md#12.4), [12.6](requirements.md#12.6)

## Phase 2: Discovery and source identity

- [ ] 5. Write tests for the filename grammar and source identity <!-- id:e7lsx1x -->
  - Grammar accept/reject table against the anchored expression: kebab-case fields, dotted version (v12, v1.0, v2.10.3), lang as ISO 639-1 or `multi`; a rejected filename reports the offending name and the expected pattern.
  - Round-trip property: for every accepted filename, `f"{vendor}_{product}_{doctype}_v{doc_version}_{lang}.pdf"` reproduces it exactly - doc_version is stored without the leading `v` (2.7).
  - source_id is `<vendor>/<product>` with no version; display_name is the title-cased vendor and product with no version appended.
  - Slug injectivity: `/`->`_` keeps `a/b-c` and `a-b/c` distinct; assert `-` would collide.
  - Two files resolving to one source_id reject both; a non-PDF in manuals/ is skipped with no report line.
  - The grammar applies to vendor-manual only - an authored source is not tested against it (12.5).
  - Blocked-by: e7lsx1w (Define the loader seam types)
  - Stream: 1
  - Requirements: [1.3](requirements.md#1.3), [2.1](requirements.md#2.1), [2.2](requirements.md#2.2), [2.3](requirements.md#2.3), [2.4](requirements.md#2.4), [2.5](requirements.md#2.5), [2.6](requirements.md#2.6), [2.7](requirements.md#2.7), [12.5](requirements.md#12.5)

- [ ] 6. Implement the filename grammar and identity derivation <!-- id:e7lsx1y -->
  - dawmans/corpus/discover.py: the anchored expression, identity derivation, slug rule, and collision detection by grouping on source_id before any work.
  - Blocked-by: e7lsx1x (Write tests for the filename grammar and source identity)
  - Stream: 1
  - Requirements: [1.3](requirements.md#1.3), [2.1](requirements.md#2.1), [2.2](requirements.md#2.2), [2.3](requirements.md#2.3), [2.4](requirements.md#2.4), [2.5](requirements.md#2.5), [2.6](requirements.md#2.6), [2.7](requirements.md#2.7), [12.5](requirements.md#12.5)

- [ ] 7. Write tests for store scanning, fingerprints and removal <!-- id:e7lsx1z -->
  - A missing or unreadable store removes no shard and reports the store unavailable; an existing empty store removes its shards. This is the test that stops an unmounted volume deleting every authored passage.
  - Removal is scoped by the store recorded on the shard, so 9.5 never tests a source of one kind against the other kind's store.
  - sha256 over file bytes as the fingerprint; a changed fingerprint marks the source for re-ingestion.
  - Discovery finds both stores in one run, with no hard-coded list of expected sources.
  - Blocked-by: e7lsx1y (Implement the filename grammar and identity derivation)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2), [1.4](requirements.md#1.4), [9.2](requirements.md#9.2), [9.3](requirements.md#9.3), [9.5](requirements.md#9.5), [12.3](requirements.md#12.3)

- [ ] 8. Implement store scanning, fingerprinting and removal <!-- id:e7lsx20 -->
  - Extend discover.py with both stores, the unknown-vs-empty distinction, and removal of a shard plus its sidecar and audit.
  - Blocked-by: e7lsx1z (Write tests for store scanning, fingerprints and removal)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2), [1.4](requirements.md#1.4), [9.2](requirements.md#9.2), [9.3](requirements.md#9.3), [9.5](requirements.md#9.5), [12.3](requirements.md#12.3)

## Phase 3: PDF extraction and fixtures

- [ ] 9. Write tests for PDF extraction and the span model <!-- id:e7lsx21 -->
  - Extraction of a screenshot-dense fixture page yields no type-1 block and no image key carrying bytes - TEXT_PRESERVE_IMAGES must be cleared, which is what makes 10.1 and 10.4 hold at once.
  - Zero extracted non-furniture spans across every page is the no-text-layer rejection (3.3); a sparse but present layer sets low_text and is ingested.
  - low_text is words / page_count computed on extracted text before language selection - assert a multilingual guide is not flagged for having translations.
  - Line boxes and the leading enumerator (`1.`, bullet) survive, so a procedure reads as discrete steps; every span keeps its page, bbox, font name, size and flags.
  - Figure captions present in the text layer are indexed as ordinary text.
  - Blocked-by: e7lsx1w (Define the loader seam types)
  - Stream: 1
  - Requirements: [3.1](requirements.md#3.1), [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.4](requirements.md#10.4)

- [ ] 10. Implement corpus/pdf/extract.py <!-- id:e7lsx22 -->
  - page.get_text("dict", flags=...) per page into Page/Line/Span, with the default flag set minus TEXT_PRESERVE_IMAGES.
  - Physical 1-based page indices are what is recorded, not printed page numbers.
  - Blocked-by: e7lsx21 (Write tests for PDF extraction and the span model)
  - Stream: 1
  - Requirements: [3.1](requirements.md#3.1), [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.4](requirements.md#10.4)

- [ ] 11. Add the fixture-capture tool and commit the extraction snapshots <!-- id:e7lsx23 -->
  - manuals/ is gitignored, so no test may open a reference PDF: fixtures are committed extraction snapshots that pin the extractor's output as an explicit input to every downstream test.
  - Write a developer command that dumps a page range's span geometry, font names and text to JSON, with a redaction mode that keeps bbox, font and a language label only.
  - Capture the nine fixtures named in design 'Fixtures': nitro_max_p25, apc_p3_arrows, apc_pages (redacted - full span text for 24 pages would commit substantially the whole guide), live_toc_slice, live_contents_p13, live_procedure_pagebreak, apc_no_toc, cover_only, furniture_pages.
  - Also build the rejection fixtures: image-only PDF, malformed filename, two files colliding on source_id, and a source over the 2% unmappable threshold.
  - Requires the vendor PDFs present locally - see prerequisites.md.
  - Blocked-by: e7lsx22 (Implement corpus/pdf/extract.py)
  - Stream: 1
  - Requirements: [3.1](requirements.md#3.1)
  - References: specs/data/manual-corpus/prerequisites.md

## Phase 4: Text conditioning

- [ ] 12. Write tests for furniture marking <!-- id:e7lsx24 -->
  - Property - furniture safety: no line whose normalised key occurs on exactly one page is ever suppressed.
  - A repeated right-aligned page number in the top or bottom 8% band is marked; a numeric line inside a detected table on one page is not.
  - Stage 3 only marks. Assert nothing is deleted here - clearing is stages 5 and 7, and the drop is at the end of stage 7.
  - Blocked-by: e7lsx23 (Add the fixture-capture tool and commit the extraction snapshots)
  - Stream: 1
  - Requirements: [3.6](requirements.md#3.6)

- [ ] 13. Implement corpus/pdf/furniture.py <!-- id:e7lsx25 -->
  - Normalise a band line to a key (casefold, collapse whitespace, digit runs to `#`); mark a key occurring on >=60% of pages, or >=5 pages in a document of <=10, at a consistent y-band, plus any digits-only line in those bands.
  - Blocked-by: e7lsx24 (Write tests for furniture marking)
  - Stream: 1
  - Requirements: [3.6](requirements.md#3.6)

- [ ] 14. Write tests for glyph detection and repair <!-- id:e7lsx26 -->
  - Against apc_p3_arrows: the Wingdings3 run at U+00F0/F1/F4/F5 repairs to arrows, and a genuine Spanish n-tilde in the body face on the same fixture is left alone - detection is font-keyed, not character-keyed, with no condition on neighbouring spans.
  - A mutated span with no mapping sets degraded and yields U+FFFD in Passage.text; assert the raw characters are never indexed as words, so BM25 cannot match them.
  - The corruption table is keyed on the code point the extractor returns after ToUnicode (0xF0/F1/F4/F5), not the published Wingdings 3 codes - pin the resulting characters so a wrong entry fails a test rather than reaching a user.
  - The 5.5 denominator is every character extracted from the text layer, counted after furniture suppression and before language selection; assert a 2% arrow ratio in a quarter-English guide is not inflated to 8% by selection.
  - Over 2% unmappable is a rejection with reason `unreadable-text`; counts glyph_spans_repaired, glyph_spans_degraded and unmappable_char_ratio reach the source's audit.
  - Blocked-by: e7lsx23 (Add the fixture-capture tool and commit the extraction snapshots)
  - Stream: 1
  - Requirements: [5.1](requirements.md#5.1), [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [5.4](requirements.md#5.4), [5.5](requirements.md#5.5)

- [ ] 15. Implement corpus/pdf/glyphs.py <!-- id:e7lsx27 -->
  - Mapping in order: embedded glyph names via extract_font + fontTools post table through the Adobe Glyph List, using get_texttrace() for raw glyph ids; then the static corruption table keyed on (family, extracted code point); then unmappable.
  - Most subsetters emit post v3.0 with no glyph names, so for a novel symbol font the realistic outcome is degraded with 5.5 as the backstop - do not build the first path up into something it cannot be.
  - Blocked-by: e7lsx26 (Write tests for glyph detection and repair)
  - Stream: 1
  - Requirements: [5.1](requirements.md#5.1), [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [5.4](requirements.md#5.4), [5.5](requirements.md#5.5)

- [ ] 16. Write tests for English content selection <!-- id:e7lsx28 -->
  - A source declared with a single ISO 639-1 code is not scored at all: assert Live's keyboard-shortcut chapter (3,979 words, 24 sentence-final stops over 23 pages) is fully included, and that its audit lists every page as included.
  - Detection runs only where lang is `multi`, at block granularity; against apc_pages, pp3-6 and p23 are selected and pp7-22 excluded with no page range anywhere in the code (4.2, 4.6).
  - Short blocks (<8 words) inherit from the nearest scored block above, else below, else the page's predecessor; the first page of a document with no scored block anywhere is included.
  - Language-neutral blocks - top confidence <0.5 and predominantly non-alphabetic tokens - inherit the same way, so the MIDI note table and the specifications table are not discarded as non-English.
  - Property - audit completeness: included union excluded is every page, the two are disjoint, and partial is a subset of included.
  - No English content at all is the `no-english-content` rejection.
  - Assert the APC front page's printed language index is not parsed - it is exactly the per-manual structure 4.2 forbids depending on.
  - Blocked-by: e7lsx23 (Add the fixture-capture tool and commit the extraction snapshots)
  - Stream: 1
  - Requirements: [4.1](requirements.md#4.1), [4.2](requirements.md#4.2), [4.3](requirements.md#4.3), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [4.6](requirements.md#4.6)

- [ ] 17. Implement corpus/pdf/language.py <!-- id:e7lsx29 -->
  - lingua-py, offline, constrained to the languages present in the corpus plus English, returning confidence values; writes the english_pages / excluded_pages / partial_pages audit.
  - Blocked-by: e7lsx28 (Write tests for English content selection)
  - Stream: 1
  - Requirements: [4.1](requirements.md#4.1), [4.2](requirements.md#4.2), [4.3](requirements.md#4.3), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [4.6](requirements.md#4.6)

## Phase 5: Sectioning, layout and region assembly

- [ ] 18. Write tests for the section map and its three structure paths <!-- id:e7lsx2a -->
  - Path A (embedded outline, >=2 entries), path B (a page >=60% dot-leader matches, with the number group optional), path C (heading styles) tried in that order; none is per-manual configuration.
  - Path C's quality gate is the dangerous one: against cover_only, a title plus strapline must fail the gate and yield one titled region, not two bogus regions spanning the whole document. A style qualifies only when its spans start a line, are under 60% of the modal line length, do not end in a full stop, and number >=4 spread over >=40% of pages at >=1 per ten pages.
  - A document is numbered when >=60% of entries carry a parsed section number; otherwise every region is unnumbered and no number is invented (apc_no_toc renders citations with no section number).
  - Printed contents pages are excluded from chunking on every document, not only when path B is chosen: live_contents_p13 contributes no text while staying in page_count and the 4.4 audit.
  - Property - section-number round-trip: parse(render(number, title)) is identity across both printed forms `24.1 Title` and `(1.3.1) Title`.
  - Path C regions carry `inferred`, and the report records the heading count and the qualifying style.
  - Blocked-by: e7lsx23 (Add the fixture-capture tool and commit the extraction snapshots)
  - Stream: 1
  - Requirements: [6.3](requirements.md#6.3), [6.4](requirements.md#6.4), [6.5](requirements.md#6.5), [6.6](requirements.md#6.6)

- [ ] 19. Implement corpus/pdf/sections.py section map <!-- id:e7lsx2b -->
  - The three paths, the path C quality gate, the numbered-document threshold, and dot-leader page detection applied to every page of every document.
  - Blocked-by: e7lsx2a (Write tests for the section map and its three structure paths)
  - Stream: 1
  - Requirements: [6.3](requirements.md#6.3), [6.4](requirements.md#6.4), [6.5](requirements.md#6.5), [6.6](requirements.md#6.6)

- [ ] 20. Write tests for TOC anchoring, the parent chain and region derivation <!-- id:e7lsx2c -->
  - Live averages 1.2 TOC entries per page, so page-granular attribution breaks the citation: against live_toc_slice, text on a page shared by two sections is attributed to the right one.
  - Anchor scan order - normalised prefix match at or after the previous entry's position on that page, then the target page +/-1, then top-of-page with `anchor: page-only` recorded so weak sectioning is visible rather than silent.
  - The parent chain is load-bearing: `Sidechain Parameters` occurs eight times in Live's TOC, so assert a region under 28.21 Glue Compressor carries the device name in section_path while Passage.section_title stays the leaf.
  - Contiguous pages before the first anchor and after the last region are titled regions, named by their own printed title if it passes path C's style test, else Front matter / Back matter.
  - Property - TOC cover: derived regions are ordered, non-overlapping, and together with front and back matter cover every page exactly once.
  - Blocked-by: e7lsx2b (Implement corpus/pdf/sections.py section map)
  - Stream: 1
  - Requirements: [6.5](requirements.md#6.5), [6.6](requirements.md#6.6), [6.7](requirements.md#6.7)

- [ ] 21. Implement anchoring and region derivation <!-- id:e7lsx2d -->
  - Anchoring clears the furniture mark on any line a section anchor resolves to (the stage 5 half of the mark-then-clear ordering).
  - Region.section_path holds the nearest two ancestors.
  - Blocked-by: e7lsx2c (Write tests for TOC anchoring, the parent chain and region derivation)
  - Stream: 1
  - Requirements: [6.5](requirements.md#6.5), [6.6](requirements.md#6.6), [6.7](requirements.md#6.7)

- [ ] 22. Write tests for row, column and table assembly <!-- id:e7lsx2e -->
  - Property - row integrity: for a generated cell grid with x/y jitter inside tolerance, recovered rows equal generated rows, including ragged rows. Cells are placed by x-position, never by index.
  - nitro_max_p25 is the acceptance fixture: all 19 trigger-to-note pairs recoverable with their printed pairings across two ragged panels (11 rows left, 8 right). Pairing by row index silently mis-associates every row past the eighth - assert that failure is caught.
  - The three-physical-line heading joins to `Trigger | MIDI Note Number | Trigger | MIDI Note Number`; the naive reading treats `MIDI Note` as a data row and loses `Number`.
  - Panel boundaries come from the repeated heading sequence, never a hardcoded x; rows serialise in printed order with the boundary marked, and the page is never reordered into per-panel runs (7.2's precedence rule).
  - Prose with >=2 full-height columns orders by (column, y); tabular content orders by (row, x) and gets no column segmentation.
  - Blocked-by: e7lsx23 (Add the fixture-capture tool and commit the extraction snapshots)
  - Stream: 1
  - Requirements: [7.1](requirements.md#7.1), [7.2](requirements.md#7.2), [7.3](requirements.md#7.3), [7.6](requirements.md#7.6)

- [ ] 23. Implement corpus/pdf/layout.py <!-- id:e7lsx2f -->
  - Row clustering by y-overlap at 0.5x median line height, column clustering of x0 at 0.02x page width, tabular classification at >=3 consecutive rows sharing >=3 columns with short cells, and heading-row joining per column.
  - Blocked-by: e7lsx2e (Write tests for row, column and table assembly)
  - Stream: 1
  - Requirements: [7.1](requirements.md#7.1), [7.2](requirements.md#7.2), [7.3](requirements.md#7.3), [7.6](requirements.md#7.6)

- [ ] 24. Write tests for unit assembly and the furniture drop <!-- id:e7lsx2g -->
  - Stage 7 clears the furniture mark inside detected table regions, then drops what is still marked - assert text is discarded exactly once, and that furniture_pages' in-table numeric line survives while the repeated page number does not.
  - A numbered procedure and a table row are emitted atomic; the joined table heading is emitted repeat_on_split.
  - has_figures uses page.get_images() filtered to a placed area >=2% of the page, or a screenshot-dense manual sets it almost everywhere and it stops discriminating.
  - A unit spanning a page break keeps both page_start and page_end (live_procedure_pagebreak): p11 to p12.
  - Region.units order is preserved and no stage reorders them - data/symptom-triage 1.5 depends on it.
  - Blocked-by: e7lsx25 (Implement corpus/pdf/furniture.py), e7lsx27 (Implement corpus/pdf/glyphs.py), e7lsx29 (Implement corpus/pdf/language.py), e7lsx2d (Implement anchoring and region derivation), e7lsx2f (Implement corpus/pdf/layout.py)
  - Stream: 1
  - Requirements: [3.5](requirements.md#3.5), [3.6](requirements.md#3.6), [6.7](requirements.md#6.7), [6.10](requirements.md#6.10), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [10.3](requirements.md#10.3)

- [ ] 25. Implement unit assembly and the vendor-manual load path <!-- id:e7lsx2h -->
  - Assemble Region[] from the annotated span model, and wire PdfLoader to the SourceLoader protocol: extract, furniture mark, glyph repair, section map, language selection, unit assembly.
  - Stage order is load-bearing - glyph repair before sectioning before language, because a run of mojibake inside English prose skews a language identifier and anchoring needs the whole document before anything is dropped.
  - The PDF-specific stages run for vendor-manual only (12.4).
  - Blocked-by: e7lsx2g (Write tests for unit assembly and the furniture drop)
  - Stream: 1
  - Requirements: [3.5](requirements.md#3.5), [3.6](requirements.md#3.6), [6.7](requirements.md#6.7), [6.10](requirements.md#6.10), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [10.3](requirements.md#10.3), [12.4](requirements.md#12.4)

## Phase 6: Chunking and passage identity

- [ ] 26. Write property tests for passage_id <!-- id:e7lsx2i -->
  - Determinism over the whole pipeline, not just the hash function: ingesting the same PDF bytes twice yields an identical (passage_id, text) sequence.
  - Sensitivity - any text change alters the id; a whitespace-only or NFC-form change does not. Case is preserved, since two chunks differing only in case are different text.
  - Metadata invariance - perturbing doc_version, page offsets or section numbers leaves every id unchanged (also data/symptom-triage 8.2-8.3).
  - Uniqueness - ids are pairwise distinct within a source, including for byte-identical chunks.
  - Duplicate stability, and it is asymmetric on purpose: where k chunks share a digest the first in document order keeps the unsuffixed id and the rest take `.2`..`.k`, so newly acquiring a second copy of some boilerplate does not destroy the stable id of the first copy and orphan a citation held in retained UI history.
  - entry_location never enters the digest (CONTRACTS 2).
  - Blocked-by: e7lsx1v (Implement records.py and version.py)
  - Stream: 1
  - Requirements: [6.1](requirements.md#6.1)

- [ ] 27. Implement corpus/passage_id.py <!-- id:e7lsx2j -->
  - NFC, collapse whitespace, sha256 of the body text; source_id is the visible prefix and is not hashed, so cross-source collisions are impossible by construction and a fetch can route on the prefix without a lookup.
  - Blocked-by: e7lsx2i (Write property tests for passage_id)
  - Stream: 1
  - Requirements: [6.1](requirements.md#6.1)

- [ ] 28. Write tests for the chunker and the citation header <!-- id:e7lsx2k -->
  - Property - cap: no chunk exceeds 350 words unless it is a marked part of an over-cap atomic unit.
  - Property - coverage round-trip: over the packing type that records each chunk's overlap length, concatenating a region's chunks and removing the recorded overlap reproduces the region's text in order.
  - Property - region purity: every chunk's (section_number, section_title) equals exactly one region's; overlap never crosses a region boundary or an atomic unit.
  - Property - page attribution: a chunk's page range covers only pages its own non-copied, non-overlap units occupy. Without this a split table's continuation chunk records p25-26 from a heading copied off p25 while every row it holds is on p26, and open-at-page lands on a page containing none of the quoted rows.
  - Property - flag aggregation: degraded, has_figures and unbacked are the OR over all the chunk's units, copied units included, so a chunk of degraded rows stays degraded. unbacked and entry_location are carried through unchanged and never set here (12.6).
  - Every chunk from a split table repeats the joined heading; a single row over the cap splits and each part is marked as carrying part of one row.
  - The citation header is embedded and BM25-indexed but is not part of Passage.text; the section marker and number are omitted entirely rather than rendered as a null when section_number is absent. Three header forms: numbered, unnumbered, pageless authored.
  - Token budget: every chunk's header-prefixed encoding is under 512 BGE tokens, and any chunk within 32 tokens of the window is listed in the run report.
  - 6.11 - a chunk page outside the source's page range is a failure, not a rejection: it names the offending chunk and page, keeps the source's previous shard, and exits non-zero. Assert it is skipped entirely for a pageless source (12.8).
  - A pageless source records no page number, page range or page count and none is synthesised.
  - Blocked-by: e7lsx2j (Implement corpus/passage_id.py)
  - Stream: 1
  - Requirements: [6.2](requirements.md#6.2), [6.7](requirements.md#6.7), [6.8](requirements.md#6.8), [6.9](requirements.md#6.9), [6.10](requirements.md#6.10), [6.11](requirements.md#6.11), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [12.6](requirements.md#12.6), [12.8](requirements.md#12.8)

- [ ] 29. Implement corpus/chunk.py <!-- id:e7lsx2l -->
  - Greedy packing within one region at a 350-word cap, ~50 words of overlap snapped to a sentence boundary, and the emission contract table of design 'Region/Unit -> Passage' - every Passage field comes from exactly one rule there.
  - Blocked-by: e7lsx2k (Write tests for the chunker and the citation header)
  - Stream: 1
  - Requirements: [6.2](requirements.md#6.2), [6.7](requirements.md#6.7), [6.8](requirements.md#6.8), [6.9](requirements.md#6.9), [6.10](requirements.md#6.10), [6.11](requirements.md#6.11), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [12.6](requirements.md#12.6), [12.8](requirements.md#12.8)

## Phase 7: Index build and commit

- [ ] 30. Write tests for the embedding wrapper and offline enforcement <!-- id:e7lsx2m -->
  - With networking disabled and HF_HUB_OFFLINE=1 set in the ingestion process's own environment, ingestion of a fixture corpus succeeds with the model cache present.
  - With the cache absent it fails immediately, naming the model, the cache directory and `make fetch-model` - a failure, not a rejection, since no source is at fault and nothing can be embedded.
  - The model is loaded once per run, before iterating sources: assert the cold load is not paid per source. This is what makes 8.4 achievable at all - a 7.2 s cold load inside a 10 s budget leaves nothing.
  - Output is float32, 384-dimensional and L2-normalised.
  - Blocked-by: e7lsx1v (Implement records.py and version.py)
  - Stream: 2
  - Requirements: [8.5](requirements.md#8.5)

- [ ] 31. Implement index/embed.py and the model-cache target <!-- id:e7lsx2n -->
  - fastembed wrapper over bge-small-en-v1.5 with cache_dir pointed at a gitignored models/ at the repository root.
  - `make fetch-model` populates it once per machine, deliberately outside the ingestion path.
  - Blocked-by: e7lsx2m (Write tests for the embedding wrapper and offline enforcement)
  - Stream: 2
  - Requirements: [8.5](requirements.md#8.5)

- [ ] 32. Write tests for the lexical index and its tokeniser <!-- id:e7lsx2o -->
  - `Dry/Wet`, `4th-gen`, `bge-small-en-v1.5` and bare numerals (38, 74) survive tokenisation as retrievable terms - this is the failure Decision 2 names and the one that is otherwise silent, because a default tokeniser drops them and nothing errors.
  - Exact-term and meaning-based matching must be available over the same set of passages; neither alone satisfies 8.8.
  - Blocked-by: e7lsx1v (Implement records.py and version.py)
  - Stream: 2
  - Requirements: [8.8](requirements.md#8.8)

- [ ] 33. Implement index/lexical.py <!-- id:e7lsx2p -->
  - bm25s wrapper with a tokeniser that preserves hyphenated, slashed and numeric tokens; saved as the view's lexical/ directory.
  - Blocked-by: e7lsx2o (Write tests for the lexical index and its tokeniser)
  - Stream: 2
  - Requirements: [8.8](requirements.md#8.8)

- [ ] 34. Write tests for shard build, the cache key and per-passage vector reuse <!-- id:e7lsx2q -->
  - A shard is reused only when all four of fingerprint, ingestion_version, embedding.model and embedding.dim match. Assert both silent failures the fingerprint-only key allows: changing the embedding model must re-embed every shard rather than concatenating vectors from two models under a manifest declaring one, and bumping ingestion_version must re-ingest even though no PDF byte changed.
  - Authored per-passage reuse: editing one entry re-embeds that entry's passages and copies every other row by passage_id from the shard meta's vectors map; changing the embedding model re-embeds all of them. The shard is still rewritten wholesale, so 9.4 is unaffected.
  - ingested_at is the time the shard was built and is carried through reuse unchanged, so a skipped source does not look freshly ingested.
  - Rollback is scoped to the failing source: artefacts are written to .tmp and moved with os.replace, a failed source's .tmp files are deleted and its previous shard is untouched, and a source that succeeded in the same run commits and stays queryable.
  - A single new vendor-manual of <=50 pages ingests without re-extracting, re-chunking or re-indexing any unchanged source of either kind.
  - Blocked-by: e7lsx2l (Implement corpus/chunk.py), e7lsx2n (Implement index/embed.py and the model-cache target), e7lsx2p (Implement index/lexical.py)
  - Stream: 1
  - Requirements: [8.3](requirements.md#8.3), [8.4](requirements.md#8.4), [8.7](requirements.md#8.7), [9.3](requirements.md#9.3), [9.4](requirements.md#9.4)

- [ ] 35. Implement index/build.py shard build and commit <!-- id:e7lsx2r -->
  - shards/<slug>.passages.jsonl, .vectors.npy, .sidecar.json and .meta.json, with meta carrying the full SourceRecord, the store name, the four-part cache key and the authored vectors map.
  - Blocked-by: e7lsx2q (Write tests for shard build, the cache key and per-passage vector reuse)
  - Stream: 1
  - Requirements: [8.3](requirements.md#8.3), [8.4](requirements.md#8.4), [8.7](requirements.md#8.7), [9.3](requirements.md#9.3), [9.4](requirements.md#9.4)

- [ ] 36. Write tests for the merge, the manifest and the view commit <!-- id:e7lsx2s -->
  - manifest.sources is sorted by source_id, and sorting is load-bearing: filesystem iteration order could change row_start offsets between two runs over an identical source set while corpus_revision - hashed over sorted triples - stayed the same, leaving a consumer slicing the wrong rows.
  - Row i of vectors.npy corresponds to line i of passages.jsonl; row_start and row_count make source scoping a slice, not a scan (8.10).
  - Every Passage and SourceRecord field is readable from the view with no access to any source PDF, including kind, hardware_applicability and entry_location (8.9, 9.6, 11.6, 12.7); sources.json carries no filesystem path.
  - corpus_revision changes when and only when indexed content changes; a reader whose expected index_version differs refuses to load rather than interpreting the files.
  - The view is built into a fresh views/<hex>/ and manifest.json is renamed into place last, so that rename is the only switch - a reader sees the old manifest with the old view or the new with the new, never a mix.
  - Sidecar revision pairing: every passage_id keyed in a view's reports/<slug>.json is present in that view's passages.jsonl, and a second run that rewrites the authored shard leaves the previous view's sidecar byte-identical.
  - Sidecar survives reuse: a run in which every shard is reused still produces a view holding each source's sidecar, copied from the shard rather than regenerated - a sidecar produced only by load() would be absent from every view built after the run that produced it.
  - Audit lifetime: a rejected source's index/audits/<slug>.json is still readable after two later runs have superseded the view it accompanied; removing the source deletes its audit and its shard sidecar.
  - Views not named by the live manifest are deleted at the start of the next run, not immediately, so a reader still working from the previous manifest keeps its files.
  - A full rebuild from the two stores alone reproduces the index with no other input (8.6).
  - Blocked-by: e7lsx2r (Implement index/build.py shard build and commit)
  - Stream: 1
  - Requirements: [8.6](requirements.md#8.6), [8.8](requirements.md#8.8), [8.9](requirements.md#8.9), [8.10](requirements.md#8.10), [8.11](requirements.md#8.11), [9.4](requirements.md#9.4), [9.6](requirements.md#9.6), [11.6](requirements.md#11.6), [12.7](requirements.md#12.7)

- [ ] 37. Implement the merge, index/manifest.py and the atomic view commit <!-- id:e7lsx2t -->
  - The merged view is a plain concatenation of committed shards - re-ingestion replaces a source's shard wholesale, which is 9.4, because nothing merges from anywhere else.
  - Copy each shard's sidecar into views/<hex>/reports/<slug>.json; the two report directories are named differently on purpose, so a reader resolving the wrong one gets an error rather than a well-formed JSON document keyed by something else.
  - Blocked-by: e7lsx2s (Write tests for the merge, the manifest and the view commit)
  - Stream: 1
  - Requirements: [8.6](requirements.md#8.6), [8.8](requirements.md#8.8), [8.9](requirements.md#8.9), [8.10](requirements.md#8.10), [8.11](requirements.md#8.11), [9.4](requirements.md#9.4), [9.6](requirements.md#9.6), [11.6](requirements.md#11.6), [12.7](requirements.md#12.7)

- [ ] 38. Write the incremental-equivalence property test <!-- id:e7lsx2u -->
  - For a random source set and a random add/edit/remove sequence, incremental ingestion yields the same merged passages as a full rebuild. This is the test that catches an incremental path that quietly diverges from the rebuild it is supposed to be an optimisation of.
  - Blocked-by: e7lsx2t (Implement the merge, index/manifest.py and the atomic view commit)
  - Stream: 1
  - Requirements: [8.3](requirements.md#8.3), [8.7](requirements.md#8.7), [9.4](requirements.md#9.4)

## Phase 8: Reports, rig inventory and the CLI

- [ ] 39. Write tests for the rig inventory and the two gap reports <!-- id:e7lsx2v -->
  - rig.yaml is hand-maintained and committed, with device ids in the same <vendor>/<product> shape as source_id so matching is exact and never fuzzy; the rig inventory is never derived from manuals/ - what is documented is not evidence of what is owned.
  - An undeclared source is `assumed` for the product named in its filename; nothing is ever recorded as `confirmed` by default, and applicability is never inferred from content.
  - Both reports compute over source_applicability.device, not over source_id - a manual can document a device whose id is not its own product, and comparing against source IDs silently ignores it.
  - owned-but-undocumented excludes authored-triage sources: a triage entry naming a device must not make that device look documented.
  - documented-but-unconfirmed is restricted to devices in the rig inventory - without that qualifier every undeclared source is reported, including manuals for gear the owner does not hold, and the report stops meaning anything. Revision comparison is casefold-and-strip.
  - Against the real rig: owned-but-undocumented is EMPTY and documented-but-unconfirmed names akai/apc-key-25. Assert the empty report is still emitted as an empty member of gaps.json, never omitted (11.4) - a consumer distinguishing absent from empty breaks on the day it fills.
  - The non-empty owned-but-undocumented case is asserted against a fixture rig declaring a device with no indexed source, since the real corpus can no longer produce it.
  - indexed-but-not-owned (11.7): a source whose resolved applicability device is not in the rig inventory is named in the run report and never in gaps.json. Assert the diagnostic pairing - drop the Scarlett's source_applicability declaration and BOTH focusrite/scarlett-solo (owned-but-undocumented) and focusrite/scarlett-solo-4g (indexed-but-not-owned) appear, which is the only signal separating a missing declaration from a real gap.
  - The authored source's source-level applicability is fixed at `assumed` and nothing in rig.yaml sets it.
  - Blocked-by: e7lsx1v (Implement records.py and version.py)
  - Stream: 2
  - Requirements: [11.1](requirements.md#11.1), [11.2](requirements.md#11.2), [11.3](requirements.md#11.3), [11.4](requirements.md#11.4), [11.5](requirements.md#11.5), [11.6](requirements.md#11.6), [11.7](requirements.md#11.7)

- [ ] 40. Implement corpus/rig.py and gaps.json <!-- id:e7lsx2w -->
  - Also author the initial rig.yaml at the repository root with the four declared devices and both source_applicability entries - Live's confirmed applicability and the Focusrite mapping - per the design's worked example.
  - The Focusrite mapping is mandatory, not optional (11.7): focusrite/scarlett-solo-4g -> device focusrite/scarlett-solo, revision 4th-gen, status confirmed. Omit it and the manual is present while its device reports as undocumented.
  - gaps.json is written into the view before the manifest rename, with both members always present even when empty.
  - Blocked-by: e7lsx2v (Write tests for the rig inventory and the two gap reports)
  - Stream: 2
  - Requirements: [11.1](requirements.md#11.1), [11.2](requirements.md#11.2), [11.3](requirements.md#11.3), [11.4](requirements.md#11.4), [11.5](requirements.md#11.5), [11.6](requirements.md#11.6), [11.7](requirements.md#11.7)

- [ ] 41. Write tests for the per-run report and the per-source audits <!-- id:e7lsx2x -->
  - Per-run report lists every source as ingested, skipped as unchanged, or rejected with its reason; filename-invalid additionally reports the expected pattern.
  - The rejection reasons are a closed set - filename-invalid, source-id-collision, no-text-layer, no-english-content, unreadable-text, authored-invalid - and anything not in it is a failure. Assert an unlisted condition cannot be reported as a rejection.
  - A rejection continues the run and reports it as succeeded; a failure continues the remaining sources and exits non-zero with every failure listed, with no abort-on-first-failure path.
  - The audit at index/audits/<slug>.json is written as each source finishes, whether it committed a shard or was rejected, and carries the English ranges, glyph counts, anchor quality and the rejection reason.
  - The 9.1 inventory reports every SourceRecord field from the CONTRACTS 1 table, reporting a field that table marks not applicable as not applicable rather than inventing a value, and adds no field of its own.
  - 9.5 anomalies are reported per store, in both directions.
  - The indexed-but-not-owned line (11.7) renders from the value rig.py supplies, and is never an error and never in gaps.json. A stub value is enough here - report.py renders it, it does not compute it.
  - Blocked-by: e7lsx20 (Implement store scanning, fingerprinting and removal)
  - Stream: 1
  - Requirements: [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.7](requirements.md#1.7), [4.4](requirements.md#4.4), [5.4](requirements.md#5.4), [9.1](requirements.md#9.1), [9.5](requirements.md#9.5), [11.7](requirements.md#11.7)

- [ ] 42. Implement report.py <!-- id:e7lsx2y -->
  - The per-run report and the per-source ingestion audits; a reused shard's audit is not rewritten, because it describes the run that produced the shard.
  - Blocked-by: e7lsx2x (Write tests for the per-run report and the per-source audits)
  - Stream: 1
  - Requirements: [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.7](requirements.md#1.7), [4.4](requirements.md#4.4), [5.4](requirements.md#5.4), [9.1](requirements.md#9.1), [9.5](requirements.md#9.5), [11.7](requirements.md#11.7)

- [ ] 43. Write end-to-end tests for a full ingestion run <!-- id:e7lsx2z -->
  - Over a synthetic corpus with a stub TriageLoader standing in for data/symptom-triage: both kinds converge before chunking and are chunked, embedded, sharded and inventoried by the same code, which is what makes 12.2 structural rather than a set of kind branches.
  - Pass ordering: the authored load runs after every vendor shard commits, so an authored fix pointer whose target text this run repaired resolves and is not flagged unbacked from the previous run's passages.
  - A rejected source is excluded, its reason reported, and the run still succeeds with the remaining sources queryable.
  - unbacked and entry_location arrive from the loader and reach the emitted Passage unchanged - this spec neither sets, clears nor derives them (12.6).
  - Blocked-by: e7lsx2t (Implement the merge, index/manifest.py and the atomic view commit), e7lsx2w (Implement corpus/rig.py and gaps.json), e7lsx2y (Implement report.py)
  - Stream: 1
  - Requirements: [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.7](requirements.md#1.7), [8.6](requirements.md#8.6), [9.1](requirements.md#9.1), [9.6](requirements.md#9.6), [12.2](requirements.md#12.2), [12.3](requirements.md#12.3), [12.6](requirements.md#12.6), [12.7](requirements.md#12.7)

- [ ] 44. Implement cli.py and the run orchestration <!-- id:e7lsx30 -->
  - `dawmans ingest`, `dawmans validate`, `dawmans inventory`.
  - Run order: delete superseded views, discover both stores, load the embedding model once, ingest vendor sources and commit their shards, then the authored load, then merge, gaps.json, and the manifest rename.
  - Blocked-by: e7lsx2z (Write end-to-end tests for a full ingestion run)
  - Stream: 1
  - Requirements: [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.7](requirements.md#1.7), [8.6](requirements.md#8.6), [9.1](requirements.md#9.1), [9.6](requirements.md#9.6), [12.2](requirements.md#12.2), [12.3](requirements.md#12.3), [12.7](requirements.md#12.7)

- [ ] 45. Add the timing tests and the bench target <!-- id:e7lsx31 -->
  - 8.2 (<5 s extraction) and 8.4 (<10 s for a new <=50-page source) run against synthetic PDFs generated at test time and assert their budgets in CI.
  - 8.4 is measured with the model resident and the cold load asserted separately, rather than hiding a 7.2 s constant inside a 10 s budget. 8.4, not 8.1, is the tightest budget in the spec.
  - 8.1 (full corpus under 60 s) needs the real gitignored PDFs, so it is `make bench`, run locally and skipped when manuals/ is empty; CI cannot verify it.
  - Blocked-by: e7lsx30 (Implement cli.py and the run orchestration)
  - Stream: 1
  - Requirements: [8.1](requirements.md#8.1), [8.2](requirements.md#8.2), [8.4](requirements.md#8.4)
