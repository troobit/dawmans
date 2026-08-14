# Requirements: Manual Corpus

**Domain:** `data` · **Capability:** manual-corpus · **Status:** draft

## Purpose

DAWMans answers home-studio questions strictly from the sources it has ingested. This spec
owns **ingestion only**: turning a folder of manual PDFs — and the studio owner's own authored
troubleshooting source — into a queryable, citable corpus. It is the foundation the rest of the
app stands on — if a fact is not in the corpus with a usable citation, no downstream component
can produce it.

**In scope:** discovering sources of both kinds (§12), extracting manual text faithfully,
selecting the English content, repairing broken glyphs, splitting text into section-aware chunks
that carry citation metadata, building and refreshing the index, reporting what is indexed, and
recording which hardware each document actually applies to against the rig the owner holds.

[`CONTRACTS.md`](../../CONTRACTS.md) is governing. This spec owns the `SourceRecord` (§1 there)
and the `Passage` (§2 there) — every field of both except `unbacked`, which is owned by
[`data/symptom-triage`](../symptom-triage/requirements.md) and carried through unchanged (12.6).
Where the two documents disagree, `CONTRACTS.md` wins.

**Out of scope (owned elsewhere):** retrieval ranking, relevance scoring, and answer synthesis
belong to `api/answer-engine`; question entry, answer display, and source selection belong to
`ui/ask-and-source-picker`. This spec defines *what the index contains and guarantees*, not how
it is searched or rendered.

## Terms

