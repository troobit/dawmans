# Decision Log: Manual Corpus

Enhanced Nygard ADR entries for the load-bearing choices in
[`design.md`](design.md). Measured figures come from the benchmarks in
[`docs/agent-notes/retrieval-approach.md`](../../../docs/agent-notes/retrieval-approach.md),
taken on the reference machine (Apple M5 Pro, 64 GB, macOS 15.6) on 2026-08-14.

---

## Decision 1: No vector database

**Date**: 2026-08-14
**Status**: accepted

### Context

The index must be queryable by a separate process (`api/answer-engine`) within a 50 ms retrieval
budget (CONTRACTS §7), and rebuildable from the source stores alone in under 60 seconds
(requirement 8.1, 8.6). The obvious reach is for a vector store — sqlite-vec, LanceDB, Chroma,
Qdrant — because that is what the surrounding literature assumes.

The corpus is far smaller than that assumption. ~250,000 words at a 350-word cap gives roughly
800–1,200 chunks. At 384 dimensions in float32 the entire vector index is **1.8 MB**.

### Decision

Hold the dense index as a single `vectors.npy` array (float32, L2-normalised) and search it by
brute-force matrix–vector product with NumPy. No vector database, no approximate-nearest-neighbour
index.

### Rationale

Measured on the reference machine, a full cosine scan plus top-10 selection over 2,000 × 384
vectors takes **0.011 ms**. The query encode that must precede it takes **2.2 ms** — 200 times
longer. Search is not merely fast enough; it is invisible next to the step that feeds it. Even at
50,000 chunks, a 50× growth beyond the assumption in the requirements, the scan is 0.68 ms.

ANN indexing exists to trade recall away to avoid an expensive exhaustive scan. Here the exhaustive
scan is exact and costs nothing, so approximating it would sacrifice correctness to improve a
quantity already below measurement noise.

### Alternatives Considered

- **sqlite-vec**: Also exact brute force by default, and genuinely the right answer if metadata
  filtering in SQL were needed - Rejected because it adds a loadable extension and a schema for no
  measurable gain; source scoping is already a row-range slice via the manifest.
- **LanceDB**: Columnar on-disk format with ANN indexing and versioning - Rejected because all of
  that is machinery for datasets that do not fit in memory. This one is 1.8 MB.
- **Qdrant**: Network service with HNSW indexing - Rejected because the network hop alone costs two
  orders of magnitude more than the entire search it replaces.
- **SQLite FTS5 for the lexical half**: Built in, implements BM25 natively - Rejected narrowly in
  favour of `bm25s`, which keeps the whole index as plain files rebuilt in one pass (8.6) and avoids
  tokeniser and stemmer configuration in SQL. This was a close call, not a strong preference.

### Consequences

**Positive:**
- Zero dependencies beyond NumPy for the search path; the index is one `.npy` file that is trivially
  rebuildable and trivially inspectable.
- 8.6 falls out for free — there is no database state that can drift from the source stores.
- Source-scoped retrieval is a contiguous row slice, because the merge writes shards in manifest
  order.

**Negative:**
- Growth by an order of magnitude past the assumption in the requirements would need revisiting,
  though the measured 50,000-chunk figure suggests the ceiling is far away.
- Metadata filtering must be implemented in Python rather than delegated to a query engine.

---

## Decision 2: Hybrid BM25 and dense retrieval, fused with RRF

**Date**: 2026-08-14
**Status**: accepted

### Context

The index this spec builds is consumed by `api/answer-engine`, so the artefacts written here decide
what retrieval strategies are available to it. Building only `vectors.npy` forecloses lexical
retrieval; building both leaves the choice open.

The questions this corpus answers are dense with exact strings that a user reads off a screen or a
piece of hardware and types verbatim: device names ("Glue Compressor", "Utility"), parameter names
("Threshold", "Dry/Wet", "Makeup"), control names ("Scene Launch", "Rec Arm"), and numbers
("MIDI note 38", "CC 74", "channel 10").

### Decision

