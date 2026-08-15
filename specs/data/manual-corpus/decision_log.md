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

The index must be queryable by a separate process within a 50 ms retrieval budget (CONTRACTS §7) and
rebuildable from the source stores in under 60 s (8.1, 8.6). The surrounding literature assumes a
vector store. This corpus does not need one: ~250,000 words at a 350-word cap is 800–1,200 chunks,
which at 384 float32 dimensions is **1.8 MB**.

### Decision

Hold the dense index as a single `vectors.npy` array (float32, L2-normalised) and search it by
brute-force matrix–vector product with NumPy. No vector database, no approximate-nearest-neighbour
index.

### Rationale

A full cosine scan plus top-10 selection over 2,000 × 384 vectors measures **0.011 ms**. The query
encode that must precede it takes **2.2 ms** — 200 times longer. ANN indexing exists to trade recall
away to avoid an expensive exhaustive scan; here the exhaustive scan is exact and free, so
approximating it would sacrifice correctness to improve a quantity below measurement noise.

### Alternatives Considered

- **sqlite-vec**: Also exact brute force by default, and right if SQL metadata filtering were needed
  - Rejected: a loadable extension and a schema for no measurable gain; source scoping is already a
  row-range slice via the manifest.
- **LanceDB**: Columnar on-disk format with ANN and versioning - Rejected: machinery for datasets
  that do not fit in memory. This one is 1.8 MB.
- **Qdrant**: Network service with HNSW - Rejected: the network hop alone costs two orders of
  magnitude more than the entire search it replaces.
- **SQLite FTS5 for the lexical half**: Built in, BM25 native - Rejected narrowly in favour of
  `bm25s`, which keeps the index as plain files rebuilt in one pass (8.6) and avoids tokeniser
  configuration in SQL. A close call, not a strong preference.

### Consequences

**Positive:**
- Zero dependencies beyond NumPy on the search path; the index is one inspectable `.npy` file.
- 8.6 falls out for free — no database state can drift from the source stores.
- Source-scoped retrieval is a contiguous row slice.

**Negative:**
- Metadata filtering must be written in Python rather than delegated to a query engine.
- The corpus ceiling that matters is not the scan, which stays under a millisecond well past any
  plausible size. It is **embedding**: at 42.4 chunks/s, 8.1's 60 s budget is spent by the embedding
  stage alone at ~2,500 chunks, roughly 2.5× the current corpus. The escape hatch is the shard cache
  (Decision 7) — a full rebuild is the only operation that pays it, and only after a model or
  ingestion-code change. Nothing about this decision moves that ceiling either way.

---

## Decision 2: Build both a dense and a lexical index; recommend RRF rather than specify it

**Date**: 2026-08-14
**Status**: accepted

### Context

What this spec writes to disk decides what retrieval is possible for `api/answer-engine`. Building
only `vectors.npy` forecloses lexical retrieval; building both leaves the choice open. Choosing
*between* them at query time does not belong here — `requirements.md` Non-Goals put retrieval
ranking and relevance scoring in `api/answer-engine`.

The questions this corpus answers are dense with exact strings a user reads off a screen and types
verbatim: device names ("Glue Compressor", "Utility"), parameter names ("Threshold", "Dry/Wet"),
control names ("Scene Launch"), and numbers ("MIDI note 38", "CC 74").

No acceptance criterion in this spec asks for either index or for an embedding model; 8.1's
"queryable" is the only hook. That is a requirements gap, recorded in `design.md`.

### Decision

Build **both** a dense index and a `bm25s` lexical index over the same passage ordering, and prefix
every chunk with its citation header before both embedding and lexical indexing. **Fusion is not
specified here.** Reciprocal Rank Fusion is handed to `api/answer-engine` as a recommendation with
the caveat below; that spec owns the choice and the parameter.

### Rationale

Dense retrieval fails on precisely the queries a user most expects to work. "Utility" is a common
English word that is also a Live device, and a dense model embeds it near "usefulness". "Threshold"
appears in dozens of devices with near-identical embeddings. Bare numerals are the worst case: 38
and 39 embed almost identically while the correct answer differs completely — and for the Nitro Max
MIDI note table that is the primary use case, not a marginal one. BM25 conversely cannot handle "how
do I make a sound quieter over time" → *fade / volume automation*. Neither is sufficient alone, so
both artefacts must exist regardless of how they are combined.

The cost is negligible: `bm25s` measures **0.047 ms per query** and **0.14 s to index 4,000 chunks**.
Anthropic's published measurements put adding BM25 to a dense retriever at a 2.9% failure rate
against 3.7% dense-only, on a general corpus; on one this identifier-dense the benefit should be
larger.

**The caveat handed on with the RRF recommendation.** RRF consumes only ranks, which is what makes
it robust, and it is also what makes k=60 wrong for this corpus at the margin. A chunk that both
retrievers rank mediocrely — ranks 10 and 20 — scores 1/70 + 1/80 = **0.0268**, while a verbatim
BM25 rank-1 match that dense misses entirely scores 1/61 = **0.0164** and loses. That is exactly the
"MIDI note 38" case: the query is a bare numeral, dense retrieval is blind to it, and the one
retriever that found the right row is outvoted by two retrievers that half-found the wrong one. A
smaller k, or a floor on rank-1 lexical hits, is likely needed. Deciding it requires query-set
evaluation, which is `api/answer-engine`'s work, not ingestion's.

### Alternatives Considered

- **Dense-only**: One index, one code path, no tokenisation questions - Rejected because it fails on
  exact identifiers, which is the majority of real queries here, and the failures are silent.
- **BM25-only**: No embedding model, no 21-second build stage, no 67 MB prerequisite - Rejected
  because it cannot answer a symptom described in the user's own words, which is the whole reason
  `authored-triage` entries exist.
- **Specify the fusion method here** (the previous form of this decision): One less thing for the
  consumer to decide - Rejected as out of scope: it is query-time ranking, it cannot be validated by
  anything this spec builds or tests, and the k=60 caveat above shows the specified value would have
  been wrong.
- **Weighted score blending instead of RRF**: Preserves score magnitude, so a runaway-best lexical
  match outranks a merely-good one - Not rejected outright; passed on with the same caveat. The
  common objection — that normalisation parameters "drift as the corpus changes" — is false: per-
  query min-max normalisation stores nothing and recomputes on every query, so there is nothing to
  drift. The honest objection is outlier fragility: one runaway BM25 score compresses every other
  candidate towards zero, and the compression is invisible.

### Consequences

**Positive:**
- Exact strings and paraphrases both retrieve, and the choice of how to combine them stays where the
  evaluation data is.
- The citation header puts the exact product and section strings into the lexical index, where
  verbatim queries land — most of the benefit of contextual retrieval at no model cost.

**Negative:**
- Two indexes to build, commit and keep in step with the same passage ordering; a bug that
  desynchronises them mis-cites silently.
- The lexical tokeniser must not destroy "Dry/Wet", hyphenated identifiers or bare numerals, and
  that failure is quiet. `design.md`'s Testing Strategy carries the explicit test.
- `api/answer-engine` inherits an unresolved parameter rather than a specified one.

---

## Decision 3: 350-word chunk cap, derived from the embedding window

**Date**: 2026-08-14
**Status**: accepted

### Context

A chunk cap has to be chosen. The intuitive basis is readability — short enough that a person can
check the quoted text against the printed page — which suggests something around 500 words. The
draft requirements originally said 500. The dense index is built with `bge-small-en-v1.5`, whose
input window is **512 tokens**.

### Decision

Cap chunks at **350 words**, record in the requirements (6.9) that the bound comes from the
retrieval window rather than from readability, and **assert the encoded length at embed time**
rather than trusting the word count.

### Rationale

A 500-word chunk of manual prose measures **601 tokens** with the BGE tokeniser. Overflow is not an
error — it is a **silent truncation**. The last ~90 words of every maximal chunk would never reach
the embedding while still appearing in the lexical index and in the text shown to the user.

350 words is ~420 tokens, leaving ~90 tokens of headroom for the citation header and tokeniser
variance. It also embeds 31% faster (42.4 against 32.3 chunks/s measured), pulling the embedding
stage from 28 s to 21 s inside 8.1's budget. Readability is better served at 350 words than at 500,
so nothing is traded away.

A word cap is an estimate of a token bound, and the estimate is worst for exactly the content this
corpus is full of: serialised table rows run far above the 1.2 tokens/word that prose averages. The
BGE tokeniser is already loaded at embed time, so measuring the real encoded length costs nothing —
and converts the residual risk from a silent truncation into a report line.

