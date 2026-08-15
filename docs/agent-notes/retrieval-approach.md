# Retrieval Approach

Research note for `api/answer-engine`. Covers whether DAWMans needs a vector database, which
local embedding model to use, hybrid retrieval, chunking for citations, the end-to-end latency
budget, and whether to rerank.

All figures marked **(measured)** were benchmarked on this machine — **Apple M5 Pro, 64 GB, macOS
15.6 (Darwin 25.6.0), 2026-08-14** — using `fastembed` 0.8.0 (ONNX Runtime, CPU), `bm25s`, and
NumPy. Benchmark scripts were throwaway; the numbers are reproducible from the method described
in each section. Anything I could not verify is marked **UNVERIFIED**.

---

## Recommendation

- **No vector database. Hold the vectors in a NumPy array and brute-force it.** At the real corpus
  size (~1,000 chunks × 384 dims = **1.8 MB**), a full cosine scan plus top-10 selection measures
  **0.011 ms** (measured). Even at 50,000 chunks — 50× growth — it is 0.68 ms. Every vector store
  on the market is solving a problem this corpus does not have. sqlite-vec, LanceDB, Chroma and
  Qdrant would each add a dependency, a schema and a failure mode to save ~0 ms.
- **Embed with `BAAI/bge-small-en-v1.5` via `fastembed` (ONNX).** 384 dims, 67 MB on disk,
  **2.2 ms** single-query encode (measured) — the only embedding cost in the hot path. Full-corpus
  index build is **~21 s** at 42.4 chunks/s (measured), inside the 60 s budget of requirement 8.1.
  Larger models cost far more for the build and more in the hot path: `nomic-embed-text-v1.5-Q`
  is 10.6 chunks/s (85 s build) and `arctic-embed-m-long` is 8.1 chunks/s (111 s build, and
  11.8 ms per query).