Build **both** a dense index and a `bm25s` lexical index over the same passage ordering, and specify
Reciprocal Rank Fusion with k=60 as the fusion method. Prefix every chunk with its citation header
before both embedding and lexical indexing.

### Rationale

Dense retrieval fails on precisely the queries a user most expects to work. "Utility" is a common
English word that is also a specific Live device, and a dense model embeds it near "usefulness" and
"tool". "Threshold" appears in dozens of devices with near-identical embeddings. Bare numerals are
the worst case: 38 and 39 embed almost identically while the correct answer differs completely — and
for the Nitro Max MIDI note table that is not a marginal case, it is the primary use case.

BM25 conversely cannot handle "how do I make a sound quieter over time" → *fade / volume
automation*. Neither method is sufficient alone.

The cost is negligible: `bm25s` measures **0.047 ms per query** and **0.14 s to index 4,000 chunks**.
Anthropic's published measurements put adding BM25 to a dense retriever at a 2.9% failure rate
against 3.7% dense-only, and 5.7% for embeddings without context — on a general corpus. On one this
identifier-dense the benefit should be larger.

RRF is chosen over weighted score blending because BM25 scores are unbounded and corpus-dependent
while cosine similarities cluster in a narrow band; blending requires normalisation whose parameters
drift every time a manual is dropped into `manuals/`. RRF consumes only ranks and is immune to that.

### Alternatives Considered

- **Dense-only**: One index, one code path, no tokenisation questions - Rejected because it fails on
  exact identifiers, which is the majority of real queries here, and the failures are silent.
- **BM25-only**: No embedding model, no 21-second build stage, no 67 MB download - Rejected because
  it cannot answer a symptom described in the user's own words, which is the whole reason
  `authored-triage` entries exist.
- **Weighted score blending instead of RRF**: Preserves score magnitude, so a runaway-best lexical
  match outranks a merely-good one - Rejected because it needs normalisation parameters that drift
  as the corpus changes, and the loss of magnitude does not matter when the fused candidates are fed
  to a model that does its own selection.

### Consequences

**Positive:**
- Exact strings and paraphrases both retrieve, without a tuning parameter to maintain.
- The citation header puts the exact product and section strings into the lexical index, where
  verbatim queries land — most of the benefit of contextual retrieval at no model cost.
- RRF degrades gracefully: a chunk found by one retriever still scores.

**Negative:**
- Two indexes to build, commit and keep in step with the same passage ordering; a bug that
  desynchronises them mis-cites silently.
- The lexical tokeniser must not destroy "Dry/Wet", hyphenated identifiers or bare numerals, and
  that failure is quiet. It needs an explicit test.

---

## Decision 3: 350-word chunk cap, derived from the embedding window

**Date**: 2026-08-14
**Status**: accepted

### Context

A chunk cap has to be chosen. The intuitive basis is readability — short enough that a person can
check the quoted text against the printed page — which suggests something around 500 words. The
draft requirements originally said 500.

The dense index is built with `bge-small-en-v1.5`, whose input window is **512 tokens**.

### Decision

Cap chunks at **350 words**, and record in the requirements (6.9) that the bound comes from the
retrieval window rather than from readability.

### Rationale

A 500-word chunk of manual prose measures **601 tokens** with the BGE tokeniser. Overflow is not an
error — it is a **silent truncation**. The last ~90 words of every maximal chunk would never reach
the embedding while still appearing in the lexical index and in the text shown to the user. A
passage would be cited, displayed in full, and partly invisible to the retriever that was supposed
to find it, with nothing anywhere reporting the loss.

350 words is ~420 tokens, leaving ~90 tokens of headroom for the citation header and tokeniser
variance. It also embeds 31% faster (42.4 against 32.3 chunks/s measured), pulling the embedding
stage from 28 s to 21 s inside the 60 s budget of 8.1. Readability is better served at 350 words
than at 500 anyway, so nothing is traded away.

### Alternatives Considered