### Alternatives Considered

- **Keep 500 words and accept truncation**: No change to the chunker - Rejected because the failure
  is silent and unbounded: nothing surfaces which chunks lost their tail or what was in it.
- **Keep 500 words and use a longer-context model** (`nomic-embed-text-v1.5`, 8,192 tokens): Removes
  the constraint entirely - Rejected on measured build cost: 10.6 chunks/s against 42.4, an 85 s
  embedding stage that breaches 8.1 on that stage alone, to buy context the chunker would not use.
- **Cap by tokens rather than words**: Exact against the real constraint - Rejected because it makes
  the cap depend on the embedding model, so changing the model silently rewrites every chunk
  boundary and therefore every `passage_id`. A word cap with headroom is stable across model choice,
  and the embed-time assertion recovers the exactness without the coupling.

### Consequences

**Positive:**
- No chunk is ever partly invisible to dense retrieval, and any chunk within 32 tokens of the window
  is named in the run report rather than discovered later.
- Faster embedding stage and smaller prompts downstream; time to first token scales with prompt
  length, so the cap is also the highest-leverage latency decision available here.

**Negative:**
- More chunks for the same corpus, so more overlap duplication and more near-duplicate hits in a
  result list.
- A long procedure or table is more likely to exceed the cap and be split, making the
  split-with-repeated-heading paths (7.4, 7.5) load-bearing rather than rare.
- A chunk that trips the embed-time assertion has no automatic remedy: the chunker cannot re-split
  it without changing every `passage_id` in its region, so it is reported and left.

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
fallback in the report. Carry each entry's parent chain from the outline's own level column.

### Rationale

The TOC and the headings each supply half of what a citation needs and neither supplies both. The
TOC gives authoritative titles, numbers and ordering, but its page number is too coarse: with 1.2
entries per page, page-granular attribution would place several sections' text under one heading and
cite the wrong section. In-body headings give exact position but no reliable numbering or hierarchy,
since heading style is a visual convention that varies per document.

The parent chain is not decoration. 54 of Live's section titles are duplicated across the TOC and
`Sidechain Parameters` occurs eight times; the leaf title alone cannot distinguish the Glue
Compressor's from the seven others, and the citation header exists precisely to make that
distinction. The outline already reports the level, so the chain costs nothing to keep and ~11
tokens to carry.

Anchoring degrades in a visible way: a failed anchor produces a page-granular section plus a report
line, rather than a confidently wrong citation. Live's in-body headings are printed with their
numbers (`24.1 An Overview of Racks`), so the match succeeds on the first attempt for the
overwhelming majority of the 816 entries. The ordered fallback chain also means the APC guide, which
has no machine-readable structure at all, still produces titled unnumbered sections under 6.4.

### Alternatives Considered

- **Heading detection only** (font size and weight clustering, no TOC): Works on any document -
  Rejected because it cannot recover section *numbers*, which 6.3 requires for a `§24.9`-shaped
  citation, and heading hierarchy inferred from font size is unreliable in a 1009-page document with
  many styles. Retained as the last fallback, behind a quality gate, not as the primary path.
- **TOC page numbers only, no anchoring**: Simple, and correct for documents with one section per
  page - Rejected because Live averages 1.2 entries per page, so it mis-attributes routinely and
  silently.
- **Semantic or model-driven segmentation**: Works on documents with no structure at all - Rejected
  because ingestion is offline and requires no network (8.5), it produces titles that are not the
  document's own, and it cannot produce a section number that matches what the user sees.

### Consequences

**Positive:**
- Citations name the document's own section number and title, so a user can verify against the
  printed page in seconds.
- Sectioning quality is measurable: the count of page-only anchors is a per-source report line, and
  path-C regions are marked `inferred`.
- Three documents with three different structures work through one mechanism and no configuration.

**Negative:**
- Anchoring is text matching and can fail when an in-body heading is worded differently from its
  TOC entry, or is split by a line break; those cases silently degrade to page granularity, visible
  only in the report.
- Three code paths for structure extraction, each needing its own fixtures.
- A document that fails path C's quality gate collapses to a single region and produces weak
  citations, as 6.4 anticipates. That is the intended outcome: path C firing *wrongly* — two bogus
  regions from a cover title and a strapline — mis-names every citation in the document, which is
  worse than one weak region.

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

Nothing else enters the digest. Where k > 1 chunks within one source produce the same digest, the
**first in document order keeps the unsuffixed ID** and the 2nd…kth are suffixed `.2 … .k`.

### Rationale

Each exclusion answers a specific way the ID could otherwise break:

| Excluded | Would break on |
|---|---|
| section number, section title, citation header | a point release renumbering sections (triage 8.3) |
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

**The duplicate rule is deliberately asymmetric.** Suffixing all k occurrences would mean that when
re-ingestion introduces a *second* copy of previously-unique boilerplate, the first copy's stable ID
ceases to exist and becomes `.1` — a retained citation pointing at text that did not change stops
resolving because of an edit elsewhere in the document. Leaving the first occurrence unsuffixed
confines the churn to the newly introduced duplicates, which have no history to orphan. The property
*introducing a duplicate elsewhere in a source does not change the ID of the pre-existing chunk* is
asserted in the Testing Strategy.

Truncation to 16 hex characters gives 64 bits; at ~1,200 chunks the accidental collision probability
is ~4 × 10⁻¹⁴, and the duplicate rule handles real duplicates deterministically regardless.

**Determinism is a property of the pipeline, not of this function.** 6.1 is satisfied only if the
whole run is a pure function of the PDF bytes: a stage that iterated a set, keyed on a dictionary's
insertion order, consulted the wall clock or depended on the locale would change chunk boundaries
and therefore IDs while this function stayed correct. The guarantee is tested end to end — the same
bytes ingested twice yield the identical `(passage_id, text)` sequence — not by re-hashing one
string.

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
- **Suffix every member of a duplicate set** `.1 … .k`: One uniform rule, no special case for the
  first occurrence - Rejected for the reason given above: it destroys a pre-existing stable ID when
  a duplicate appears, breaching 6.1 and triage 8.2.

### Consequences

**Positive:**
- A manual can be re-ingested, updated to a new document version, or re-extracted by a newer library
  without invalidating retained citations or authored fix pointers.
- The ID is verifiable: given a passage's text and its source ID, anyone can recompute it.
- **The blast radius of an edit is one section.** Greedy packing makes every chunk boundary a
  function of everything before it, so a one-sentence vendor edit does re-mint every passage ID
  after it — but packing restarts at each region and overlap never crosses a region boundary, so
  "after it" means "later in the same section", not "in the rest of the manual". That confinement is
  the actual guarantee, and it is why region-scoped packing is not merely a chunking convenience.

**Negative:**
- Exact-duplicate chunks within one source get order-dependent suffixes, so deleting the *first*
  duplicate promotes the second to the unsuffixed ID. Narrower than the alternative, not free.
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

PyMuPDF is licensed AGPL-3.0-or-later.

### Decision

Extract with PyMuPDF via `page.get_text("dict")` with `TEXT_PRESERVE_IMAGES` cleared, producing a
per-page span model carrying text, bounding box, font name, size and flags, plus `doc.get_toc()` for
the outline. Stages annotate that model; only the chunker flattens it to text. **Confine the
dependency to `dawmans/corpus/pdf/`; the API process never imports it.**

### Rationale

The glyph case decides it. The APC guide's arrow symbols extract as `ð ñ ô õ` from a font named
`Wingdings3` whose ToUnicode CMap maps its own byte codes into the Latin-1 supplement — so the
corruption is well-formed Unicode and no character-level rule identifies it as broken. The same
document's Spanish pages contain a genuine `ñ`. A character-only heuristic would either miss the
arrows or corrupt the Spanish; the **font name** separates them cleanly and is available only from a
structured extraction.

Row assembly needs the same structure for a different reason: whitespace-aligned text loses the
distinction between "a cell absent from this row" and "a cell whose text happens to be short", which
is exactly what the ragged 11-row/8-row panels on Nitro Max p25 present.

Cost is not a factor. PyMuPDF's dict mode is the same order as the measured 0.63 s, and 8.2 allows
5 s — provided `TEXT_PRESERVE_IMAGES` is cleared, since the default materialises image bytes into
the returned structure and Live carries 96 MB of screenshots.