- **Source** — one ingested document. Every source carries a **kind** (§12).
- **Source kind** — `vendor-manual` (a manufacturer's PDF in `manuals/`) or `authored-triage`
  (written by the studio owner), per [`CONTRACTS.md`](../../CONTRACTS.md) §4a. Kind changes what a
  source is trusted for downstream, and which fields of the shared records apply to it (12.5,
  12.8); it does not change how the source is retrieved or cited.
- **Source ID** — the stable identifier for a source: derived from the filename for a
  `vendor-manual`, and the constant `authored/triage` for the authored source, which is a store
  rather than a document and so does not vary with its contents
  ([`CONTRACTS.md`](../../CONTRACTS.md) §1).
- **Chunk** — the smallest indexed unit of text, carrying the metadata needed to cite it. A chunk
  is the `Passage` record of [`CONTRACTS.md`](../../CONTRACTS.md) §2.
- **Passage ID** — the content-derived identifier every chunk carries, stable across
  re-ingestion while the chunk's text is unchanged.
- **Citation metadata** — what a chunk itself carries so a reference such as `Live 12 §24.9 p400`
  can be rendered: source ID, section number, section title, and page number(s) where the source
  has pages. Product, document version and display name are `SourceRecord` fields and resolve
  through the source ID; they are not repeated on the chunk (6.2).
- **Pageless source** — a source that has no pages at all. An `authored-triage` source is
  pageless; its page fields are absent and are never synthesised (12.8).
- **Ingestion run** — a single pass that brings the index up to date with both source stores:
  `manuals/` and the authored entry store (§12).
- **Queryable index** — the state the artefacts written by an ingestion run must be in for another
  process to search them: both kinds of matching available over the same passages, readable without
  any source PDF, restrictable to a chosen subset of sources, and self-describing enough to be
  rejected when incompatible. §8 states this as criteria ([8.8](#8.8)–[8.11](#8.11)); it is what
  "a queryable one" in [8.1](#8.1) means.
- **Rejection** — an expected, per-source outcome: the source is excluded and the reason
  reported, and the run still succeeds. Distinct from a **failure**, which is unexpected and
  fails the run.
- **Rig inventory** — the declared list of hardware the studio owner actually owns, held
  separately from the corpus inventory of what is indexed.
- **Reference corpus** — the manuals present at the time of writing: Ableton Live 12 Reference
  Manual (1009 pages), Akai APC Key 25 User Guide (24 pages, multilingual), Alesis Nitro Max
  User Guide (35 pages). Roughly 1068 pages and 250,000 words in total.

---

## 1. Source Discovery and Registration

**User Story:** As the studio owner, I want to drop a new manual PDF into `manuals/` and have it
become answerable, so that adding gear does not mean editing code or configuration.

**Acceptance Criteria:**

1. <a name="1.1"></a>The system SHALL discover `vendor-manual` sources by scanning the `manuals/`
   directory at the start of every ingestion run, SHALL discover `authored-triage` sources in the
   same run per [12.3](#12.3), and SHALL NOT rely on any hard-coded list of expected sources of
   either kind.
2. <a name="1.2"></a>WHEN a PDF is present in `manuals/` that is not yet in the index, the system
   SHALL ingest it during the next ingestion run without any further user action.
3. <a name="1.3"></a>WHEN a file in `manuals/` is not a PDF, the system SHALL skip it silently and
   SHALL NOT report the run as failed.
4. <a name="1.4"></a>WHEN a source is removed from the store it was discovered in — `manuals/` for
   a `vendor-manual`, the authored entry store ([12.3](#12.3)) for an `authored-triage` source —
   the next ingestion run SHALL remove that source's chunks from the index so that no answer can
   cite a source that is no longer present.
5. <a name="1.5"></a>The system SHALL produce a per-run report listing, for each source, whether
   it was ingested, skipped as unchanged, or rejected, and the reason for any rejection.
6. <a name="1.6"></a>WHEN a source cannot be ingested for an expected reason — a filename that
   does not match the convention (2.5), a source ID collision (2.6), no text layer (3.3), no
   English content (4.5), unreadable text (5.5), or an authored source reported as invalid
   (12.6) — the system SHALL treat it as a
   **rejection**: it SHALL exclude that source from the index, report the reason, continue with
   the remaining sources, and still report the run as succeeded.
7. <a name="1.7"></a>WHEN a source fails to ingest for any other reason, the system SHALL treat
   it as a **failure**: it SHALL continue ingesting the remaining sources and SHALL report the
   run as failed at the end, rather than aborting on the first failure. Sources that ingested
   successfully in that run SHALL remain indexed (8.7).

## 2. Source Identity and Naming Convention

**User Story:** As the studio owner, I want each manual's identity to come from its filename, so
that citations name the right product and version without a separate registry to maintain.

**Acceptance Criteria:**

1. <a name="2.1"></a>The system SHALL require every source filename to match the pattern
   `<vendor>_<product>_<doctype>_v<version>_<lang>.pdf`, with fields separated by underscores and
   every field other than `<version>` lowercase kebab-case.
2. <a name="2.2"></a>The system SHALL accept a `<version>` field consisting of the literal `v`
   followed by one or more groups of digits separated by full stops — `v12`, `v1.0`, `v1.1`,
   `v2.10.3`. This is an explicit exception to kebab-case: vendors number manual revisions with
   full stops, and two of the three sources in the reference corpus do so.
3. <a name="2.3"></a>The system SHALL accept a `<lang>` field that is either an ISO 639-1 language
   code or the literal value `multi`.
4. <a name="2.4"></a>The system SHALL derive the source ID, vendor, product, document type,
   document version, declared language, and human-readable display name of a source from its
   filename, and SHALL keep the source ID stable across ingestion runs for as long as the
   filename is unchanged.
5. <a name="2.5"></a>WHEN a filename in `manuals/` does not match the required pattern, the system
   SHALL reject that source, SHALL report the offending filename together with the expected
   pattern, and SHALL NOT index any of its content.
6. <a name="2.6"></a>WHEN two sources resolve to the same source ID, the system SHALL reject both
   and report the collision, rather than silently indexing one of them.

## 3. Text Extraction Fidelity

**User Story:** As the studio owner, I want the words in the manual to reach the index exactly as
written, so that answers quote real instructions rather than approximations.

**Acceptance Criteria:**

1. <a name="3.1"></a>The system SHALL extract text from a source's embedded text layer and SHALL
   preserve the wording, ordering, and casing of the source text.
2. <a name="3.2"></a>The system SHALL retain the page number on which each extracted passage
   appears, for every page of every source.
3. <a name="3.3"></a>WHEN a source has no embedded text layer at all, the system SHALL reject it
   and report it as having no usable text layer, rather than indexing it as empty.
4. <a name="3.4"></a>WHEN a source has an embedded text layer but yields fewer than 50 words per
   page averaged across the document, the system SHALL ingest it and set the `low_text` flag on
   its `SourceRecord` (CONTRACTS §1), rather than rejecting it. The flag exists to be seen, not
   acted on: it is reported in the inventory ([9.1](#9.1)) and marks the source where sources are
   listed for selection, and nothing in retrieval, ranking or synthesis consumes it. A short,
   heavily pictorial guide is a legitimate source with a perfectly good text layer, and a word
   count is not evidence that extraction failed.
5. <a name="3.5"></a>The system SHALL preserve line and paragraph boundaries sufficiently that a
   numbered or bulleted procedure remains readable as a sequence of discrete steps.
6. <a name="3.6"></a>The system SHALL remove repeated page furniture (running headers, running
   footers, and standalone page numbers) from indexed text, so that it does not appear inside
   quoted answers.

## 4. English Content Selection

**User Story:** As the studio owner, I want only the English pages of a multilingual manual in the
index, so that a search does not return the same fact five times in languages I cannot read.

**Acceptance Criteria:**

1. <a name="4.1"></a>The system SHALL index only English content, regardless of how many languages
   a source contains.
2. <a name="4.2"></a>WHEN a source's declared language is `multi`, the system SHALL determine which
   parts of the document are English by inspecting the extracted content, and SHALL NOT depend on
   page ranges configured per known manual — a newly added multilingual manual SHALL require no
   code or configuration change.
3. <a name="4.3"></a>The system SHALL apply language selection at page granularity or finer, so
   that a page containing both English and non-English content contributes only its English part.
4. <a name="4.4"></a>The system SHALL record, per source, which page ranges were included as
   English and which were excluded, and SHALL additionally list every page that was included only
   in part, so that a sub-page selection made under 4.3 is visible in the audit rather than
   hidden inside a whole-page range. The selection SHALL be auditable without re-reading the PDF.
5. <a name="4.5"></a>WHEN a source yields no English content, the system SHALL reject it and report
   that no English content was found, rather than indexing an empty source.
6. <a name="4.6"></a>The system SHALL include English content that appears outside the main English
   section of a multilingual document, such as an appendix placed after the translations.

## 5. Glyph and Encoding Repair

**User Story:** As the studio owner, I want symbols such as the transport arrows in a controller
manual to survive ingestion, so that a button procedure is not quoted back to me as gibberish.

**Acceptance Criteria:**

1. <a name="5.1"></a>The system SHALL detect extracted spans whose characters are inconsistent with
   the surrounding English text — for example, a run of accented Latin letters standing in for
   symbol glyphs through a font encoding fault.
2. <a name="5.2"></a>WHEN a detected span can be mapped to its intended characters, the system
   SHALL repair it and index the repaired text.
3. <a name="5.3"></a>WHEN a detected span cannot be mapped, the system SHALL index the containing
   chunk with its `degraded` flag set, and SHALL NOT index the unrepaired characters as if they
   were ordinary words. `degraded` is a field of the `Passage` record (CONTRACTS §2) and is
   contractually required to reach the citation, where the expanded passage is marked as
   containing unreadable characters (CONTRACTS §3) — it is not an optional hint downstream may
   discard.
4. <a name="5.4"></a>The system SHALL report, per source, the number of spans repaired and the
   number flagged as degraded.
5. <a name="5.5"></a>WHEN more than 2% of a source's extracted characters are unmappable, the
   system SHALL reject the source and report it as unreadable, rather than indexing a document
   that is mostly noise.

## 6. Section-Aware Chunking and Citation Metadata

**User Story:** As the studio owner, I want every answer to point at a section and page I can open
in the actual manual, so that I can verify it in seconds.

**Acceptance Criteria:**

1. <a name="6.1"></a>The system SHALL attach to every chunk a passage ID derived from the chunk's
   own content, such that re-ingesting a source yields the same passage ID for every chunk whose
   text is unchanged. Because re-ingestion replaces all of a source's previous chunks (9.4) and
   the UI retains prior exchanges across restarts, a citation held in that history SHALL still
   resolve to its passage text after the source is re-ingested.
2. <a name="6.2"></a>The system SHALL attach to every chunk: its passage ID, source ID, the title
   of the section the chunk's text belongs to, and — WHERE the source has pages — the page number
   or page range of its text. Product name and document version are `SourceRecord` fields
   (CONTRACTS §1) that resolve through the source ID, and SHALL NOT be duplicated onto the chunk.
3. <a name="6.3"></a>WHEN a source uses numbered sections, the system SHALL additionally attach the
   section number to every chunk derived from that section, such that a citation of the form
   `<product> §<section> p<page>` can be rendered without further lookup.
4. <a name="6.4"></a>WHEN a source has no section numbering, the system SHALL still attach a
   section title — and a page number WHERE the source has pages — and SHALL render the citation
   without a section number rather than inventing one.
5. <a name="6.5"></a>WHEN a page belongs to no section — a title page, table of contents,
   copyright notice, or other front or back matter — the system SHALL treat each contiguous run
   of such pages as a titled region, named either by its own printed title or as front or back
   matter, so that every chunk carries a section title (6.2) without borrowing the title of an
   adjacent section.
6. <a name="6.6"></a>The system SHALL derive section structure from the document itself — its table
   of contents, headings, or both — and SHALL NOT require per-manual structure to be supplied by
   hand.
7. <a name="6.7"></a>A chunk SHALL contain text from exactly one section or one titled region;
   the system SHALL NOT produce a chunk whose text spans two of them.
8. <a name="6.8"></a>WHEN a section is longer than the maximum chunk size, the system SHALL split
   it into consecutive chunks that each carry that same section's identity and, WHERE the source
   has pages, the page range of their own text.
9. <a name="6.9"></a>The system SHALL produce chunks of at most 350 words. This bound is derived
   from the retrieval window, not from readability alone: 500 words measures at roughly 600
   tokens against a 512-token embedding window, so the tail of every maximal chunk would be
   silently invisible to retrieval while still appearing in the text shown to the user
   (CONTRACTS §8).
10. <a name="6.10"></a>The system SHALL NOT split a numbered procedure across chunks when the whole
    procedure fits within the maximum chunk size.
11. <a name="6.11"></a>WHERE a source has pages, the system SHALL verify that every chunk's
    recorded page number falls within the source's actual page range, and SHALL reject the source
    if it does not. A pageless source records no page ([12.8](#12.8)) and SHALL NOT be rejected,
    flagged or delayed by this check.

## 7. Table and Multi-Column Preservation

**User Story:** As the studio owner, I want to ask which MIDI note a given drum pad sends and get
the right number, so that mapping a kit does not require me to open the PDF anyway.

**Acceptance Criteria:**

1. <a name="7.1"></a>The system SHALL preserve row integrity in tabular content: every cell SHALL
   remain associated with the row it appears in, and no value SHALL be attributed to a different
   row than the source shows.
2. <a name="7.2"></a>The system SHALL preserve the reading order of multi-column *prose*, such
   that a sentence from one column is not interleaved with a sentence from another. WHERE a
   page's columns are side-by-side panels of tabular content rather than running prose, row
   integrity (7.1) SHALL take precedence: the system SHALL keep each printed row intact with its
   cells in their printed left-to-right order, and SHALL NOT reorder the page into per-panel
   runs, because de-interleaving the panels destroys the pairings the printed row carries.
3. <a name="7.3"></a>The system SHALL keep a table's column headings with its rows in the indexed
   text, so that a row's values remain interpretable in isolation. WHERE a heading is printed
   across more than one physical line, the system SHALL join those lines into one heading before
   associating it with the rows, and SHALL NOT treat a heading line as a data row or discard the
   lines it cannot align.
4. <a name="7.4"></a>The system SHALL NOT split a table row across two chunks when that row fits
   within the maximum chunk size. WHEN a single row is itself longer than the maximum chunk size,
   the system SHALL split it and SHALL mark each resulting chunk as carrying part of one row,
   rather than leaving the row unindexed.
5. <a name="7.5"></a>WHEN a table is larger than the maximum chunk size, the system SHALL split it
   between rows and SHALL repeat the column headings in each resulting chunk.
6. <a name="7.6"></a>The system SHALL index the Alesis Nitro Max MIDI note table (§5.2, p25) such
   that all 19 trigger-to-note pairs are recoverable from the indexed text, each trigger paired
   with the number printed beside it. That page is a required acceptance fixture for this
   section: it is printed as two side-by-side panels of unequal length — 11 rows on the left,
   8 on the right — under a heading that wraps across three physical lines. Because the panels
   are ragged, a cell SHALL be paired with its trigger by horizontal position rather than by row
   index; pairing by index would silently mis-associate every row past the eighth. This is
   precisely the layout 7.2 and 7.3 must survive.

## 8. Index Build, Queryability and Incremental Update

**User Story:** As the studio owner, I want rebuilding the corpus to be a matter of seconds, so
that adding a manual or fixing an ingestion bug never becomes a chore I avoid — and I want what a
rebuild leaves behind to be searchable by the answering side without it opening a single PDF.

**Acceptance Criteria:**

1. <a name="8.1"></a>The system SHALL complete a full rebuild of the reference corpus (~1068 pages,
   ~250,000 words) in under 60 seconds on the target machine, measured from an empty index to a
   queryable one ([8.8](#8.8)–[8.11](#8.11)).
2. <a name="8.2"></a>The system SHALL complete the text-extraction stage of a full rebuild in under
   5 seconds for the reference corpus.
3. <a name="8.3"></a>WHEN a single new source of either kind appears in its store — `manuals/` or
   the authored entry store ([12.3](#12.3)) — the system SHALL ingest only that source and SHALL
   NOT re-extract, re-chunk, or re-index any unchanged source of either kind.
4. <a name="8.4"></a>The system SHALL complete the ingestion of one newly added `vendor-manual`
   source of 50 pages or fewer in under 10 seconds. The corresponding budget for the authored
   source is owned by [`data/symptom-triage`](../symptom-triage/requirements.md) (its 5.6) and is
   not restated here.
5. <a name="8.5"></a>The system SHALL perform ingestion entirely offline, requiring no network
   access.
6. <a name="8.6"></a>The system SHALL be able to rebuild the entire index from the contents of the
   two source stores — `manuals/` and the authored entry store ([12.3](#12.3)) — with no other
   input.
7. <a name="8.7"></a>WHEN a source fails partway through ingestion (1.7), the index SHALL retain
   none of that source's chunks from the failed attempt and SHALL retain its previously indexed
   chunks unchanged, so that no source is ever left partly rebuilt. Rollback SHALL be scoped to
   the failing source: sources that ingested successfully in the same run SHALL commit and remain
   queryable.
8. <a name="8.8"></a>The system SHALL make both **exact-term matching** — a passage containing a
   query term literally, including model names, version strings, hyphenated and slashed tokens and
   bare numerals — and **meaning-based matching** — a passage whose wording differs from the query
   — available over the same set of passages produced by the run. Neither kind alone satisfies this
   criterion.
9. <a name="8.9"></a>The system SHALL make every field of `Passage` (CONTRACTS §2) and of
   `SourceRecord` (CONTRACTS §1) readable from the artefacts an ingestion run writes, with no
   access to any source PDF, so that a citation can be rendered and its applicability judged
   without opening the document it came from.
10. <a name="8.10"></a>The system SHALL allow matching to be restricted to any chosen subset of the
    indexed sources, without reading the passages of the sources left out. This is what per-source
    scoping in the answering side rests on.
11. <a name="8.11"></a>The artefacts SHALL be self-describing: they SHALL declare the identity of
    the process that produced them, such that a consumer expecting a different one refuses to
    interpret them rather than misreading them, and SHALL carry a corpus revision identifier that
    changes when and only when the indexed content changes, so that a consumer can detect the
    change with a single cheap read rather than by diffing the corpus.

> **Basis for the targets.** A full layout-preserving text extraction of the 1009-page Live 12
> manual — the largest source by an order of magnitude — measured at 0.7 seconds and yielded
> 1.5 MB of text. Extraction is therefore not the bottleneck, and 8.2 allows roughly seven times that
> measured cost as headroom. The 60-second budget in 8.1 leaves the remaining time for language
> selection, chunking, and index construction over a corpus of only ~330,000 tokens. A corpus this
> small does not justify a slow build; if a rebuild takes minutes, something is wrong.

## 9. Corpus Inventory and Staleness

**User Story:** As the studio owner, I want to see exactly which manuals and versions are
answerable right now, so that I know whether a wrong answer is a bug or a missing manual.

**Acceptance Criteria:**

1. <a name="9.1"></a>The system SHALL report, for each indexed source, every field of the
   `SourceRecord` table in CONTRACTS §1 — that table, not a copy of it held here — reporting a
   field that table marks as not applicable to the source's kind as not applicable rather than
   inventing a value for it, and SHALL NOT add fields to that record. The English page-range audit
   of [4.4](#4.4) SHALL be reported alongside the inventory for `vendor-manual` sources, as an
   ingestion report rather than as a field of the record.
2. <a name="9.2"></a>The system SHALL record a content fingerprint for each ingested source.
3. <a name="9.3"></a>WHEN a source's file content has changed since its last ingestion, the system
   SHALL detect the change on the next ingestion run and SHALL re-ingest that source.
4. <a name="9.4"></a>WHEN a source is re-ingested, the system SHALL replace all of its previous
   chunks, leaving no chunk from the superseded version in the index, while preserving the
   passage ID of every chunk whose text is unchanged (6.1).
5. <a name="9.5"></a>The system SHALL report any `vendor-manual` source that is present in
   `manuals/` but absent from the index, and any `vendor-manual` source present in the index but
   absent from `manuals/`. It SHALL apply the equivalent check to `authored-triage` sources
   against the authored entry store ([12.3](#12.3)), and SHALL NOT test a source of one kind
   against the other kind's store — an authored source is not an anomaly for being absent from
   `manuals/`.
6. <a name="9.6"></a>The system SHALL make the inventory available to `api/answer-engine` and
   `ui/ask-and-source-picker` so that a user can be told which manuals an answer could have come
   from.

## 10. Figures and Screenshots

**User Story:** As the studio owner, I want a fast text-only corpus for the first release, so that
the app ships and answers questions instead of stalling on image handling.

**Acceptance Criteria:**

1. <a name="10.1"></a>The system SHALL build a text-only index; image content SHALL NOT be
   extracted, described, or indexed.
2. <a name="10.2"></a>The system SHALL index figure captions and callout labels as ordinary text
   when they are present in the embedded text layer.
3. <a name="10.3"></a>WHEN a chunk's section contains one or more figures, the system SHALL set the
   chunk's `has_figures` flag together with the page number of the figure. `has_figures` is a
   field of the `Passage` record (CONTRACTS §2) and is contractually required to reach the
   citation, where it is rendered as "figure on p*N*" (CONTRACTS §3) — in a text-only index it is
   the only pointer the user gets to content the corpus cannot hold.
4. <a name="10.4"></a>The system SHALL NOT reject or degrade a source on account of its images; the
   96 MB of screenshots in the Live 12 manual SHALL have no effect other than file size.

## 11. Hardware Applicability and the Rig Inventory

**User Story:** As the studio owner, I want to be told when a manual describes a different
revision of my hardware, or when I own a device with no manual at all, so that a confident
citation never sends me looking for a control my unit does not have.

**Acceptance Criteria:**

1. <a name="11.1"></a>The system SHALL hold, for every source, a declared `hardware_applicability`
   (CONTRACTS §1) stating which hardware revision the document describes and whether that is
   `confirmed` or `assumed`.
2. <a name="11.2"></a>WHEN a source's applicability is not declared, the system SHALL record it as
   `assumed` for the product named in its filename, and SHALL NOT record any applicability as
   `confirmed` by default — an undeclared source is unverified, not verified.
3. <a name="11.3"></a>The system SHALL hold a declared **rig inventory** of the hardware the studio
   owner owns, separately from the corpus inventory of §9, and SHALL NOT derive it from the
   contents of `manuals/` — what is documented is not evidence of what is owned.
4. <a name="11.4"></a>The system SHALL report every **owned-but-undocumented** device: an item in
   the rig inventory for which no source is indexed. Today that is the Focusrite Scarlett Solo.
5. <a name="11.5"></a>The system SHALL report every **documented-but-unconfirmed** source: an
   indexed source whose applicability is `assumed` for a device in the rig inventory, or whose
   declared revision differs from the revision owned. Today that is the Akai APC Key 25 guide,
   Manual Version 1.0, which describes the original unit while the rig holds an mk2 with
   different pads and a different shift layer.
6. <a name="11.6"></a>The system SHALL publish each source's `hardware_applicability` and both gap
   reports to `api/answer-engine` and `ui/ask-and-source-picker` alongside the corpus inventory,
   so that a citation drawn from an unconfirmed source can be marked inline (CONTRACTS §3).

## 12. Source Kinds

**User Story:** As the studio owner, I want my own written troubleshooting notes indexed and cited
by exactly the same machinery as a vendor PDF, so that the knowledge the manuals do not hold is
answerable without a second pipeline and without pretending the manufacturer said it.

**Acceptance Criteria:**

1. <a name="12.1"></a>The system SHALL record the `kind` field of the `SourceRecord` table
   (CONTRACTS §1) on every source, being either `vendor-manual` or `authored-triage`
   (CONTRACTS §4a), and SHALL NOT index a source whose kind is undeclared.
2. <a name="12.2"></a>The system SHALL apply source discovery and registration (§1), section-aware
   chunking and citation metadata (§6), index build and incremental update (§8), and the corpus
   inventory and staleness rules (§9) to sources of **both** kinds, so that an authored source is
   retrieved, cited and inventoried through the same `SourceRecord` and `Passage` records as a
   manual — subject only to the kind-dependent fields of CONTRACTS §1 and the pageless rule in
   [12.8](#12.8).
3. <a name="12.3"></a>The system SHALL discover `authored-triage` sources at the location, and in
   the form, that [`data/symptom-triage`](../symptom-triage/requirements.md) defines, rather than
   from `manuals/`. The skip rule in [1.3](#1.3) governs unexpected files in `manuals/` only and
   SHALL NOT cause an authored source to be skipped.
4. <a name="12.4"></a>The PDF-specific requirements of this spec — text extraction fidelity (§3),
   English content selection (§4), glyph and encoding repair (§5), table and multi-column
   preservation (§7), and figures and screenshots (§10) — SHALL apply to `vendor-manual` sources
   only, and SHALL NOT be applied to, or cause the rejection of, an `authored-triage` source,
   which has no PDF to extract from.
5. <a name="12.5"></a>The filename convention in [2.1](#2.1)–[2.3](#2.3), and the derivation of
   identity from a filename in [2.4](#2.4), SHALL apply to `vendor-manual` sources only. An
   `authored-triage` source SHALL carry the identity fields CONTRACTS §1 marks as applying to its
   kind — the constant source ID `authored/triage`, a display name, and a hardware applicability
   of `assumed` — so that its citations render by the same rules as any other source. The source ID
   SHALL NOT be derived from the source's contents: it prefixes every passage ID, so an identifier
   that moved whenever an entry was edited would orphan every retained citation. The fields that table marks as not applicable to it — vendor, product,
   document type, declared language, document version and page count — SHALL NOT be synthesised
   to satisfy a rule written for a PDF.
6. <a name="12.6"></a>The content, structure and validation of an `authored-triage` source are
   owned by [`data/symptom-triage`](../symptom-triage/requirements.md). This spec SHALL ingest
   whatever that spec declares valid, SHALL NOT restate or duplicate its rules, and SHALL treat a
   source that spec reports as invalid as a **rejection** ([1.6](#1.6)) rather than a failure. The
   `unbacked` flag of CONTRACTS §2 is owned by that spec; this spec SHALL carry it on the emitted
   `Passage` unchanged and SHALL NOT set, clear or derive it.
7. <a name="12.7"></a>The system SHALL publish each source's `kind` to `api/answer-engine` and
   `ui/ask-and-source-picker` alongside the corpus inventory ([9.6](#9.6)), because kind
   determines what a source is trusted for (CONTRACTS §4a) and CONTRACTS §3 requires it to be
   shown inline on every citation drawn from that source.
8. <a name="12.8"></a>WHERE a source is **pageless** — as an `authored-triage` source is — the
   system SHALL record no page number, page range or page count for it, SHALL NOT synthesise any
   (CONTRACTS §2), and SHALL NOT reject, flag or exclude the source for lacking them. The
   page-bearing clauses of this spec — [6.2](#6.2), [6.4](#6.4), [6.8](#6.8) and [6.11](#6.11) —
   apply only to sources that have pages.

---

## Non-Goals

- **Retrieval and ranking.** Choosing which chunks answer a question is `api/answer-engine`.
- **Answer synthesis and citation rendering.** This spec guarantees the metadata exists; composing
  prose and formatting the reference string is `api/answer-engine` and
  `ui/ask-and-source-picker`.
- **OCR.** Every source in the reference corpus has a clean embedded text layer. A source with no
  text layer at all is rejected (3.3), not recovered; a sparse one is ingested and flagged (3.4).
- **Detecting applicability from content.** §11 records a *declared* hardware applicability.
  Ingestion does not infer the revision a document describes by reading it; an undeclared source
  is `assumed`, never `confirmed`.
- **Image understanding.** No figure extraction, diagram parsing, or screenshot description
  (§10). If a manual conveys a fact only in a picture, DAWMans will not know it.
- **Non-English answers.** Translated content is deliberately discarded (§4).
- **Automatic manual acquisition.** The system does not download, discover, or update manuals from
  vendor websites; files arrive in `manuals/` by hand.
- **Vendor formats other than PDF.** HTML, EPUB, and video manuals are out of scope for now, though
  the naming convention leaves room for them. This exclusion is about *vendor* documents; it does
  not exclude the `authored-triage` source, which is not a vendor document at all (§12).
- **Authoring, structuring, or validating the triage source.** `data/symptom-triage` owns what an
  authored source contains and what makes it valid; this spec only ingests it (12.6).
- **Redistribution.** The corpus is built and used locally; nothing exposes the manual PDFs for
  download.

## Assumptions and Risks

- **Risk — the APC Key 25 manual is the wrong revision.** The ingested guide
  (`akai_apc-key-25_user-guide_v1.0_multi.pdf`) contains no mk2 markers, while the rig has an
  APC Key 25 mk2 with different pads and a different shift layer. This is no longer left to
  citation metadata: §11 makes it a criterion. The source is declared `assumed` (11.2) and
  reported as documented-but-unconfirmed (11.5), and the applicability reaches the citation
  (11.6). What remains a risk is the *declaration* being wrong — ingestion still cannot read a
  document and work out which revision it describes, so a mis-declared source will be reported
  as confidently as a correct one. Obtaining the mk2 guide remains a corpus gap.
- **Risk — glyph faults are silent.** The APC manual's arrow symbols extract as `(ð, ñ, ô, õ)`.
  Similar faults in future manuals may not be detectable by the heuristics in §5, and a degraded
  passage that reads as plausible English will not be flagged. The per-source counts in 5.4 are
  the main guard.
- **Risk — table extraction is layout-dependent.** The Nitro Max MIDI note table survives a
  layout-preserving extraction but is mangled by a naive one; 7.6 pins that page as an acceptance
  fixture so the regression is caught. A future manual with a more complex table (merged cells,
  nested headings) may still not satisfy §7, and that failure is likely to be quiet.
- **Assumption — manuals stay third-party and out of the repository.** `manuals/` is gitignored:
  the PDFs are copyrighted vendor documents, kept locally for personal reference and never
  committed or redistributed. Every environment therefore builds its own index from its own copy
  of the PDFs, together with the authored entry store, which — being the owner's own writing —
  does travel with the repository ([8.6](#8.6) rebuilds from both). Keeping ingestion output out
  of version control constrains the developer, not the system, so it is not an acceptance
  criterion — see `DECISIONS.md` Decision 3.
- **Assumption — the corpus stays small.** The targets in §8 assume a corpus in the low thousands
  of pages. Growth by an order of magnitude would invalidate the "rebuild everything, it's cheap"
  position and require revisiting incremental behaviour.
- **Assumption — section structure is machine-readable.** Both large manuals carry numbered tables
  of contents with page numbers, which is what makes §6 citations precise. A manual without
  headings or numbering would fall back to 6.4 and produce weaker citations.
- **Assumption — the authored triage source is maintained by hand.** §12 ingests it; nothing
  generates it, and nothing checks that its entries still match the manuals they point at. A
  stale entry is indexed and cited as confidently as a current one, and detecting that is
  `data/symptom-triage`'s problem, not ingestion's.
- **Assumption — the rig inventory is maintained by hand.** §11 compares what is indexed against a
  declared list of owned hardware. Nothing detects connected devices, so a device bought and not
  declared will not be reported as owned-but-undocumented.
- **Assumption — the reference machine is the user's macOS studio machine.** The timings in §8 are
  measured there, not on CI or a server.