- **Keep 500 words and accept truncation**: No change to the chunker - Rejected because the failure
  is silent and unbounded: nothing surfaces which chunks lost their tail or what was in it.
- **Keep 500 words and use a longer-context model** (`nomic-embed-text-v1.5`, 8,192 tokens): Removes
  the constraint entirely - Rejected on measured build cost: 10.6 chunks/s against 42.4, an 85 s
  embedding stage that breaches 8.1 on that stage alone, to buy context the chunker would not use.
- **Cap by tokens rather than words**: Exact against the real constraint - Rejected because it makes
  the cap depend on the embedding model, so changing the model silently rewrites every chunk
  boundary and therefore every `passage_id`. A word cap with headroom is stable across model choice.

### Consequences

**Positive:**
- No chunk is ever partly invisible to dense retrieval.
- Faster embedding stage and smaller prompts downstream; time to first token scales linearly with
  prompt length, so the cap is also the highest-leverage latency decision available here.

**Negative:**
- More chunks for the same corpus, so more overlap duplication and more near-duplicate hits in a
  result list.
- A long procedure or table is more likely to exceed the cap and be split, making the
  split-with-repeated-heading paths (7.4, 7.5) load-bearing rather than rare.
- The cap is a word count with headroom rather than an exact token bound, so an unusually
  token-dense chunk could still approach the window. The headroom is ~90 tokens.

---

## Decision 4: TOC-driven sectioning with heading anchoring

**Date**: 2026-08-14
**Status**: accepted

### Context

Every citation must name a section and a page a user can open (6.2–6.6). Section structure has to
come from the document itself; no per-manual structure may be supplied by hand (6.6).

Two structures are available in a PDF: the embedded outline or a printed contents page, which give
titles, numbers and target pages; and in-body heading text, which gives position. The reference
corpus splits three ways — Live 12 has an embedded outline of 816 entries across 41 chapters,
Nitro Max prints a numbered contents page with dot leaders, and the APC guide has neither.

Live averages **1.2 outline entries per page**, so several sections routinely begin on the same
page.

### Decision

Derive sections from the table of contents — embedded outline, else a printed contents page, else
heading-style detection — and then **anchor each entry to the in-body line that matches its title**,
searching the target page and then ±1. Text between consecutive anchors belongs to the earlier
section. Fall back to a page-boundary anchor only when the title cannot be matched, and record that
fallback in the report.

### Rationale

The TOC and the headings each supply half of what a citation needs and neither supplies both. The
TOC gives authoritative titles, numbers and ordering, but its page number is too coarse: with 1.2
entries per page, page-granular attribution would place several sections' text under one heading and
cite the wrong section — the exact failure the citation exists to prevent. In-body headings give
exact position but no reliable numbering or hierarchy, since heading style is a visual convention
that varies per document.

Anchoring uses both and degrades in a visible way: a failed anchor produces a page-granular section
plus a report line, rather than a confidently wrong citation. Live's in-body headings are printed
with their numbers (`24.1 An Overview of Racks`), so the match succeeds on the first attempt for the
overwhelming majority of the 816 entries.

The ordered fallback chain also means the APC guide, which has no machine-readable structure at all,
still produces titled unnumbered sections under 6.4 rather than becoming one undifferentiated
document.

### Alternatives Considered

- **Heading detection only** (font size and weight clustering, no TOC): Works on any document,
  including one with no outline - Rejected because it cannot recover section *numbers*, which 6.3
  requires for a `§24.9`-shaped citation, and heading hierarchy inferred from font size is
  unreliable in a 1009-page document with many styles. Retained as the last fallback, not the
  primary path.
- **TOC page numbers only, no anchoring**: Simple, and correct for documents with one section per
  page - Rejected because Live averages 1.2 entries per page, so it mis-attributes routinely and
  silently.
- **Semantic or model-driven segmentation**: Works on documents with no structure at all - Rejected
  because ingestion is offline and requires no network (8.5), it produces titles that are not the
  document's own, and it cannot produce a section number that matches what the user sees on the page.