**On the licence.** The event that triggers AGPL is not packaging or redistribution to a third
party, as an earlier form of this entry implied: it is **publishing this repository**, because
conveying a work that imports PyMuPDF requires the combined work to be AGPL-3.0-or-later. §13's
network clause does *not* fire — the library is unmodified, the sole user is local, and nothing is
offered over a network. Confining the import to the ingestion module is what keeps the question
answerable: the copyleft attaches to a tool the owner runs, and the API process — the component most
likely to be served or reused — never links it.

### Alternatives Considered

- **`pdftotext -layout`**: Fast, already proven on this corpus, preserves the visual alignment the
  Nitro table needs - Rejected because it exposes no font names (so glyph repair degrades to a
  character heuristic that cannot distinguish Spanish `ñ` from a broken arrow), no bounding boxes
  (so column assignment falls back to whitespace-position guessing) and no outline. GPL-2.0
  regardless, so it is not the lighter licence either.
- **`pdfplumber`** (MIT): Good table extraction with an explicit table model, exposes character
  boxes, and would avoid the copyleft entirely - Rejected because it is substantially slower on a
  1009-page document and its table detector is tuned for ruled tables; the panel tables here are
  unruled, so the detection work is needed regardless and the extra layer buys little.
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
- Publishing this repository means licensing it AGPL-3.0-or-later. Acceptable for a local
  single-user tool, and the confinement above keeps it from reaching the API process, but it is a
  standing constraint and `design.md` must not describe `src/dawmans/` as a distributable package
  without saying so.
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
source at a time by atomic rename. Key the cache on the source fingerprint **plus the embedding
model, its dimension, and an ingestion-code version**. Every run rebuilds the merged read view into
a fresh `index/views/<hex>/` directory by concatenating the committed shards, and renames
`manifest.json` — which names that directory — into place last.

### Rationale

Splitting the cheap work from the expensive work is what makes the requirements compose. Only
embedding is cached; the merge costs under a second even for a full corpus, so rebuilding it
wholesale removes the entire class of bug where a deleted source's chunks survive in a mutable store
— 9.4 holds because nothing merges from anywhere else.

**The cache key is the part that is easy to get wrong.** Keyed on the PDF fingerprint alone, a
change of embedding model reuses every shard, so `vectors.npy` concatenates vectors from two models
under a manifest declaring one. They are incomparable, nothing errors, and `index_version` does not
catch it because the on-disk shape is identical. The same hole means a fixed table-assembly bug
reaches nothing, since no PDF byte changed — which defeats §8's own user story, "adding a manual or
fixing an ingestion bug never becomes a chore". Both are closed by putting the model, its dimension
and a hand-bumped `ingestion_version` in the shard meta and re-ingesting on any mismatch.

Commit ordering gives 8.7 without a transaction manager. The subtlety is that the merged view is
four artefacts, one of which (`lexical/`) is a directory: renaming them individually lets a reader
that has already loaded the manifest pair one version's `row_start`/`row_count` against another
version's rows. Writing each view into a fresh directory and switching by the manifest rename makes
that one rename the only visible transition.

`corpus_revision` exists because `api/answer-engine` 5.10 must detect a corpus change before the
next turn retrieves; one digest in a 4 KB file is cheaper to poll than any diff. `row_start`/
`row_count` make source-scoped retrieval a contiguous slice, which requires the manifest's source
order to be deterministic — it is sorted by `source_id`, because a filesystem-iteration order would
let offsets move while `corpus_revision`, hashed over *sorted* triples, stayed the same.

### Alternatives Considered

- **Rebuild everything on every run**: Simplest possible design, and the corpus is small - Rejected
  because the embedding stage alone is 21 s, which turns 8.4's "one new 50-page manual in under 10
  seconds" into an impossibility.
- **Mutate the merged index in place** (append new chunks, delete removed ones): Avoids rewriting
  unchanged bytes - Rejected because deletion and compaction logic is the classic source of orphaned
  rows, and it would put the merged view in an inconsistent state mid-write while a separate process
  is reading it.
- **Replace the merged files in place, one atomic rename each**: No view directories to garbage-
  collect - Rejected because it is not atomic across four artefacts, and `lexical/` is a directory
  that no single rename can swap.
- **SQLite as the index container**: Real transactions, real atomicity, one file - Rejected because
  it reintroduces the dependency Decision 1 removed, and file renames already provide the atomicity
  actually needed. It would become the right answer if concurrent *writers* ever existed.
- **Shards only, with the reader concatenating at load**: Removes the merge stage entirely -
  Rejected because it moves ordering and version-checking responsibility into the consumer, and
  CONTRACTS is explicit that this spec produces the records rather than the shape they are assembled
  from.

### Consequences

**Positive:**
- Adding one manual costs only that manual's extraction, chunking and embedding; editing one
  authored entry costs only that entry, because the authored shard reuses vectors per `passage_id`.
- Rollback is a file that was never renamed; there is no partial state to repair.
- The read contract is two files whose row ordering is guaranteed to correspond, which is simple
  enough for the consumer to depend on without a library.

**Negative:**
- The shards duplicate the merged view on disk, roughly doubling index size to under 15 MB. Trivial
  here, and it would not be at a much larger corpus.
- Superseded view directories cannot be deleted at the end of the run that replaces them, because a
  reader may still hold the previous manifest; they are collected at the start of the next run, so a
  crash leaves one orphan directory behind.
- Shard files are a cache with no independent validation: a corrupted shard is merged as though it
  were sound. The cache key detects a changed source, model or pipeline, not a damaged file;
  recovery is deleting `index/` and rebuilding.
- Two version integers must be bumped by hand — `index_version` when the on-disk shape changes,
  `ingestion_version` when a stage's output could change — and forgetting either is silent.

---

## Decision 8: Ingestion audits beside the views, view sidecars inside them

**Date**: 2026-08-14
**Status**: accepted

### Context

`LoadResult.report` was one channel carrying two unrelated payloads, and the design published both to
one place, `index/reports/<slug>.json`. The first payload is an ingestion audit — English page
ranges, glyph counts, anchor quality, the rejection reason — a diagnostic for one run over one
source. The second is the authored-triage sidecar `data/symptom-triage` specifies: per-`passage_id`
device declarations and per-cause structure that CONTRACTS §2 has no field for, read by
`api/answer-engine` on every turn to satisfy its 5.13 device predicate and its 7.2 narrowing.

Published beside the views, the sidecar has no atomic switch. `manifest.json`'s rename is the only
one this spec offers, so a sidecar rewritten in place pairs with whichever view a reader is holding.
The consequence is not a stale diagnostic but wrong answers: entries dropped from turns they apply
to, entries admitted into turns scoped to other gear, and — where a reader finds no sidecar at all —
every entry in scope for every turn. `data/symptom-triage` §The sidecar listed the relocation as its
first outstanding request on this spec, and `api/answer-engine` §What the engine reads recorded it as
a blocking prerequisite: that design pins `<manifest.view_dir>/reports/authored_triage.json` and did
not hold until this landed.

### Decision

Split the channel. `LoadResult` carries `audit` and `sidecar` separately. The audit is published to
`index/audits/<slug>.json`, keeping the shard's lifetime. The sidecar is committed as a shard
artefact, `shards/<slug>.sidecar.json`, and copied by the merge into `views/<hex>/reports/<slug>.json`,
where it joins the merged view's read contract and swaps with the manifest rename.

### Rationale

The two payloads have different lifetimes because they describe different things. An audit describes
a *run over a source*: it is regenerated only when that source is re-ingested, it must survive shard
reuse unchanged, and it has to remain findable after the view it accompanied has been collected —
the run that rejected a source is exactly the run whose diagnostics are wanted later. A sidecar
describes *the passages in a view*: it is only meaningful against the `passage_id`s it keys, so its
correctness is a function of being the same revision as `passages.jsonl`.

Copying the sidecar in from the shard, rather than writing it into the view from `load()`, is what
makes that revision guarantee structural. A reused shard runs no loader, so a loader-written sidecar
would be missing from every view built after the run that produced it. Copying at merge holds for any
source, instead of resting on the authored store's `load()` happening to run unconditionally
(`data/symptom-triage` §Discovery) — a property of a sibling spec that could change without this one
noticing.

The directory is `audits/` rather than a second `reports/` because two files at the same basename
`<slug>.json`, distinguished only by their parent, fail silently when resolved wrongly: the reader
gets a well-formed JSON document rather than an error. That is the same failure mode
`data/symptom-triage` names for a hyphenated sidecar spelling, and a distinct name costs nothing.