- **Hybrid BM25 + dense, fused with Reciprocal Rank Fusion, is mandatory — not an enhancement.**
  This corpus is wall-to-wall exact strings ("Glue Compressor", "Dry/Wet", "Scene Launch", "MIDI
  note 38") and dense-only retrieval reliably misses them. Anthropic measured adding BM25 to
  contextual embeddings cutting retrieval failures from 3.7% to 2.9%, and hybrid overall taking
  failures from 5.7% to 2.9% — a 49% reduction. BM25 via `bm25s` costs **0.047 ms per query** and
  **0.14 s to index 4,000 chunks** (measured). It is effectively free; there is no argument
  against it.
- **Cap chunks at ~350 words, not the 500 words in the corpus spec (requirement 6.7).** A 500-word
  chunk tokenises to **601 tokens** (measured, BGE tokenizer), which overflows bge-small's 512-token
  window and gets **silently truncated** — the tail of every maximal chunk would be invisible to
  dense retrieval while still appearing in BM25 and in the cited text. 350 words ≈ 420 tokens,
  leaves room for the header prefix, and embeds 31% faster. This is a spec-level implication worth
  raising against `specs/data/manual-corpus`.
- **Prefix every chunk with its citation header** (`Ableton Live 12 — §24.9 Glue Compressor`)
  before both embedding and BM25 indexing. It costs ~15 tokens, disambiguates chunks that are
  otherwise near-identical across devices, and puts the exact product and section strings into the
  lexical index where users' verbatim queries will hit them. It is most of the benefit of
  Anthropic's contextual retrieval at none of the LLM cost.
- **Skip the cross-encoder reranker.** Measured on this machine, `ms-marco-MiniLM-L-6-v2` costs
  **236 ms** to rerank 20 candidates and `bge-reranker-base` costs **879 ms**. Retrieval currently
  costs ~4 ms end to end. Reranking would make the retrieval stage **60× to 200× slower** to chase
  a 2.9% → 1.9% failure-rate improvement measured on a corpus far larger and messier than this one.
  Revisit only if evaluation shows real recall failures at k=10.
- **Retrieval is ~4 ms of a ~1,500 ms answer. The LLM is the entire latency story.** The one
  retrieval-side lever that actually moves wall-clock time is *sending fewer context tokens*,
  because time-to-first-token scales linearly with prompt length. Send k=8–12 chunks of 350 words
  (~4–5k tokens), not k=20 of 500 words (~13k tokens).
- **Use a hosted model for synthesis; keep retrieval local.** This satisfies the AGENTS.md
  local/FOSS preference where it counts (the index never leaves the machine, ingestion is offline
  per requirement 8.5) while keeping the answer fast. A local 8B model on this hardware is
  prefill-bound on a multi-thousand-token RAG prompt and is unlikely to hit the "glance at a second
  screen" bar.

**Concrete stack:** `pdftotext -layout` → section-aware chunker → `fastembed`/`bge-small-en-v1.5`
→ `vectors.npy` (float32, L2-normalised) + `chunks.jsonl` + a saved `bm25s` index → NumPy dot
product and `bm25s.retrieve` in parallel → RRF → top-10 into the prompt.

---

## 1. Does this corpus need a vector database?

**No, and it is not close.**

### The corpus is smaller than the brief assumed

The brief estimated 2,000–4,000 chunks. Working from the measured corpus (~250,000 words) and the
recommended 350-word chunk with ~15% overlap (~300 net new words per chunk), the real figure is
closer to **800–1,200 chunks**. At 500 words per chunk it would be **500–700**. Either way the
index is an order of magnitude smaller than a rounding error for any vector search library.

Storage at 384 dims, float32: **1,200 × 384 × 4 = 1.84 MB.** The entire index fits in L2/L3 cache
territory and loads from disk instantly at startup.

### Measured brute-force search latency

NumPy `float32` matrix–vector product over L2-normalised embeddings, plus `argpartition` for
top-10. Median of 200 trials, M5 Pro:

| Chunks | d=384 | d=768 | d=1024 | Memory (d=384) |
|--------|-------|-------|--------|----------------|
| 2,000  | **0.011 ms** | 0.015 ms | 0.025 ms | 3.1 MB |
| 4,000  | **0.023 ms** | 0.057 ms | 0.095 ms | 6.1 MB |
| 10,000 | 0.093 ms | 0.217 ms | 0.348 ms | 15.4 MB |
| 50,000 | 0.682 ms | 1.318 ms | 1.730 ms | 76.8 MB |

At the actual corpus size the search is **~0.01 ms**. The query embedding that precedes it costs
2.2 ms — **200× more**. Search is not merely fast enough; it is invisible next to the step that
feeds it.

The whole implementation is this:

```python
# vectors: (n, 384) float32, L2-normalised at build time
scores = vectors @ query_vec          # query_vec also L2-normalised → cosine
top = np.argpartition(-scores, k)[:k]
top = top[np.argsort(-scores[top])]
```

### Comparison against the alternatives

| Option | Verdict at this scale |
|--------|----------------------|
| **NumPy array (recommended)** | 0.01 ms. Zero dependencies beyond NumPy. Index is one `.npy` file. Trivially rebuildable, trivially debuggable. |
| **sqlite-vec** | Also exact brute-force by default; its own docs position it for "thousands to low-millions" of vectors. Genuinely good, and the right answer if metadata filtering in SQL were needed. Here it adds an extension to load and a schema for no measurable gain. |
| **SQLite FTS5** | Worth considering *for the BM25 half* — it is built in and implements BM25 natively. `bm25s` measured 0.047 ms/query and 0.14 s to index; FTS5 would be comparable. I prefer `bm25s` because it keeps the whole index as plain files rebuilt in one pass, matching requirement 8.6, and avoids tokenizer/stemmer configuration in SQL. This is a close call, not a strong preference. |
| **LanceDB** | Columnar on-disk format, ANN indexing, versioning. All of it is machinery for datasets that do not fit in memory. This one is 1.8 MB. |
| **Chroma** | Adds a server process or an embedded DB plus its own embedding-function abstraction. Pure overhead here. |
| **Qdrant** | A network service with HNSW indexing. The network hop alone would cost more than the entire brute-force search by two orders of magnitude. |

### On over-engineering

The one published comparison I found reports sqlite-vec at 17 ms versus NumPy at 136 ms for k=20
on SIFT1M — **one million** 128-dim vectors on an M1 Mini. That result is real and it is
irrelevant: it is a corpus roughly 1,000× larger than this one, where the linear scan finally
costs something. Extrapolating from it to a 1,000-chunk corpus would be a mistake. My own
measurement at the actual scale supersedes it.

ANN indexing (HNSW, IVF) is a technique for trading recall away to avoid an expensive exhaustive
scan. Here the exhaustive scan costs 0.01 ms and is exact. Approximating it would sacrifice
correctness to optimise a quantity that is already below measurement noise.

**The honest summary: a vector database here is a dependency, a config surface and an operational
concern purchased in exchange for nothing.** Choose it only if a future requirement demands
something the array cannot do — and note that even 50× corpus growth does not qualify.

---

## 2. Local embedding models

All measured with `fastembed` 0.8.0 (ONNX Runtime, CPU provider, default threading), M5 Pro,
2026-08-14. "Query" is a single short question encoded alone — the hot-path number. "chunks/s" is
batched throughput on realistic 500-word manual text.

| Model | Dims | Disk | Query p50 | chunks/s | Build (~900 chunks) |
|-------|------|------|-----------|----------|---------------------|
| **`BAAI/bge-small-en-v1.5`** | 384 | 67 MB | **2.2 ms** | 32.3 (500w) / **42.4 (350w)** | **28 s / 21 s** |
| `snowflake/snowflake-arctic-embed-s` | 384 | 130 MB | 2.3 ms | 30.4 | 30 s |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | 90 MB | 4.8 ms | 304.8 | 3 s |
| `nomic-ai/nomic-embed-text-v1.5-Q` | 768 | 130 MB | 3.5 ms | 10.6 | 85 s |
| `snowflake/snowflake-arctic-embed-m-long` | 768 | 540 MB | 11.8 ms | 8.1 | 111 s |
| `BAAI/bge-base-en-v1.5` | 768 | 210 MB | 5.6 ms | 45.6 (short text) | — |

### Why bge-small

- **The query encode is the hot path, and 2.2 ms is the joint-best measured.** Everything downstream
  of it is faster; everything upstream is I/O.
- **The build fits the budget.** Requirement 8.1 caps a full rebuild at 60 s. At 350-word chunks the
  embedding stage is ~21 s, leaving ~39 s for extraction (measured at 0.7 s), language selection and
  chunking. `nomic-embed-text-v1.5-Q` at 85 s and `arctic-embed-m-long` at 111 s **both breach 8.1 on
  the embedding stage alone.**
- **384 dims halves the memory and the search cost** versus 768, and at this corpus size the search
  cost is already nil — so the dimension choice is really about build time and RAM, both of which
  favour the smaller model.
- **English-only is fine.** Requirement 4.1 indexes English content exclusively, so the multilingual
  capability of EmbeddingGemma, Qwen3-Embedding and BGE-M3 is dead weight.

### The models I rejected and why

- **`all-MiniLM-L6-v2`** is 7× faster to build (304 chunks/s) and tempting, but its context window
  is **256 tokens** — barely half a 350-word chunk. It would truncate roughly half of every chunk.
  Its retrieval quality is also the oldest and weakest of the shortlist. Speed on the build stage
  is not a constraint worth paying quality for when the build already fits in budget.
- **`nomic-embed-text-v1.5`** has a genuine advantage: an **8,192-token context** and Matryoshka
  dimensions (768 → 64 with MTEB dropping only 62.28 → 56.10). If chunking moved to whole-section
  chunks of several thousand tokens, this would become the right model. At 350-word chunks the long
  context is unused and the 8× build-time penalty buys nothing.
- **`EmbeddingGemma-300M`** (308M params, <200 MB RAM quantised, 2,048-token context, strong MTEB
  for its size) is the most interesting recent option and is available as ONNX on Hugging Face.
  **It is not in `fastembed`'s model list** (verified 2026-08-14), so it would need direct ONNX
  Runtime or `sentence-transformers` wiring. **Its Apple Silicon throughput is UNVERIFIED** — the
  only published latency figure I found is "<15 ms for 256 input tokens on EdgeTPU", which does not
  transfer. Worth benchmarking if retrieval quality ever proves inadequate; not worth the
  integration cost up front.
- **`bge-reranker`-class and 1024-dim models** (`mxbai-embed-large`, `arctic-embed-l`,
  `jina-embeddings-v3` at 2.29 GB) are all disproportionate to a 1.8 MB index.

### Encode-time notes

- **Query and document prefixes matter.** BGE models expect a query instruction prefix
  (`"Represent this sentence for searching relevant passages: "`) on the *query* only, not on
  documents. Omitting it costs measurable retrieval quality. `fastembed` handles this if the query
  is embedded via the query API rather than the document API — worth an explicit test.
- **Warm the model at server start.** Model load plus first inference measured **7.2 s** for
  bge-small. That must happen at process startup, never on the first user query.
- **MLX** is the fastest Apple Silicon runtime generally, but for a 33M-parameter encoder at
  batch size 1 the ONNX CPU path is already at 2.2 ms and dominated by fixed overhead. An MLX port
  is unlikely to repay the effort. **UNVERIFIED** — not benchmarked.

---

## 3. Hybrid retrieval

**Pure dense retrieval will fail on this corpus, and the failures will be the queries the user
most expects to work.**

### Why dense-only breaks here

Home-studio questions are dense with exact strings the user reads off a screen or a piece of
hardware and types verbatim:

- **Device names** — "Glue Compressor", "Utility", "Auto Filter". "Utility" is the pathological
  case: a common English word that is also a specific Live device. A dense model embeds it near
  "usefulness", "helper", "tool".
- **Parameter names** — "Dry/Wet", "Threshold", "Makeup", "Range". These recur in *dozens* of
  devices; the embedding of "Threshold" is near-identical everywhere it appears, so dense retrieval
  cannot discriminate which device's Threshold is meant without the header prefix.
- **Button and control names** — "Scene Launch", "Rec Arm", "Shift", "Track Select". Short,
  compound, hardware-specific.
- **Numbers and identifiers** — "MIDI note 38", "CC 74", "channel 10". Dense embeddings notoriously
  fail on numerics: 38 and 39 embed almost identically, and the *correct* answer differs completely.
  For the Nitro Max MIDI note table this is not a marginal case, it is the primary use case.

The mechanism is well documented: dense models collapse lexically distinct but semantically similar
tokens into nearby vectors, so rare identifiers and exact technical terms lose the very
distinctiveness that makes them searchable. Anthropic's write-up names precisely this failure —
their example is an error code "TS-999" — and concludes that BM25 is required for "queries that
include unique identifiers or technical terms".

BM25, conversely, cannot handle "how do I make a sound quieter over time" → *fade / volume
automation*. Neither method is sufficient alone. This is the textbook case for hybrid.

### Measured evidence

Anthropic's contextual retrieval experiments, measured as 1 − recall@20 (published 2024-09-19):

| Configuration | Failure rate | Reduction |
|---|---|---|
| Embeddings only | 5.7% | baseline |
| Contextual embeddings | 3.7% | 35% |
| Contextual embeddings + contextual BM25 | **2.9%** | **49%** |
| + reranking | 1.9% | 67% |

Adding BM25 to the dense retriever removed roughly a fifth of the remaining failures. On a corpus
as identifier-dense as gear manuals, I expect the benefit to be **larger** than these general-purpose
figures suggest.

### Recommended fusion: Reciprocal Rank Fusion, k=60

Run both retrievers to depth 50, then fuse:

```python
def rrf(dense_ids, bm25_ids, k=60):
    scores = defaultdict(float)
    for rank, cid in enumerate(dense_ids):
        scores[cid] += 1.0 / (k + rank + 1)
    for rank, cid in enumerate(bm25_ids):
        scores[cid] += 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)
```

**Why RRF rather than weighted score blending:**

- **It needs no score normalisation.** BM25 scores are unbounded and corpus-dependent; cosine
  similarities sit in [-1, 1] and cluster tightly in a narrow band. Blending them requires
  min-max or z-score normalisation whose parameters drift every time a manual is added. RRF
  consumes only *ranks*, so it is immune to this entirely — a real robustness win for a corpus
  that grows by hand-dropping PDFs into a folder.
- **It has one parameter and the default works.** k=60 comes from the original Cormack et al.
  formulation and is the default in Weaviate, Elasticsearch and Qdrant. Larger k flattens the
  contribution of top ranks; there is no tuning data here to justify departing from 60.
- **It degrades gracefully.** A chunk found by only one retriever still scores; a chunk found by
  both is boosted. That is exactly the desired behaviour when "Threshold" hits lexically and
  "make it quieter when it gets loud" hits semantically.
- **It costs nothing** — two 50-element loops over a dict, well under 0.5 ms.

The one weakness of RRF is that it discards score *magnitude*, so a runaway-best lexical match is
treated the same as a merely-good one. Given both retrievers here are cheap and the candidate pool
is fed to an LLM that does its own selection, this does not matter.

**BM25 implementation:** `bm25s` with a PyStemmer English stemmer. Measured: **0.14 s to index
4,000 chunks**, query **p50 0.047 ms / p95 0.056 ms**. It stores eagerly-computed scores in SciPy
sparse matrices, which is why it is orders of magnitude faster than `rank_bm25`. Do **not** use
`rank_bm25` — it scores at query time and is the slow option even at this scale.

One tokenisation caveat: the default stemmer/tokeniser must not destroy the strings that matter.
Verify that "Dry/Wet" survives as something matchable, that "TS-999"-style identifiers are not
split, and that bare numerals ("38") are retained rather than dropped as stopword-like noise.
This is a real source of silent BM25 failure and is worth an explicit test.

### The caveat came true — index and query tokenisers diverged (fixed)

They were two different functions, and only the index side got the custom one:

- **Index** (`index/lexical.py::tokenise`) — a custom regex over `[a-z0-9]` runs joined by
  `-/._`, emitting each compound **whole followed by its parts**.
- **Query** (`answer/retrieve.py::tokenize_query`) — `bm25s.tokenize(..., stopwords=None)`,
  bm25s's default splitter, which emitted **the parts only** and dropped single characters.

Measured before the repair:

| Input | Index tokens | Query tokens |
|---|---|---|
| `Dry/Wet` | `dry/wet`, `dry`, `wet` | `dry`, `wet` |
| `4th-gen` | `4th-gen`, `4th`, `gen` | `4th`, `gen` |
| `bge-small-en-v1.5` | whole + `bge`, `small`, `en`, `v1`, `5` | `bge`, `small`, `en`, `v1` |
| `track 3` | `track`, `3` | `track` |

So every compound in the vocabulary was indexed and unreachable — the exact-match half of
`data/manual-corpus` 8.8, the reason the custom tokeniser exists at all — and bare numerals were
dropped by the two-word-character minimum in bm25s's default pattern. `tokenise`'s own docstring
asserts "a query goes through this same function"; it did not.

It cost ranking signal rather than results (the fragments still matched, and dense retrieval was
untouched), which is why nothing caught it: parity was asserted only over in-memory fixtures that
tokenise both sides with the same function, so no test could see the two sides drift.

**The fix**: `tokenize_query` now calls `dawmans.index.lexical.tokenise`. Importing the index module
from the answer side is safe in a serve-only environment — `lexical.py`'s one dependency is `bm25s`,
which `serve` already installs — and it is the right direction, because the corpus owns the rule that
produced its vocabulary. A second implementation on the query side is the drift itself.

`tests/answer/test_lexical_parity.py` is the guard: it asserts the two callables agree on the same
text, that each of 8.8's shapes survives whole *and* in parts, that a bare numeral survives, and that
neither side applies a stopword list. Replayed against the old implementation it fails 10 assertions,
so it is a regression test and not a tautology.

**What it moved**, measured with `make bench-retrieval` over the real 1,436-passage index, before and
after: 6 of 10 questions changed their supplied set, all of them compound- or numeral-bearing; the
prose controls did not move. Latency was unaffected — median 1.10 → 1.06 ms, p95 1.51 → 1.47 ms,
against 4.2's 10 ms / 50 ms. The change is a ranking change, not a cost.

A note on what came back with it: `tokenise` has no stopword list, so `a` and `i` are now query terms
where bm25s's two-character minimum had silently dropped them. That is the intended behaviour on both
sides (Decision 2 — a list holding `on` but not `off` is worse than no list), and a term appearing in
nearly every passage carries almost no IDF weight, so it costs nothing measurable. Parity is the
property; the stopword decision belongs to `tokenise` and is made once, there.

---

## 4. Chunking for citable manuals

The corpus spec (`specs/data/manual-corpus/requirements.md` §6, §7) already constrains this well:
one section per chunk (6.5), section identity and page range on every chunk (6.1, 6.2), no split
procedures (6.8), no split table rows (7.4), headings repeated across table splits (7.5). The
retrieval-side additions are:

### Chunk size: ~350 words, not 500

**This contradicts requirement 6.7 and I think 6.7 should change.** A 500-word chunk measures
**601 tokens** with the BGE tokenizer (measured). bge-small's window is **512 tokens**. The
overflow is not an error — it is a **silent truncation**, so the last ~90 words of every maximal
chunk would never reach the embedding while still being present in the BM25 index and in the text
shown to the user. That is a quiet, hard-to-notice retrieval hole.

350 words ≈ 420 tokens, which leaves ~90 tokens of headroom for the header prefix and tokeniser
variance. It also embeds **31% faster** (42.4 vs 32.3 chunks/s measured), pulling the build from
28 s to 21 s. And 6.7's stated rationale — "short enough for a person to check against the page" —
is better served by 350 words than 500 anyway.

If 500-word chunks are wanted for citation reasons, the alternative is a longer-context model,
which costs 4–8× the build time (§2). Shrinking the chunk is the cheaper fix.

### Overlap: ~15%, sentence-aligned

Roughly 50 words, snapped to a sentence boundary. Overlap exists to stop an answer being severed
mid-explanation. Keep it modest: overlap inflates chunk count, build time and duplicate hits in the
result list. Do **not** overlap across a section boundary — 6.5 forbids a chunk spanning two
sections, and the citation would be ambiguous.

### Header prefix in every chunk — do this

Prepend the citation path to the chunk text **before both embedding and BM25 indexing**:

```
Ableton Live 12 — §24.9 Glue Compressor
Threshold sets the level at which compression begins. Ratio determines...
```

Three distinct benefits:

1. **It disambiguates repeated parameter names.** Without it, the "Threshold" paragraph in Glue
   Compressor, Compressor, Gate and Auto Filter produce near-identical embeddings and the retriever
   cannot tell them apart. With it, a query naming the device pulls the right one.
2. **It puts exact product and section strings into the lexical index**, which is where verbatim
   user queries land.
3. **It is cheap contextual retrieval.** Anthropic's technique prepends an LLM-generated 50–100
   token context to each chunk and measured a 35% failure reduction from that alone. A
   deterministic header derived from the TOC captures a large share of that benefit at zero LLM
   cost, zero build time and no risk of hallucinated context. Given the manuals have real numbered
   TOCs with page numbers, the structural header is arguably *better* than a generated one.

Cost: ~15 tokens per chunk, ~4% of the window. Trivially worth it.

### Citation metadata

Carry as chunk fields, never as parsed-out-of-text: `source_id`, `product`, `doc_version`,
`section_number`, `section_title`, `page_start`, `page_end`, `chunk_index`, plus the `degraded`
flag from requirement 5.3. Because the TOC provides section *and* page numbers, page attribution
should come from mapping extracted text back to its physical page during extraction — not inferred
from the TOC's section-start pages, which would mis-attribute anything past the first page of a
long section. Requirement 6.9 (validate page numbers fall in range) catches gross errors but not
this off-by-a-few class of mistake.

### Keeping the Nitro Max MIDI note table intact

The table is the sharpest test in the corpus, because a row split is not a degraded answer — it is
a **wrong MIDI note number**, silently.

- **Detect table regions before chunking, and treat each as an atomic unit** the generic
  section-splitter is not allowed to cut. The two-column layout of this table means naive
  extraction interleaves columns; `pdftotext -layout` preserves it, which the corpus spec already
  relies on.
- **Never split between a row's cells.** If the table exceeds the chunk size, split **between
  rows** and **repeat the column headers** in each part (requirement 7.5). A headerless fragment of
  note numbers is uninterpretable to both the retriever and the LLM.
- **Serialise rows so each is self-describing.** A row rendered as `Snare Head | 38 | Note 38`
  survives retrieval better than whitespace-aligned columns, because BM25 tokenises it cleanly and
  the LLM cannot mis-associate a value with the wrong row. Preserving the visual alignment is not
  the goal; preserving the *association* is (requirement 7.1).
- **Keep the table's section header prefix on every part**, so "what note is the snare on the Nitro
  Max" matches lexically on both the product and the row.
- Because BM25 handles bare numerals better than any dense model, this table is the strongest
  single argument for the hybrid design in §3.

---

## 5. Latency budget

Assumptions: k=10 chunks of ~350 words retrieved into the prompt (~4,600 tokens of context), a
~600-token system prompt, and a ~150-token answer. Retrieval figures are measured on this machine;
LLM figures are from published benchmarks and are marked accordingly.

| Stage | Local retrieval + hosted LLM | Local retrieval + local LLM | Source |
|---|---|---|---|
| Query embed (bge-small, ONNX) | **2.2 ms** | 2.2 ms | measured |
| Dense search (1,200 × 384 brute force) | **0.01 ms** | 0.01 ms | measured |
| BM25 search (`bm25s`) | **0.05 ms** | 0.05 ms | measured |
| RRF fusion + dedupe | <0.5 ms | <0.5 ms | estimate |
| Prompt assembly | ~1 ms | ~1 ms | estimate |
| **Retrieval subtotal** | **~4 ms** | **~4 ms** | |
| Network round trip | 30–60 ms | 0 ms | estimate |
| LLM time-to-first-token | **400–900 ms** | **2,000–8,000 ms** | published / UNVERIFIED |
| Answer decode (150 tokens) | 850–1,500 ms | 1,400–2,500 ms | published |
| **First token on screen** | **~0.45–0.95 s** | **~2–8 s** | |
| **Complete answer** | **~1.3–2.5 s** | **~3.5–10 s** | |

### Which stage dominates

**The LLM, by a factor of roughly 250.** Retrieval is ~4 ms of a ~1,500 ms answer — **0.3% of the
budget**. Any effort spent making retrieval faster is wasted; the array-scan design is chosen not
because it is fastest but because it is *simplest*, and it happens to also be fastest.

### The one retrieval-side lever that matters

Prefill is compute-bound and **TTFT scales linearly with prompt length** — 10,000 input tokens
take roughly 10× as long as 1,000. So the retrieval subsystem's real contribution to latency is
**how many context tokens it emits**, not how fast it selects them.

This inverts the usual instinct. Retrieving k=20 chunks of 500 words (~13,000 tokens) instead of
k=10 of 350 words (~4,600 tokens) costs perhaps 0.02 ms more in search and **several hundred
milliseconds more in TTFT**. Anthropic found k=20 most performant for recall, but that was
optimising recall, not latency, on a much larger corpus. Here, with a small corpus and a strong
hybrid retriever, **k=10 is the right trade** — and it is the single highest-leverage speed
decision in the whole design.

Secondary levers, both real:

- **Stream the response.** "Fast" for a glance-at-a-second-screen use case is time-to-*first*-token,
  not time-to-complete. Streaming turns a 2 s wait into a 0.5 s wait perceptually.
- **Cache the static system prompt.** The instructions and citation format never change; prompt
  caching removes them from prefill on every request after the first.

### What "fast" realistically means here

- **Achievable: first words appearing in ~0.5–1.0 s, complete answer in ~1.5–2.5 s, with a hosted
  model.** That meets the brief.
- **Not achievable: a sub-second complete answer.** Decoding 150 tokens takes ~1 s at the best
  hosted rates. The only way below that is a shorter answer.
- **Local synthesis is the risk.** A dense 7–8B model on Apple Silicon must prefill ~5,000 tokens
  before emitting anything, and prefill is where local hardware is weakest. Published M5-family
  prefill figures range widely (Apple reports M5 at 3.3–4.1× M4's TTFT; one source cites ~350–450
  tok/s for 4K prompts on M5 Max, another cites 1,810 tok/s for a sparse MoE model). **I could not
  find a figure for M5 Pro specifically — UNVERIFIED.** The spread across those sources is wide
  enough that local TTFT could be anywhere from 2 s to 8 s, and the low end is not confidently
  reachable. Hence: hosted for synthesis.

This is consistent with the brief and with AGENTS.md. Retrieval — the part that touches the manual
corpus and would otherwise leak it — stays entirely local and offline (requirement 8.5). Only the
question and the retrieved excerpts go to the model.

---

## 6. Reranking

**Do not build it. It is a premature optimisation here, and an expensive one.**

Measured on this machine, `fastembed` cross-encoders, ONNX CPU:

| Reranker | k=10 | k=20 | k=50 |
|---|---|---|---|
| `Xenova/ms-marco-MiniLM-L-6-v2` | 122 ms | **236 ms** | 493 ms |
| `BAAI/bge-reranker-base` | 473 ms | **879 ms** | 2,036 ms |

### The argument

- **The cost is 60–200× the entire retrieval stage.** Retrieval is ~4 ms. Reranking 20 candidates
  adds 236 ms (MiniLM) or 879 ms (BGE). Against a 450–950 ms time-to-first-token, the BGE reranker
  would roughly **double** the perceived wait. That is a large, certain, user-visible cost.
- **The benefit is small and uncertain here.** Anthropic measured reranking taking failures from
  2.9% to 1.9% — real, but on a corpus far larger and more heterogeneous than three gear manuals.
  Reranking earns its keep when the first-stage retriever must discriminate among thousands of
  plausible candidates. Over ~1,000 chunks drawn from three documents about distinct devices, a
  hybrid retriever with citation headers should already put the right chunk in the top 10.
- **The LLM is already a reranker.** k=10 chunks (~4,600 tokens) sits comfortably in any modern
  context window, and the model selects and cites from them. Paying 236–879 ms for a cross-encoder
  to reorder a list the LLM will read in full anyway is largely redundant. Reranking pays off
  mainly when it lets you *cut* k — but the prefill saving from k=20→k=5 is smaller than the
  rerank cost that bought it.
- **Off-the-shelf rerankers can actively hurt on technical corpora.** One reported study found
  stock cross-encoders (`ms-marco-MiniLM`, `bge-reranker-base`) *degrading* NDCG by 0.3–3.1% while
  adding 560–2,100 ms on technical and scientific corpora, because the models were not trained on
  that domain. Gear manuals — full of product names, parameter jargon and MIDI numbers — are
  exactly that kind of out-of-distribution corpus. The downside is not merely "wasted latency", it
  is "wasted latency and worse results".

### The condition that would change my mind

Build a small evaluation set first — 30–50 real questions with the correct section hand-labelled —
and measure recall@10 of the hybrid retriever. **If recall@10 exceeds ~95%, reranking has almost
nothing left to fix and should not be built.** If it lands materially lower, diagnose the cause
before reaching for a reranker: at this corpus size the likely culprits are chunking or
tokenisation (a table split, a lost "Dry/Wet" token, a missing header prefix), and fixing those is
free at query time whereas reranking is a permanent 236 ms tax on every question.

If reranking is ever genuinely needed, use `ms-marco-MiniLM-L-6-v2` over `bge-reranker-base`
(236 ms vs 879 ms at k=20) and rerank at most 20 candidates.

---

## Open questions

- **Retrieval quality is unmeasured.** Every quality claim above is reasoned from published
  benchmarks on other corpora. The evaluation set described in §6 is the prerequisite for any
  further tuning, and should probably exist before the retriever is considered done.
- **BGE query-prefix handling in `fastembed`** needs an explicit check — whether the query
  instruction prefix is applied, and whether it measurably changes results on this corpus.
- **BM25 tokenisation of "Dry/Wet", "TS-999"-style identifiers and bare numerals** needs a direct
  test; silent loss here would undermine the main justification for hybrid retrieval.
- **EmbeddingGemma-300M on Apple Silicon** is unbenchmarked (UNVERIFIED) and is the most plausible
  quality upgrade if bge-small proves insufficient.
- **Local LLM prefill throughput on M5 Pro** is UNVERIFIED; the published range is too wide to plan
  against. If local synthesis becomes a requirement, measure it before committing.

---

## Sources

All accessed 2026-08-14.

**Vector search and storage**
- Alex Garcia, *Introducing sqlite-vec v0.1.0* (2024) — https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html
- *Comparison of sqlite-vec and pgvector*, Grokipedia — https://grokipedia.com/page/Comparison_of_sqlite-vec_and_pgvector (source of the SIFT1M 17 ms / 136 ms figures; secondary source, treat with caution)
- *What Is sqlite-vec? Vector Search in SQLite* — https://ai-tldr.dev/learn/embeddings-vector-databases/vector-database-guides/sqlite-vec-explained/

**Embedding models**
- `nomic-ai/nomic-embed-text-v1.5` model card (MTEB 62.28; Matryoshka table) — https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
- Nussbaum et al., *Nomic Embed: Training a Reproducible Long Context Text Embedder* — https://arxiv.org/pdf/2402.01613
- Google Developers Blog, *Introducing EmbeddingGemma* (2025-09) — https://developers.googleblog.com/en/introducing-embeddinggemma/
- EmbeddingGemma model overview — https://ai.google.dev/gemma/docs/embeddinggemma
- `onnx-community/embeddinggemma-300m-ONNX` — https://huggingface.co/onnx-community/embeddinggemma-300m-ONNX
- Snowflake, *Introducing Snowflake Arctic-Embed* — https://www.snowflake.com/en/engineering-blog/introducing-snowflake-arctic-embed-snowflakes-state-of-the-art-text-embedding-family-of-models/
- Merrick et al., *Arctic-Embed* — https://arxiv.org/html/2405.05374v1
- Milvus, *Best Embedding Model for RAG 2026* — https://milvus.io/blog/choose-embedding-model-rag-2026.md
- BentoML, *The Best Open-Source Embedding Models in 2026* — https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models

**Hybrid retrieval and fusion**
- Anthropic, *Contextual Retrieval in AI Systems* (published 2024-09-19) — https://www.anthropic.com/engineering/contextual-retrieval
- Weaviate, *Hybrid Search Explained* — https://weaviate.io/blog/hybrid-search-explained
- Qdrant, *Implementing a Hybrid Search System* — https://qdrant.tech/course/essentials/day-3/hybrid-search-demo/
- *Reciprocal Rank Fusion: the one-line algorithm behind hybrid search* — https://blog.serghei.pl/posts/reciprocal-rank-fusion-explained/
- *Hybrid Search: BM25, Vector & Reranking Reference 2026* — https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026

**BM25 implementations**
- `bm25s` project — https://bm25s.github.io/ and https://github.com/xhluca/bm25s
- Lù, *BM25 for Python: Achieving high performance while simplifying dependencies with BM25S* — https://huggingface.co/blog/xhluca/bm25s
- SQLite FTS5 / BM25 notes — https://deepwiki.com/gwicho38/legal-workspace-mcp/3.2.1-sqlite-fts5-and-bm25

**Chunking**
- Firecrawl, *Best Chunking Strategies for RAG (and LLMs) in 2026* — https://www.firecrawl.dev/blog/best-chunking-strategies-rag
- Databricks, *The Ultimate Guide to Chunking Strategies for RAG Applications* — https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089
- *Vision-Guided Chunking Is All You Need* — https://arxiv.org/html/2506.16035v2
- Atlan, *Chunking Strategies for RAG: Methods, Trade-offs & Best Practices* — https://atlan.com/know/chunking-strategies-rag/

**Latency**
- ClickHouse, *LLM inference latency: TTFT, tokens per second, and what to measure* — https://clickhouse.com/resources/engineering/llm-inference-latency
- WEKA, *Prefill vs Decode in LLM Inference* — https://www.weka.io/learn/ai-ml/prefill-and-decode/
- *AI Model Latency Benchmarks 2026: TTFT & TPS Data* — https://www.digitalapplied.com/blog/ai-model-latency-benchmarks-2026-ttft-throughput
- *Fastest LLM API in 2026: Gemini vs OpenAI vs Claude Latency* — https://www.kunalganglani.com/blog/llm-api-latency-benchmarks-2026
- *Apple MLX in 2026: A Developer Guide to Local AI on Mac* — https://www.digitalapplied.com/blog/apple-mlx-framework-local-ai-developers-2026-guide
- *Apple Silicon LLM Benchmarks 2026 — Tokens per Second by Model & Chip* — https://llmcheck.net/benchmarks

**Reranking**
- Zilliz, *The guide to bge-reranker-base* — https://zilliz.com/ai-models/bge-reranker-base
- Towards Data Science, *Rerankers Aren't Magic Either: When the Cross-Encoder Layer Is Worth the Cost* — https://towardsdatascience.com/rerankers-arent-magic-either-when-the-cross-encoder-layer-is-worth-the-cost-enterprise-document-intelligence-vol-1-2bis/
- *Reranker Benchmark: Top 8 Models Compared* — https://aimultiple.com/rerankers