### Consequences

**Positive:**
- Citations name the document's own section number and title, so a user can verify against the
  printed page in seconds.
- Sectioning quality is measurable: the count of page-only anchors is a per-source report line.
- Three documents with three different structures work through one mechanism and no configuration.

**Negative:**
- Anchoring is text matching and can fail when an in-body heading is worded differently from its
  TOC entry, or is split by a line break; those cases silently degrade to page granularity, visible
  only in the report.
- Three code paths for structure extraction, each needing its own fixtures.
- A document with neither TOC nor heading styles collapses to a single region and produces weak
  citations, as 6.4 anticipates.

---

## Decision 5: `passage_id` from body text and source ID only

**Date**: 2026-08-14
**Status**: accepted

### Context

6.1 requires a content-derived passage ID stable across re-ingestion, because the UI retains prior
exchanges across restarts and a citation held in that history must still resolve. `data/symptom-triage`
raises the bar further: a fix pointer identifies its target by source ID and passage identity (its
8.1), must survive re-ingestion of unchanged text (8.2), and must survive replacement of a manual by
a **different document version** of the same product (8.3).

Live 12 point releases renumber sections and move page numbers. Any identity that includes a section
number or a page therefore breaks on a routine manual update, silently converting every authored
entry's fix pointer into a flagged, `unbacked` citation.

### Decision

```
passage_id = f"{source_id}#{sha256(canon(text)).hexdigest()[:16]}"
canon(text) = NFC(text), all whitespace runs collapsed to one space, stripped
```

Nothing else enters the digest — not the citation header, section number, section title, page
numbers, document version, file fingerprint, chunk index or ingest timestamp. Where k > 1 chunks
within one source produce the same digest, each is suffixed `.1 … .k` in document order.

### Rationale

Each exclusion answers a specific way the ID could otherwise break:

| Excluded | Would break on |
|---|---|
| section number, section title | a point release renumbering sections (triage 8.3) |
| page numbers | a reflowed or repaginated revision (triage 8.3) |
| document version, fingerprint, timestamp | any re-ingestion at all (6.1) |
| chunk index | insertion of an earlier chunk renumbering everything after it |

Whitespace collapsing and NFC normalisation absorb the difference between two extractions that
differ only in line wrapping or Unicode composition — a difference that carries no meaning but would
otherwise orphan every citation in the retained history at once. Case is **not** folded: 3.1
preserves casing and two chunks differing only in case are genuinely different text.

`source_id` is carried as a visible prefix rather than hashed, which makes cross-source collisions
impossible by construction and lets `fetch-passage` route on the prefix. It is also why the version
sits outside `source_id`: `ableton/live-12` survives a v12 → v12.1 replacement.

Truncation to 16 hex characters gives 64 bits; at ~1,200 chunks the accidental collision probability
is ~4 × 10⁻¹⁴, and the duplicate-suffix rule handles real duplicates deterministically regardless.

### Alternatives Considered

- **Hash the full citation context** (source, section number, title, page, text): Distinguishes
  duplicate boilerplate naturally, with no ordinal suffix rule - Rejected because it breaks every
  pointer whenever sections are renumbered or pages shift, which is exactly the routine event
  triage 8.3 requires the ID to survive.
- **Sequential IDs assigned at ingestion** (`live-12:0001`): Short, unique, trivial to generate -
  Rejected because they are not content-derived: re-ingesting after inserting one chunk renumbers
  everything below it, orphaning retained history wholesale. 6.1 forbids this directly.
- **Hash the text with no normalisation at all**: Simplest possible rule, maximally sensitive -
  Rejected because a re-extraction differing only in line wrapping — a plausible consequence of a
  library upgrade — would change every ID in the corpus at once.
- **Longer digest (full 64 hex characters)**: Removes any collision concern - Rejected as noise in
  logs, URLs and citations; 64 bits is already six orders of magnitude past what this corpus needs.

### Consequences

**Positive:**
- A manual can be re-ingested, updated to a new document version, or re-extracted by a newer library
  without invalidating retained citations or authored fix pointers.