### Alternatives Considered

- **Move every report inside the view**: One location, one lifetime, no split to explain - Rejected
  because superseded views are deleted at the start of the next run, so a source's audit would
  survive at most one further run; the diagnostics for a rejection would be gone by the time anyone
  looked. It also forces every reused shard's audit to be copied forward for a reader that has no use
  for it.
- **Leave both beside the views and have the engine re-read on a manifest change**: No change to this
  spec at all - Rejected because there is nothing to re-read *to*. The file is mutable in place and
  carries no revision, so a reader that reloads after the swap still gets whatever the next run has
  since overwritten. No read order closes a race that has no versioned object in it.
- **Fold the sidecar's fields into `Passage` and drop the file**: Removes the second artefact
  entirely - Rejected because CONTRACTS §2 fixes the `Passage` field set and forbids a spec inventing
  one; and retargeting a fix pointer would then change the passage text, orphaning the citation
  history that `data/symptom-triage` 8.2 and this spec's 6.1 exist to preserve.
- **Write the sidecar into the view directly from `load()`, skipping the shard**: One fewer artefact
  and one fewer copy - Rejected because a reused shard runs no loader: any view built by a run that
  skipped the source would hold no sidecar for it, which is the same silent under-scoping in a new
  costume.
- **Keep both directories named `reports/`**: Nothing to rename, and the parent already disambiguates
  - Rejected for the silent-resolution failure above.

### Consequences

**Positive:**
- The sidecar and the passages it keys are always the same revision, by construction rather than by a
  reader's discipline. `api/answer-engine`'s blocking prerequisite is discharged and its stated path
  is the one this spec writes.
- Ingestion diagnostics outlive the views, so a rejection stays diagnosable after later runs.
- The rule generalises: any future loader with per-passage data beyond the `Passage` fields publishes
  a sidecar and gets the atomic swap free.

**Negative:**
- Two locations and two names to know, where there was one; a reader has to be told which of
  `audits/` and `views/<hex>/reports/` it wants.
- One more shard artefact to write, copy, and delete on source removal — cheap at ~10 KB, but it is
  another file whose absence is only caught by the reader that needs it.
- The audit for a source is now silently older than the view sitting beside it whenever that source's
  shard was reused. That is correct, and it reads as staleness to anyone who has not read §Index
  layout.

### Impact

`data/manual-corpus` §Index layout, §Stages, §The loader protocol, §Source identity and discovery,
§English selection, §Glyph repair, §Incremental behaviour, §Testing Strategy.
`data/symptom-triage` §The sidecar and its dependency table — the request is discharged, not dropped.
`api/answer-engine` §What the engine reads — the blocking-prerequisite paragraph is removed.

---

## Decision 9: The rig join runs through a declared mapping, not through the source ID

**Date**: 2026-08-14
**Status**: accepted

### Context

The two gap reports of §11 compare what is owned against what is indexed. Both sides use the
`<vendor>/<product>` shape, which invites the assumption that they can be joined on the source ID
directly. They cannot. `DECISIONS.md` Decision 2 has the filename's `product` follow the vendor on
generation markers, so the corpus holds `focusrite/scarlett-solo-4g` while `rig.yaml` declares the
device as `focusrite/scarlett-solo`. The same product, two identifiers.

The design already computed both reports over a source's declared `source_applicability.device`
rather than over its source ID, which is the right join and handles this exactly. The hazard is the
*default*: 11.2 records an undeclared source as `assumed` for the product named in its filename. For
the Focusrite that resolves to a device id no rig entry holds, so the source silently misses the
device, and the device — whose manual is sitting in `manuals/` — is reported as owned-but-undocumented
with nothing naming the cause.

### Decision

Where a filename's `product` carries a generation marker the rig's device id does not, the
`source_applicability` declaration mapping the two is **mandatory**. 11.7 backs it with a check: the
ingestion run report names every indexed `vendor-manual` source whose resolved applicability device
is not in the rig inventory. The line is informational, never an error, and never appears in
`gaps.json`.

### Rationale

Making the declaration mandatory rather than inferring the relationship keeps the system out of the
business of guessing which suffixes are generation markers. `-4g`, `-mk2`, `-gen4`, `-mkii` and
`-4th-gen` are all in circulation, the list is open, and a wrong guess would join two genuinely
different products — the failure Decision 9 in `DECISIONS.md` exists to prevent, arrived at from the
other direction.

The report line is what makes the mandate enforceable without inventing an error condition. A manual
for gear the owner does not hold is perfectly legitimate and must not fail a run, so the same
observation cannot be a rejection. What it can be is a *pairing*: an undeclared generation marker
puts the device on owned-but-undocumented and the source on indexed-but-not-owned at the same time,
and that pair appears together only in this one case. A genuine gap produces the first alone; a
genuinely unowned manual produces the second alone.

Keeping the line out of `gaps.json` follows `CONTRACTS.md` §5, which governs two reports. A manual
for unowned gear is not a gap in the rig, the engine has no consumer for it, and adding a third
member to a published payload to carry an ingestion-time diagnostic would oblige two other specs to
render something neither has a use for.

### Alternatives Considered

- **Join on source ID and forbid generation markers in `product`**: Rename the file to `focusrite_scarlett-solo_user-guide_v4.0_en.pdf` so the two inventories share one identifier - Rejected because it breaks the revision comparison that `DECISIONS.md` Decision 9 rests on. If the generation is in the ID, an mk1 guide and an mk2 device hold different IDs, never meet, and documented-but-unconfirmed cannot fire on the mismatch it exists to catch. It also asks the transcriber to decide what counts as a generation, which Decision 2 rejected on its own grounds.
- **Infer the mapping by stripping known generation suffixes**: Match `scarlett-solo-4g` to `scarlett-solo` automatically with a suffix table - Rejected because the suffix list is open and the failure is silent and wrong: two distinct products that happen to share a prefix would be joined, and a joined pair reports as documented when it is not.
- **Reject a source whose applicability device is not in the rig**: Treat the unmatched case as a hard error at ingest - Rejected because holding a manual for gear the owner does not own is legitimate — a borrowed unit, a device sold on, a manual obtained ahead of the hardware — and a run that fails on it would force a rig entry for a device the user does not have.
- **Publish the third report in `gaps.json` alongside the other two**: Give consumers the full picture in one payload - Rejected because `CONTRACTS.md` §5 governs two reports with named consumers, and this one has none. It is an ingestion-time diagnostic for whoever maintains `rig.yaml`, and that reader is looking at the run report already.

### Consequences

**Positive:**
- The one silent failure in the rig join is now named at the point where it can be fixed.
- The pairing across two reports identifies the cause, not just the symptom, without any new error state.
- No suffix table, no inference, nothing to keep current as vendors invent new generation markers.

**Negative:**
- A hand-written declaration is still required, so the omission this guards against remains possible — the report names it after the fact rather than preventing it.
- A third report is a third thing to compute and test, for a condition that is legitimate more often than it is a mistake.
- The run report grows a line most runs will render empty, which is one more thing to read past.

---

## Decision 10: Path B and C fixtures withhold an outline the corpus does have

**Date**: 2026-08-15
**Status**: accepted

### Context

Capturing the fixtures of task 11 was the first time the reference PDFs were read rather than
described, and three of the design's claims about them did not survive it. **All four manuals carry
an embedded outline**: Live 12 has 1054 entries (the design says 816, from an earlier version), the
Akai APC Key 25 guide has 38 and the Alesis Nitro Max 28 — so path A fires for every source in the
corpus and paths B and C have no live instance at all. Live's printed contents pages carry **no dot
leaders**: the page numbers are a separate right-hand column of bare numerals, extracted ahead of
the titles, so path B's dot-leader test does not detect them either. Only the Nitro Max contents
page has leaders.

Paths B and C are not therefore dead code to be deleted. They are what the next manual will need,
and the design chose them as content-side structure rather than per-manual configuration for
exactly that reason. But they cannot be tested against a corpus source as it stands, and a stage
with no test is a stage that will be wrong when it first matters.

### Decision

The path B and C fixtures — `apc_no_toc` and `cover_only` — are captured **with the outline
withheld** (`--toc none`), so a real page of a real manual stands in for a document that has no
outline. The capture list records the withholding against each fixture, and `Capture.toc` documents
why the option exists.

### Rationale