- The ID is verifiable: given a passage's text and its source ID, anyone can recompute it.
- Duplicate detection within a source falls out of the digest for free.

**Negative:**
- Exact-duplicate chunks within one source get order-dependent suffixes, so deleting one duplicate
  reassigns the suffixes of the rest. This is the single case where the ID is not purely
  content-derived, and it is accepted because the alternative breaks on the far more likely event.
- Any genuine edit to a chunk's text mints a new ID, so a typo correction in a manual does break the
  pointers into that passage. That is correct — the text changed — but it means a re-ingestion of a
  meaningfully revised manual will flag authored entries (triage 8.4) rather than resolve silently.
- Because section identity is outside the digest, two chunks with identical text in different
  sections are distinguished only by the ordinal suffix, not by anything a human reading the ID can
  interpret.

---

## Decision 6: Extract with PyMuPDF, not a text-only extractor

**Date**: 2026-08-14
**Status**: accepted

### Context

The retrieval research note proposed `pdftotext -layout` as the extraction step, and it is a
reasonable proposal: it measured 0.63 s over the 1009-page Live manual and preserves the visual
alignment that the Nitro Max MIDI note table depends on.

Three later requirements need information a text-only extractor discards. Row integrity (7.1–7.2)
needs cell bounding boxes to assign cells to columns by position rather than by index. Glyph repair
(5.1–5.2) needs the **font name** of the offending span. Sectioning (6.6) needs the embedded
outline.

### Decision

Extract with PyMuPDF via `page.get_text("dict")`, producing a per-page span model carrying text,
bounding box, font name, size and flags, plus `doc.get_toc()` for the outline. Stages annotate that
model; only the chunker flattens it to text.

### Rationale

The glyph case decides it. The APC guide's arrow symbols extract as `ð ñ ô õ` from a font named
`Wingdings3` which carries a ToUnicode CMap that maps its own byte codes into the Latin-1 supplement
— so the corruption is well-formed Unicode and no character-level rule identifies it as broken. The
same document's Spanish pages contain a genuine `ñ`. A character-only heuristic would either miss
the arrows or corrupt the Spanish; the **font name** separates them cleanly and is available only
from a structured extraction.

Row assembly needs the same structure for a different reason: whitespace-aligned text loses the
distinction between "a cell absent from this row" and "a cell whose text happens to be short", which
is exactly what the ragged 11-row/8-row panels on Nitro Max p25 present.

Cost is not a factor. PyMuPDF's dict mode is the same order as the measured 0.63 s, and 8.2 allows
5 s.

### Alternatives Considered

- **`pdftotext -layout`**: Fast, already proven on this corpus, preserves the visual alignment the
  Nitro table needs - Rejected because it exposes no font names (so glyph repair degrades to a
  character heuristic that cannot distinguish Spanish `ñ` from a broken arrow), no bounding boxes
  (so column assignment falls back to whitespace-position guessing) and no outline.
- **`pdfplumber`**: Good table extraction with an explicit table model, and it exposes character
  boxes - Rejected because it is substantially slower on a 1009-page document and its table detector
  is tuned for ruled tables; the panel tables here are unruled, so the detection work is needed
  regardless and the extra layer buys little.
- **Extract twice — PyMuPDF for structure, `pdftotext` for text**: Uses each where it is strongest -
  Rejected because it creates two texts that must agree; where they disagree, the citation and the
  index would refer to different strings.

### Consequences

**Positive:**
- Glyph repair is font-keyed, which is causal rather than heuristic and produces no false positives
  on genuinely accented text.
- Column assignment is by coordinate, which is what makes ragged panel rows survive.
- Sectioning gets the embedded outline directly, including the 816 Live entries.

**Negative:**
- A heavier dependency than a command-line extractor, and PyMuPDF is AGPL — acceptable for a local
  single-user tool that is not redistributed, but it constrains any future distribution.