The alternative inputs to those two paths are worse in ways that matter. A synthesised PDF has
synthetic typography: the heading-style gate measures the ratio of a candidate style's line length
to the modal line length, how many headings there are and how they are spread, and every one of
those numbers would be a number the test author chose rather than one a real document produced. The
APC pages give the gate genuine, awkward input — a nine-point heading over eight-point body, six
headings on one page and none on the next — and the only thing withheld is a structure the path is
defined by not having.

Withholding is honest because it is recorded. `toc: none` sits beside the fixture's page range in
`tools/capture_fixture.py`, and the fixture file itself carries an empty `toc` and a note saying
what it stands for. Nobody reading the failing test later concludes the APC guide has no outline.

### Alternatives Considered

- **Synthesise PDFs for paths B and C**: Generate documents with no outline, a dot-leader contents page and a heading hierarchy - Rejected because the quality gate's thresholds would then be tested against typography chosen to pass them. It is the same circularity as asserting a regular expression against a string written to match it, and path C's gate is precisely the thing the design calls dangerous.
- **Obtain a manual that genuinely has neither**: Add a fifth source to the corpus to serve the two paths - Rejected because the corpus is the studio owner's own gear (requirement 11.1's rig is the whole point), and adding a document nobody owns to make a test pass inverts that. It would also arrive with its own drift the moment the vendor reissues it.
- **Delete paths B and C and keep only the outline path**: Ingest what the corpus has and add the others when a source needs them - Rejected because it fails 6.5 for the first manual that arrives without an outline, and that manual is discovered in production. It would also discard the printed-contents detection that Live needs for a different reason: its contents pages must be excluded from chunking whether or not they are the sectioning source.
- **Test the paths only through their unit predicates**: Assert the dot-leader grammar and the style gate directly, with no document behind them - Rejected as insufficient rather than wrong. Those tests are worth having and are in task 18, but neither exercises anchoring, region derivation or the interaction with furniture marks, which is where the paths actually break.

### Consequences

**Positive:**
- Paths B and C get realistic input without inventing a document or acquiring one.
- The corpus facts are now written down where the next reader of §Section map will meet them, instead of being rediscovered at task 19.
- Live's contents pages are pinned as a fixture before the detector that has to catch them is written, so the "no dot leaders" case cannot be missed.

**Negative:**
- Two fixtures assert against a document that does not exist in exactly that form, and the withholding has to stay documented or it reads as a corpus fact.
- Path B still has no fixture of its own with leaders — the Nitro Max contents page is a candidate for one, and task 18 will need it.
- The design's §Section map reference-corpus column had to be corrected, and any downstream reasoning that rested on "the APC has no outline" is now suspect.

### Impact

`tools/capture_fixture.py` (the `toc` option and the capture list), `tests/fixtures/apc_no_toc.json`,
`tests/fixtures/cover_only.json`, and design §Section map. Task 18/19 inherit the correction:
the sectioning implementation must not assume path C ever runs against this corpus, and the
printed-contents detector cannot rest on dot leaders alone.

---

## Decision 11: Redaction masks character classes rather than dropping text

**Date**: 2026-08-15
**Status**: accepted

### Context

`manuals/` is gitignored because the vendor PDFs are copyrighted, and the fixtures are the one place
any of their text enters the repository. The design draws the line at the APC guide: full span text
for its 24 pages "would commit substantially the whole guide", so `apc_pages` keeps "bounding box,
font and a language label only".

Taken literally that fixture cannot drive the stage it exists for. English selection scores blocks,
does not score a block under eight words, and does not score a block whose tokens are predominantly
non-alphabetic — three measurements over text that a bbox-and-font-only fixture no longer has. The
fixture would assert the page ranges and nothing about how they were arrived at.

### Decision

Redaction replaces each character with its class — letters become `x` or `X`, digits `0`, and
punctuation and whitespace are left as they are — and attaches a per-block language label supplied
by hand at capture time. The test is `str.isalpha()`, not `[a-zA-Z]`, so accented characters are
masked too.

### Rationale

Every measurement the later stages make is a measurement of shape: word counts, line lengths, the
ratio of alphabetic to non-alphabetic tokens, the run of dots in a leader, the length of a heading
against the modal line. All of them survive masking exactly, and none of them needs a word. What
does not survive is the expression — which is what copyright protects and what the design's rule is
about.

Masking accented characters as well is not fastidiousness. On a multilingual guide `á`, `ñ` and `ü`
are precisely the characters that identify the language of the line they sit in, so a
`[a-zA-Z]`-only mask would leave the guide's Spanish, French, Italian and German pages
distinguishable from their remains.

The language label has to be ground truth supplied by hand, because a masked fixture cannot exercise
a language identifier at all. That is a real limit and it is the right one: `lingua-py` is a third-
party library and its accuracy is not this spec's to test, while the selection machinery around it —
block granularity, the two inheritance guards, the audit's page ranges — is.

### Alternatives Considered

- **Keep only bbox, font and a label, as the design says**: Drop the text entirely - Rejected because the short-block guard and the language-neutral guard both measure the text, so the fixture could not exercise the two rules that most need exercising. The design's intent — no words of the guide in the repository — is met by masking, and masking meets the stages' needs as well.
- **Capture the English pages in full and the rest redacted**: Commit pp3-6 and p23 verbatim, mask pp7-22 - Rejected because pp3-6 plus p23 is the entire English content of the guide. "Substantially the whole guide" is exactly what that is, in the one language a reader of this repository would want.
- **Replace each word with a fixed placeholder**: `word word word` in place of the text - Rejected because it destroys line lengths and the alphabetic-token ratio, which the language-neutral guard and path C's heading test both measure. Character-class masking preserves both at the same cost.
- **Hash each word**: Substitute a digest so identical words stay identical - Rejected because it preserves the word-frequency structure of the source, which is more of the original than the fixture needs, while also destroying the character shape the stages measure.

### Consequences

**Positive:**
- The one fixture that must be redacted still drives the stage it was captured for.
- No word of the APC guide is in the repository, and the accented-character hole is closed rather than left as a `[a-zA-Z]` oversight.
- The same masking is available to any future fixture that grows too large to commit verbatim.

**Negative:**
- The language labels are hand-written ground truth, so a mislabelled block is a test asserting the wrong thing with nothing to catch it.
- The redacted fixture cannot test the language identifier itself, only the selection around it, and that limit has to stay visible or a later reader will over-trust the fixture.
- A masked fixture is unreadable to a human checking whether it captured the right pages; the `asserts` note and the page range are all there is to go on.

---

## Decision 12: The language-neutral guard is confidence alone

**Date**: 2026-08-15
**Status**: accepted

### Context

The design's English selection scores blocks and gives two guards for when a score is not to be
trusted. The second reads: "A block whose top confidence is below 0.5 *and* whose tokens are
predominantly non-alphabetic inherits the same way." It was written for the Nitro Max MIDI note
table and the APC specifications table — numbers, units and dimensions that no identifier calls
English, and whose loss would take the pages that answer "which note does the kick pad send".

Running the finished stage against the real APC guide (24 pages, `multi`) showed the conjunction
leaking the other way. Physical pp11 and 15 — French and Italian — were selected as partly English.
The block responsible on p11 is `• Mac OS X : Live > Preferences`: eight tokens, five of them
alphabetic, scored English at 0.42. It passes the confidence half of the guard and fails the
alphabetic half, so it is trusted, and the short French step below it — `4. Cliquez sur l'onglet
MIDI/Sync.` — then inherits *from it* and reaches the index as English. That is requirement 4.1
failing on the one multilingual source in the corpus.

### Decision

A block inherits when the identifier's top confidence is below 0.5, whatever its tokens look like.
The "predominantly non-alphabetic" clause of the design's second guard is superseded.

### Rationale

Confidence below the threshold means the identifier has not decided anything, and a verdict it did
not reach is not evidence to index on. Inheriting the neighbouring decision is the safer answer in
both directions: on an English page the neighbours are English, and on a French page they are not.

The new condition is a strict superset of the old one — a table of numerals is unconfident as well
as non-alphabetic — so everything the guard was written to protect is still protected, and the tests
that pin the MIDI note table and the specifications table pass unchanged. Measured on the APC guide,
the audit goes from `english [[1,6],[11,11],[15,15],[23,24]]` to `english [[1,6],[23,24]],
excluded [[7,22]]`, which is what §4 describes.

### Alternatives Considered

- **Leave the guard as the design writes it**: Accept the two partial pages, since the audit reports them - Rejected because the audit reports the page as partial, not the sentence as French. A reader asking a question in English can be answered with a French step quoted as though it were the manual's English, which is exactly what 4.1 exists to prevent, and "it is in the audit" is not a defence a user ever sees.
- **Raise the confidence threshold instead**: Keep the conjunction, move 0.5 up until the false positive falls below it - Rejected because it treats a structural fault as a tuning problem. The UI-path line scores 0.42 and a genuine English paragraph in this corpus scores 0.73, so a threshold exists — but it would be fitted to one measurement on one guide, and the next fitting would be someone else's.
- **Exclude a block whose page is predominantly foreign**: Decide the page first, then the blocks in it - Rejected because it is page granularity wearing block granularity's clothes, and 4.3 asks for finer than a page so that a page holding two translations contributes its English part. The APC's own p23 appendix is the case that needs it.

### Consequences

**Positive:**
- No non-English text reaches the index from the one multilingual source in the corpus.
- The rule is one sentence rather than a conjunction, and the guard's two motivating cases are unaffected.
- The stage's selection now matches the audit §4's own example describes, so the requirement and the behaviour can be read against each other.

**Negative:**
- More blocks inherit rather than being scored, so a genuinely English block on an otherwise foreign page is now excluded unless the identifier is confident about it. On this corpus that is the intended outcome; on a future guide with long stretches of English inside a foreign chapter it costs coverage the old rule would have kept.
- A document whose every block scores under 0.5 is included whole, with nothing scored anywhere. That is the design's stated fallback and not new, but the wider guard makes it reachable by more documents.

### Impact

`src/dawmans/corpus/pdf/language.py` (`_score_block`), the design's §English selection, and the
`NEUTRAL_CONFIDENCE` constant's meaning. `tests/test_pdf_language.py` pins the measured case.

---

## Decision 13: Stage 7 and the load path are their own modules

**Date**: 2026-08-15
**Status**: accepted

### Context

The design's §Module placement names one module per stage through `pdf/layout.py` and then stops:
`Region[]` assembly and the `SourceLoader` implementation that runs the stages in order have no
module of their own in the tree. Implementing stage 7 made the gap concrete. Unit assembly is not
row geometry — it is the furniture drop, the atomic and `repeat_on_split` flags, the figure flag and
the page-break join — and the load path is not a stage at all but the order the stages run in, plus
the three rejections that can only be decided once a source has been read.

### Decision

Add `src/dawmans/corpus/pdf/units.py` (stage 7: the annotated span model into `Region[]`) and
`src/dawmans/corpus/pdf/loader.py` (`PdfLoader`), and record both in the design's module tree.
`layout.py` keeps to geometry and returns tables and prose runs; nothing else moves.

### Rationale

The stage table already treats these as two things — stage 7 *writes* `Region[]` while the loader
*is* the seam of 12.2 and 12.4 — and the ordering the design calls load-bearing has to be written
down somewhere a reader can find it. Putting either into `layout.py` would give that module two
jobs and make the AGPL-confined package's largest file the one with the least to do with PyMuPDF.
Putting the loader into `units.py` would mean a test of the furniture drop imports the module that
opens PDFs.

### Alternatives Considered

- **Both in `layout.py`**: One module for everything after sectioning - Rejected because row clustering and unit assembly fail differently and are tested differently; a table-detection regression should not be read against a page-break join in the same file.
- **`PdfLoader` in `corpus/loader.py` beside the protocol**: Keep the seam and its implementation together - Rejected because `corpus/loader.py` is interfaces only and is imported by `data/symptom-triage`; putting a PyMuPDF-importing class in it breaches the Decision 6 confinement outright.
- **No `units.py`, assemble inside `PdfLoader`**: Stage 7 as a private method of the loader - Rejected because stage 7's output is the shared shape and its tests want a `Document` in and `Region[]` out, with no store, no filename and no PDF.

### Consequences

**Positive:**
- Each module states one thing: geometry, assembly, order.
- Stage 7 is testable from a hand-built span model, which is how `tests/test_pdf_units.py` pins the furniture drop and the atomic flags without writing a PDF.
- The stage order and its three rejections are documented in one docstring rather than spread across the stages they sequence.

**Negative:**
- Two modules the design did not name, so a reader comparing tree to package finds more than the tree lists until this entry is read.
- `assemble()` takes an optional `spans` argument so the loader can reuse stage 5's output for its audit — a small seam between the two modules that would not exist if they were one.

### Impact

`src/dawmans/corpus/pdf/units.py`, `src/dawmans/corpus/pdf/loader.py`, design §Module placement.

---

## Decision 14: `entry_location` crosses the seam on `Region`

**Date**: 2026-08-15
**Status**: accepted

### Context

CONTRACTS §2 puts `entry_location` on `Passage` and requires it on every `authored-triage` passage —
`records.py` refuses to construct one without it, since it is the whole of the open-at-source action
for a source that has no page (CONTRACTS §3a). The chunker is the stage that constructs `Passage`
records, and the loader seam it reads had nowhere for the field to travel: `Region` and `Unit` carry
section identity, pages, order and flags, and nothing else.

Implementing the chunker made the gap unavoidable. `data/symptom-triage` publishes the entry's
`source_file` and line in its **sidecar**, which is keyed by `passage_id` — an identifier that does
not exist until the chunker has run. A sidecar therefore cannot supply a field the chunker needs in
order to emit the passage the sidecar would be keyed to.

### Decision

Add `entry_location: str | None = None` to `Region`. `TriageLoader` sets it, the chunker copies it
onto every `Passage` of that region unchanged, and no stage of this spec derives, clears or hashes
it. It stays `None` on a `vendor-manual`, which has a page instead.

### Rationale

A region is exactly one authored entry (`data/symptom-triage` §Passage emission: one `Region` per
entry, with the symptom as its `section_title`), so the entry's location is a property of the region
and of nothing smaller. Putting it on `Unit` would repeat one value across every cause of an entry
and invite a chunk whose units disagree about where the entry lives.

The field is inert for the `vendor-manual` half of the seam, which is what keeps 12.2 structural:
the chunker copies whatever is there, and the only branch anywhere is the `None` a manual carries.
It defaults, so no existing construction site changes.

### Alternatives Considered

- **Keep it in the sidecar and have the chunker read it back**: No seam change - Rejected as
  circular: the sidecar is keyed by `passage_id`, which the chunker is the stage that mints.
- **Put it on `Unit`**: Uniform with `unbacked`, which is per-unit for a real reason - Rejected
  because the location is per entry; per-unit invites disagreement inside one chunk and buys nothing.
- **Pass a map into the chunker beside the regions**: Keeps `Region` unchanged - Rejected because
  there is one authored source and many entries, so the map would have to be keyed by the region
  itself — which is the field, with an indirection in front of it.
- **Derive it in the chunker from the region title**: No plumbing at all - Rejected outright: 12.6
  gives the content and validation of an authored source to `data/symptom-triage`, and a derived
  locator would be a claim about a file this spec never read.

### Consequences

**Positive:**
- The one field CONTRACTS §2 requires on an authored passage has a route to the passage, and it is
  the same route as every other passage field: the region.
- The chunker stays kind-neutral — it copies a field rather than testing a kind.
- `Passage.__post_init__` now validates the seam end to end: an authored region reaching the chunker
  without a location fails at construction rather than producing a citation with no open action.

**Negative:**
- A field on the shared `Region` that is meaningless for every source in `manuals/`.
- `data/symptom-triage`'s own design table for `Region` construction does not yet list it, so that
  spec's emission table is one field behind this one until it is amended.

### Impact

`src/dawmans/corpus/loader.py`, `src/dawmans/corpus/chunk.py`, design §The loader protocol and
§`Region`/`Unit` → `Passage`, and an outstanding amendment to `data/symptom-triage` §Passage
emission.

---

## Decision 15: A repeat replaces overlap, rather than joining it

**Date**: 2026-08-15
**Status**: accepted

### Context

The chunker carries ~50 words of overlap into each continuation chunk within a region, and repeats
every `repeat_on_split` unit — a table's joined heading (7.5) — onto each part of a split.
`data/symptom-triage` §Passage emission requires the opposite for its own regions: "chunk overlap is
suppressed for authored regions", because an entry's symptom statement is a `repeat_on_split` unit
and a split entry would otherwise carry the symptom twice in text that is hashed into `passage_id`
and shown to the user when the citation is expanded.