- The span model is more code than a string, and every stage must preserve it correctly; a stage
  that flattens early silently disables the ones after it.

---

## Decision 7: Per-source shards merged into a flat read view

**Date**: 2026-08-14
**Status**: accepted

### Context

8.3 requires that adding one source not re-extract, re-chunk or re-index any unchanged source, while
8.7 requires that a source failing partway leaves neither partial output nor damage to what was
already indexed — with rollback scoped to the failing source, so its neighbours in the same run still
commit. 8.6 requires the whole index to be rebuildable from the two stores and nothing else. A
separate process reads the result concurrently.

The expensive stage is embedding at ~21 s for the full corpus; everything else totals under 10 s.

### Decision

Cache each source's passages and vectors as a **shard** under `index/shards/<slug>.*`, committed one
source at a time by atomic rename. Every run then rebuilds the merged read view — `passages.jsonl`,
`vectors.npy`, the lexical index and `sources.json` — by concatenating the committed shards, and
renames `manifest.json` into place last. The manifest carries `index_version`, a `corpus_revision`
digest, and per-source `row_start`/`row_count`.

### Rationale

Splitting the cheap work from the expensive work is what makes the requirements compose. Only
embedding is cached; the merge costs under a second even for a full corpus, so there is no reason to
make it incremental, and rebuilding it wholesale removes the entire class of bug where a deleted
source's chunks survive in a mutable store — 9.4 holds because nothing merges from anywhere else.

Commit ordering gives 8.7 without a transaction manager: a failed source leaves its temporary files
unmoved and its previous shard intact, the merge reads whatever shards exist, and the manifest
arriving last means a reader never sees a manifest naming an artefact that is not there.

`corpus_revision` exists because `api/answer-engine` 5.10 must detect a corpus change before the
next turn retrieves. One digest in a 4 KB file is cheaper to poll than any diff over the corpus.
`row_start`/`row_count` make source-scoped retrieval a contiguous array slice rather than a scan,
which matters because scoping to selected sources is the engine's normal case.

`index_version` makes the on-disk shape an explicit contract. A reader whose expected version
differs must refuse to load rather than interpret the files; the remedy is a rebuild, which costs
~31 s.

### Alternatives Considered

- **Rebuild everything on every run**: Simplest possible design, and the corpus is small - Rejected
  because the embedding stage alone is 21 s, which turns 8.4's "one new 50-page manual in under 10
  seconds" into an impossibility and makes adding a manual a chore the owner avoids, which is the
  outcome §8's user story exists to prevent.
- **Mutate the merged index in place** (append new chunks, delete removed ones): Avoids rewriting
  unchanged bytes - Rejected because deletion and compaction logic is the classic source of orphaned
  rows, and it would put the merged view in an inconsistent state mid-write while a separate process
  is reading it.
- **SQLite as the index container**: Real transactions, real atomicity, one file - Rejected because
  it reintroduces the dependency Decision 1 removed, and file renames already provide the atomicity
  actually needed here. It would become the right answer if concurrent *writers* ever existed.
- **Shards only, with the reader concatenating at load**: Removes the merge stage entirely -
  Rejected because it moves ordering and version-checking responsibility into the consumer, and
  CONTRACTS is explicit that this spec produces the records rather than the shape they are assembled
  from.

### Consequences

**Positive:**
- Adding one manual costs only that manual's extraction, chunking and embedding.
- Rollback is a file that was never renamed; there is no partial state to repair.
- The read contract is two files whose row ordering is guaranteed to correspond, which is simple
  enough for the consumer to depend on without a library.

**Negative:**
- The shards duplicate the merged view on disk, roughly doubling index size to under 15 MB. Trivial
  here, and it would not be at a much larger corpus.
- Shard files are a cache with no independent validation: a corrupted shard is merged as though it
  were sound. The source fingerprint detects a changed *source*, not a damaged cache; recovery is
  deleting `index/` and rebuilding.
- `index_version` must be bumped by hand when the shape changes, and forgetting to bump it lets a
  stale reader interpret new files.