Requirement 12.2 makes everything from `Region` onwards shared code, so the chunker cannot answer
this with an `if kind == "authored-triage"`.

### Decision

Overlap is taken only where the continuation chunk copies **no** `repeat_on_split` unit. Where a
repeat is copied, it is the whole of the carried text.

### Rationale

The rule is kind-neutral and states the actual reason: a repeat and overlap exist to do the same
job — give the continuation enough context to read on its own — and doing it twice duplicates text
into the digest. Written this way it covers the authored case the triage design asks for, and it
also covers the split table, where overlap was already forbidden because table rows are atomic.

It also keeps the cap honest. A chunk carrying a heading *and* 50 words of overlap has 50 fewer
words of room for the rows it exists to hold, on every part of every split table.

### Alternatives Considered

- **Suppress overlap for pageless regions**: One line, and it catches today's only case - Rejected
  because it keys on the wrong property: a pageless source is 12.8's concern, nothing about having
  no pages implies anything about continuity, and a future paged source with repeated units would
  get both.
- **Suppress overlap when the source kind is `authored-triage`**: Exactly what the triage design
  says - Rejected as the `if kind ==` branch 12.2 exists to prevent, in the one module that is most
  load-bearing for the seam.
- **Carry both**: No rule at all - Rejected because it duplicates the symptom statement inside
  `Passage.text`, which is hashed (6.1) and is what the user is shown when a citation is expanded.

### Consequences

**Positive:**
- One rule, stated in terms of the seam's own types, satisfies two specs.
- Split table chunks keep their full room for rows.

**Negative:**
- A region mixing prose and a table loses overlap at the split immediately after the table's heading
  is copied, where prose alone would have had it. The heading is the more useful of the two at that
  boundary, so this is a trade rather than a regression.

### Impact

`src/dawmans/corpus/chunk.py`, design §Chunking.

---

## Decision 16: The Nitro Max is reported documented-but-unconfirmed

**Date**: 2026-08-15
**Status**: accepted

### Context

Implementing the rig join (tasks 39–40) ran 11.5 against the committed `rig.yaml` and produced two
sources, not one. The design's §Rig inventory states the live outcome as "the first report is empty,
the second names `akai/apc-key-25`, and the third is empty", and 11.5 says "Today that is the Akai
APC Key 25 guide". Both are computed from the same worked `rig.yaml`, which declares four devices and
exactly two `source_applicability` entries — Live's and the Focusrite mapping.

`alesis/nitro-max` is not among those two. Under 11.2 an undeclared source is `assumed` for the
product named in its filename, so the Nitro Max guide resolves to `assumed` for device
`alesis/nitro-max`, which **is** in the rig inventory. 11.5's first arm — "an indexed source whose
applicability is `assumed` for a device in the rig inventory" — fires on it, before the revision
comparison is reached at all. The arms are a disjunction, so the fact that neither side declares a
revision does not save it.

### Decision

`rig.py` reports `alesis/nitro-max` alongside `akai/apc-key-25` under documented-but-unconfirmed,
and `rig.yaml` is committed with the design's two `source_applicability` entries and no third. The
design's "the second names `akai/apc-key-25`" and 11.5's "Today that is the Akai APC Key 25 guide"
are **superseded** as statements of the live outcome; the criteria they sit in are unchanged.

### Rationale

The alternative — adding `alesis/nitro-max: {device: alesis/nitro-max, status: confirmed}` to
`rig.yaml` — would make the reports match the prose, and it is the wrong way round. `confirmed` is a
claim that a human checked this document against this unit. Nobody has. 11.2 is explicit that nothing
is recorded as `confirmed` by default and that an undeclared source is unverified rather than
verified, and writing the declaration during implementation would be exactly the inference
CONTRACTS §5 forbids, dressed as a fix to a test.

Reporting the Nitro Max is also *correct* on its own terms. The ingested guide is v1.1 and the unit
declares no revision marker; whether the two agree is unknown, which is what `assumed` means and what
the report exists to surface. The APC is the *interesting* instance because its mismatch is known —
that is why the requirements name it — but "interesting" and "the only one" are different claims, and
only the second is wrong.

The remedy stays open and costs one line: the owner declares the Nitro Max `confirmed` once they have
checked the guide against the unit, and the report drops back to naming the APC alone.

### Alternatives Considered

- **Declare `alesis/nitro-max` confirmed in `rig.yaml`**: One entry, and both documents' prose becomes true - Rejected because it fabricates a verification nobody performed, which is the single thing 11.2 and CONTRACTS §5 both forbid. The report would then be silent about a source whose applicability is genuinely unknown, which is the failure §11 exists to prevent, arrived at from the other direction.
- **Restrict 11.5's first arm to sources whose revision also differs**: Report only a mismatch, so an `assumed` source agreeing on revision passes - Rejected because it deletes the arm's whole purpose. `assumed` means unchecked, not matching; a source that has never been compared has no revision agreement to rest on, and every undeclared source in the corpus would then report as confirmed-by-silence.
- **Exclude a source whose device declares no revision**: Treat the Nitro Max's absent revision marker as nothing to confirm - Rejected because the absence is a property of the *unit*, not of the document. A guide can still describe a different production run of a device that prints no revision, and the report would go quiet on exactly the hardware where the mismatch is hardest to spot by eye.

### Consequences

**Positive:**
- The implementation follows the criteria rather than the worked example, and the divergence is
  recorded where the next reader will look for it.
- No `confirmed` status is ever written by anything other than a person.
- The correct remedy — a one-line declaration after an actual check — stays available and is named in
  `rig.yaml`'s own comments.

**Negative:**
- The live report names two sources where two spec documents say one, until the Nitro Max is checked
  and declared.
- `ui/ask-and-source-picker` marks a second source as assumed in the picker, which is one more mark
  to read past on a four-source corpus.

### Impact

`src/dawmans/corpus/rig.py`, `rig.yaml`, `tests/test_rig.py`; design §Rig inventory and
requirement 11.5, both of which carry a superseded note pointing here.

---

## Decision 17: The run orchestration needs a wider loader protocol than the seam publishes

**Date**: 2026-08-15
**Status**: accepted

### Context

The design's §The loader protocol gives `SourceLoader` two methods: `discover() -> Iterable[Discovered]`
and `load(d) -> LoadResult`. Wiring the run (task 44) found that `discover()` cannot carry two things
the run is required to report.

The first is **rejections**. 1.5 requires a per-run line for every source, including one rejected at
discovery for a malformed filename (2.5) or a source-ID collision (2.6). Those sources never become a
`Discovered` — that is what being rejected at discovery means — so a loader that yields only
`Discovered` has already dropped them by the time it returns.

The second is **availability**. 1.4 removes a source's chunks when its store no longer holds it, and
`discover.py`'s `StoreScan` already draws the distinction the removal rests on: an absent or
unreadable store is an *unknown* discovery set and removes nothing, while an existing empty one
removes its shards. `data/symptom-triage` §The store on disk states the same rule for `triage/`. An
empty `Iterable[Discovered]` cannot tell the two apart, and reading it as "empty" deletes every
passage of an unmounted volume and reports the run as succeeded.

### Decision

`dawmans/cli.py` declares its own `Store` protocol — `scan() -> StoreScan` plus `load()` — and the run
orchestration is written against that. `corpus/loader.py`'s `SourceLoader` is left exactly as the
design states it, with a note pointing here. `PdfLoader` already offers both; `TriageLoader` must
offer `scan()` too.

### Rationale

The protocol a consumer needs belongs with the consumer, and this one has exactly one consumer. Put
in `corpus/loader.py`, `scan()` would also force a circular import — `StoreScan` lives in
`discover.py`, which imports `loader.py` — and the fix for that (a `TYPE_CHECKING` guard, or moving
`StoreScan` down into the seam) would be paying a structural cost to relocate a requirement that has
no second reader.

Leaving `SourceLoader` alone also keeps the published seam honest. It is what `data/symptom-triage`
§Module placement reproduces, and widening it silently would change that spec's obligations in a
document it does not own. Stated in `cli.py`, the extra obligation is visible at the place that
enforces it and is named in both modules' docstrings.

### Alternatives Considered

- **Add `scan()` to `SourceLoader` in `corpus/loader.py`**: One protocol, no duplication - Rejected because it inverts the layering. `StoreScan` is defined in `discover.py`, which already imports `loader.py`, so the seam would import the store layer above it; the circularity is a symptom of the seam being the wrong home, not an inconvenience to route around.
- **Move `StoreScan` and `DiscoveryRejection` down into `loader.py`**: Removes the cycle and gives one protocol - Rejected as the largest change for the smallest gain. It relocates two types that five modules import so that one method can sit somewhere it has no second caller, and `discover.py` — "stage 1 of the run", by its own docstring — is where a discovery set legibly belongs.
- **Keep `discover()` and pass the scan alongside it**: `ingest(vendor_loader, vendor_scan, …)` - Rejected because it lets the two disagree. Nothing would stop a caller passing one store's scan with another store's loader, and the failure would be a silently wrong removal set rather than an error.

### Consequences

**Positive:**
- The seam `data/symptom-triage` implements against is unchanged, and the extra obligation is written
  down in both places rather than implied.
- An unavailable store is distinguishable from an empty one everywhere the run can act on it, which
  is what 1.4 needs and what `StoreScan` was built to say.
- Discovery rejections reach the run report by the same path as every other outcome.

**Negative:**
- Two protocols describe one relationship, and a reader has to find the second to know what a loader
  really has to provide.
- `TriageLoader` carries an obligation stated in this spec's `cli.py` rather than in the design
  section its own spec cites.

### Impact

`src/dawmans/cli.py`, `src/dawmans/corpus/loader.py`, design §The loader protocol.

---

## Decision 18: The rig is joined at the merge, not written into the shard

**Date**: 2026-08-15
**Status**: accepted

### Context

`rig.py` gives `Rig.applied(record)`, which replaces the loader's 11.2 default applicability with
whatever `rig.yaml` declares for that source. The first wiring called it in `_ingest_source`, so the
joined value was written into the shard alongside the passages.

Running that against the real corpus showed it was wrong within one run. `rig.yaml` declares
`focusrite/scarlett-solo-4g -> focusrite/scarlett-solo`, and the run still reported the Scarlett under
indexed-but-not-owned and its device under owned-but-undocumented — the exact diagnostic pairing 11.7
exists to signal a *missing* declaration. The declaration was not missing. Editing `rig.yaml` changes
no byte of any PDF, so every shard's cache key still matched, every shard was reused, no loader ran,
and `Rig.applied` was never reached. The joined value in each shard was the one written the last time
that manual's bytes happened to change.

### Decision

`Rig.applied` runs at the **merge**, over the shards the run is about to commit, and not when a shard
is built. The shard records the loader's own 11.2 default; `views/<hex>/sources.json` and `gaps.json`
carry the joined value.

### Rationale

The split follows what each artefact is a record of. A shard is a cache of what the *document* said,
keyed by the document's bytes — so a value that does not derive from those bytes has no business
being cached under them. `rig.yaml` is what the *owner* says, it is versioned separately, and it is
the input the whole of §11 is a join against. Deriving it at the point the two meet is the only place
where both are current.

It also makes 11.6's consumers correct by construction rather than by luck. `api/answer-engine` and
`ui/ask-and-source-picker` read applicability out of the view, and a declaration added today reaches
them on the next run rather than on the next run that happens to touch a manual.

The cost is one `dataclasses.replace` per source per run, over a list of four.

### Alternatives Considered

- **Fold `rig.yaml`'s digest into the shard cache key**: A rig edit invalidates every shard, so the build-time join stays correct - Rejected because it re-extracts and re-embeds the whole corpus to change a declaration nobody claims is derived from the corpus — ~34 s and a fresh `corpus_revision` for an edit that altered no passage, which would also trip `api/answer-engine` 5.10 into discarding valid cached retrieval state.
- **Apply at build time and again at merge**: Belt and braces - Rejected because two writers of one field is how they come to disagree. The shard's copy would be stale by construction and a reader picking it up would get an answer that was true at some earlier run, which is worse than not having it.
- **Publish `rig.yaml` beside the view and let consumers join it**: The corpus stays out of it - Rejected because CONTRACTS §5 puts the two gap reports on this spec, and a join done in two consumers is a join done two ways. It would also hand `ui/ask-and-source-picker` a file whose grammar this spec owns.

### Consequences

**Positive:**
- A `rig.yaml` edit reaches the index on the next run with no rebuild, which is the case §11 is for.
- The shard means one thing — what the document said — and the view means the other.
- The live corpus now reports what the design predicts: owned-but-undocumented empty and
  indexed-but-not-owned empty, with the Focusrite mapping resolving.

**Negative:**
- `corpus_revision` is hashed over `(source_id, fingerprint, chunk_count)` and so does **not** change
  when only `rig.yaml` changes. A consumer keyed on it alone will not see new applicability until
  something else moves; `manifest.view_dir` does change every run, and that is the signal to use.
- The applicability in `shards/<slug>.meta.json` is not the published one, so a reader debugging from
  a shard has to know to look at the view.

### Impact

`src/dawmans/cli.py`, `tests/test_run.py`, design §Rig inventory and §Index layout.

---

## Decision 19: The cold model load is measured, not assumed, and it is lazy

**Date**: 2026-08-15
**Status**: accepted

### Context

The design's §Build budget states "a one-off 7.2 s model load per process", and the whole of the 8.4
argument rests on it: a new ≤50-page source is ~1.5 s of embedding, so a 7.2 s load takes the total to
8.7 s of the allowed 10 s, which is why the CLI loads the model once per run before iterating sources
and why the design calls 8.4 the tightest budget in the spec.

Writing the timing tests (task 45) measured it. From a cold process to a first vector is **~0.25 s**
on the reference machine, not 7.2 s — the populated cache is `models--qdrant--bge-small-en-v1.5-onnx-q`,
the *quantised* ONNX build. The first draft of the test also passed vacuously for a second reason:
`load_embedder()` constructs `TextEmbedding` and returns, and `fastembed` builds no ONNX session until
something is embedded, so timing the call timed an import.

### Decision

The cold-load test spawns a **fresh process** and measures through to a **first vector**, asserting
against the design's 7.2 s figure rather than against the measured 0.25 s. The design's §Build budget
carries a superseded note recording the measurement. The CLI keeps loading the model once per run.

### Rationale

Asserting the design's number rather than today's is the point. A timing test exists to catch a
regression toward what the design feared, and one pinned to a fresh measurement fails on the first
slower CI runner and teaches everyone to add a zero. 7.2 s is the number 8.4's reasoning was built on,
so it is the number worth defending; the 29× headroom underneath it is reported in the test's comment
where the next person to tighten it will find it.

Measuring to a first vector rather than to a constructed object is not a refinement but the whole
test. A lazy constructor makes "the model is loaded" unobservable at the call site, and the budget
that matters to 8.4 is time-to-first-vector regardless of which line inside the library pays it.

Loading once per run stays correct whatever the constant turns out to be. It is free, it is what makes
the cost a per-*run* one rather than a per-*source* one, and if the cache is ever repopulated with the
unquantised build the design's figure returns without a code change.

### Alternatives Considered

- **Assert the measured 0.25 s with a small margin**: The test then catches any regression at all - Rejected because it makes the suite a machine-speed detector. A cold ONNX load on a shared CI runner varies by more than an order of magnitude, and a test that fails for that reason is one that gets marked flaky and then skipped.
- **Update the design's 7.2 s to 0.25 s and drop the separate assertion**: The documents would agree - Rejected because the figure is cache-dependent, not settled: it is a property of which ONNX build `make fetch-model` happens to populate, and folding a number that can change by 29× back into 8.4's 10 s is exactly the hiding the task set out to prevent.
- **Force the session eagerly inside `load_embedder()`**: Construction would then mean what it says - Rejected as this spec reaching into the library's strategy for a test's convenience. Laziness costs the run nothing — the first source embeds within milliseconds of the load either way — and the seam has no other reason to care.

### Consequences

**Positive:**
- The cold-load budget is asserted against a real load in a real cold process, and cannot pass by
  timing an import.
- 8.4 is measured with the model resident, so the per-source cost is free to regress into a test
  rather than into 7 s of unclaimed headroom.
- The gap between the design's figure and the measurement is written down instead of discovered again.

**Negative:**
- The test spawns a subprocess, which is slower and noisier than an in-process call and will be the
  first thing blamed when the suite is slow.
- The assertion has ~29× headroom on this machine, so it will not catch a load that becomes ten times
  slower and still finishes in 2.5 s.

### Impact

`tests/test_timing.py`, `pyproject.toml` (`-m 'not bench'`), design §Build budget.
