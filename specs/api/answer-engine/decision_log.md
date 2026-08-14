# Decision Log: Answer Engine

## Decision 1: Reciprocal Rank Fusion at k=10, not k=60 and not weighted score blending

**Date**: 2026-08-14
**Status**: accepted

### Context

`data/manual-corpus` builds a dense index and a `bm25s` lexical index over the same passage ordering
and deliberately hands fusion to this spec (its Decision 2), with a caveat rather than a value: at
the conventional RRF k=60, a chunk both retrievers rank mediocrely beats a verbatim lexical rank-1
match that dense retrieval misses entirely. That is the "MIDI note 38" case — the primary use case
for the Nitro Max trigger table, not a marginal one — and it is the case hybrid retrieval exists to
serve.

The corpus design also passed on weighted score blending without rejecting it, correcting the common
objection: per-query min-max normalisation stores nothing between queries, so there is no parameter
to drift. The honest objection it named is outlier fragility.

### Decision

Fuse with Reciprocal Rank Fusion, `score(c) = Σ 1/(k + rank(c))` over 1-based ranks, **k = 10**,
each retriever run to depth 50. No separate lexical floor, no reranker.

### Rationale

RRF's decisiveness is governed by one inequality. A sole rank-1 hit beats a double hit at symmetric
ranks (r, r) exactly when

```
1/(k+1) > 2/(k+r)   ⟺   r > k + 2
```

At k=60 that requires r > 62, and both retrievers run to depth 50 — so **within the candidate pool a
sole rank-1 can never outrank any double hit**. The asymmetric instance from the corpus caveat:
sole BM25 rank-1 scores 1/61 = 0.0164 while a (dense 10, BM25 20) chunk scores 1/70 + 1/80 = 0.0268
and wins by 63%.

At k=10 the threshold falls to r > 12, and the same instance reverses: 1/11 = 0.0909 against
1/20 + 1/30 = 0.0833. k=12 reverses it by 0.3% and k=15 does not reverse it at all, so k=10 is
roughly the largest value that carries margin.

**Weighted blending with per-query min-max fails the same case, for a reason RRF does not have.**
Worked on realistic figures: bge-small cosines over depth-50 candidates on a topical corpus span a
narrow band — say 0.38 to 0.62. Min-max stretches that 0.24-wide band across [0, 1], so a 0.02
cosine difference becomes 0.083 of normalised score. The correct trigger row, which dense retrieval
is blind to, sits at cosine 0.40 → 0.083 normalised, with BM25 top score → 1.0; at α = 0.5 it scores
0.542. A consensus chunk at cosine 0.58 → 0.833 and BM25 8.7 of a 4.0–14.2 span → 0.461 scores
0.647 and still wins. The right row only wins below α ≈ 0.418 — a value obtainable solely by fitting
to this example, and no evaluation set exists to fit against. Min-max on a narrow cosine band
converts dense noise into dense signal, which is a worse failure than discarding magnitude.

k=10 is chosen because the arithmetic is checkable today; the evaluation set will re-test it.

### Alternatives Considered

- **RRF at k=60** (the published default, and the default in Weaviate, Elasticsearch and Qdrant):
  One fewer departure from convention - Rejected on the arithmetic above; within a depth-50 pool it
  makes a decisive single-retriever hit unreachable, which is the specific failure the corpus design
  flagged.
- **Weighted blending, per-query min-max, α = 0.5**: Preserves score magnitude, which is exactly the
  signal a runaway lexical match carries - Rejected: on the worked figures it loses the same case,
  and min-max amplifies a narrow cosine band into full-range noise. Fixing it requires fitting α to
  an example.
- **RRF at k=60 plus a rank-1 lexical floor** (reserve one slot for the top BM25 hit): Keeps the
  conventional constant and guarantees set membership - Rejected as two mechanisms where one
  suffices. The floor would also fire on every query, including those where the lexical top hit is a
  common-word false positive.
- **Add a cross-encoder reranker**: Anthropic measured failures dropping 2.9% → 1.9% - Rejected:
  measured at 236 ms (`ms-marco-MiniLM-L-6-v2`) to 879 ms (`bge-reranker-base`) on this machine
  against a ~4 ms retrieval stage, and reported to *degrade* NDCG on out-of-distribution technical
  corpora, which gear manuals are.

### Consequences

**Positive:**
- A verbatim identifier query that only BM25 can serve reaches synthesis, which is the majority of
  real queries against this corpus.
- One mechanism, one parameter, no normalisation, no per-source state. Under 0.5 ms.
- The governing inequality is directly testable as a property, so a future change to k is caught
  rather than argued.

**Negative:**
- A small k makes fusion top-heavy: a lexical false positive at rank 1 takes an early slot. With a
  cap of 8 and a synthesis model that re-selects, one wasted slot is cheap — but it is a real cost.
- k=10 departs from every published default, so anyone reading the code will expect 60 and must be
  told why.
- The value rests on arithmetic over one worked case, not on measured recall. It is provisional
  until the evaluation set exists.

---

## Decision 2: Obtain the answer's structure from a prompt-level framing the engine parses, not from a provider's structured-output feature

**Date**: 2026-08-14
**Status**: accepted

### Context

`CONTRACTS.md` §4 requires a distinct `direct_answer` and a `body` carrying machine-identifiable
structure, and 1.9 requires the first actionable instruction within 25 words. 1.11 requires **one**
declared text format for every provider and every outcome. The engine must also extract
`uncovered_parts[]`, `narrowing`, `required_device` and inline citations from the same stream. The
providers are a keyed hosted Anthropic model, a local OpenAI-compatible server, and a shared
backend.

### Decision

Define a line-oriented framing, `dawmans/answer-framing/1`: outcome token, `direct_answer`, `---`,
then a restricted Markdown subset plus five sigil prefixes, with inline `[[p:<passage_id>]]`
citation markers. The engine parses it incrementally into SSE events. No provider-side schema
enforcement is used on any provider.

### Rationale

Structured outputs would make the first streamed tokens `{"outcome":"answered","direct_answer":"` —
roughly ten tokens of scaffolding before the first word the user can read, against a design whose
headline property is that the first word arrives fast and is itself the answer. Streaming a JSON
object also requires assuming keys are emitted in schema order so a partial parser can surface
`direct_answer` early; constrained decoding does not contractually guarantee that ordering.

1.11 settles the rest. Local models behind an OpenAI-compatible endpoint have inconsistent or absent
constrained-decoding support, so a schema-level contract would either be provider-specific — which
1.11 forbids — or would have to degrade to the weakest provider anyway.

And the parser exists either way: citations must sit **inline within prose**, which no JSON schema
can constrain. A schema-level design would still need an in-string marker convention and an engine
parser for it, so the schema buys reliability on the outer envelope only, at the cost of the first
ten tokens and of provider uniformity.

### Alternatives Considered

- **`output_config.format` with a `json_schema`** on the hosted provider: Guarantees the envelope
  parses; validated server-side - Rejected on first-token cost, on the key-ordering assumption
  streaming needs, and on 1.11 — it cannot be the single format across a local provider.
- **A forced tool call with a strict schema**: Same guarantee, and `strict: true` validates
  parameters - Rejected for the same reasons plus one more: a tool call is not streamed as prose at
  all, so 4.5's incremental delivery of the answer text is lost.
- **Two calls — one to synthesise prose, one to structure it**: Clean separation - Rejected
  outright: a second round trip against a 1.2 s first-token budget.
- **Free prose with no framing, structure inferred by the engine**: Nothing for a model to get wrong
  - Rejected: 1.10 explicitly forbids the caller applying heuristics to prose, and the engine
  applying them instead just moves the heuristic.

### Consequences

**Positive:**
- The first token the provider emits after the outcome word is the answer.
- One format across three provider kinds; a new provider implements `stream()` and nothing else.
- The five sigils give `uncovered_parts`, `narrowing` and `required_device` without a second pass,
  and give 1.12's edition caveat and 1.4's conflict a machine-identifiable home in `body` — so no
  field is invented on the closed `AnswerEnvelope`.

**Negative:**
- Nothing enforces the framing. A model that ignores it falls to the unparsed path, where the whole
  stream becomes `body` and `direct_answer` is the first sentence — degraded, and 1.9's 25-word
  target is then luck.
- The framing is a prompt-engineering surface that can regress silently on a model change. Mitigated
  by the parser-totality property and one fixture per content outcome, but not eliminated.
- A parser to own, versioned in the format name.

---

## Decision 3: Classify the outcome with fixed-order engine gates plus a model-chosen content outcome carried as the stream's first line

**Date**: 2026-08-14
**Status**: accepted, counts amended by `DECISIONS.md` Decision 11

> **Amendment (2026-08-14).** `DECISIONS.md` Decision 11 added `ranked-causes` to `CONTRACTS.md` §6,
> so every count below moves by one on the model's side: **seventeen** outcomes, **seven** of them
> content outcomes validated against a seven-member enum, ten still engine-determined. The split,
> its disjointness and the single framing-unparsed exception are unchanged, and `ranked-causes` is
> deliberately model-chosen for that reason — reaching it from the engine's own narrowing counter
> would put a content outcome behind a gate and add a second exception to the property this decision
> exists to keep provable. The counter is instead carried into the prompt, exactly as 7.5 already
> requires. `causes[]` itself is still engine-built from the triage sidecar on the entry path, for
> the same reason `narrowing` is.

### Context

`CONTRACTS.md` §6 is a closed set of sixteen outcomes and every turn must yield exactly one. Most
are mechanical — an empty scope, an unconfigured provider, a timeout. Six are judgements about the
answer: `answered`, `partially-answered`, `needs-narrowing`, `refused-not-covered`, `out-of-domain`,
`no-manual-for-device`.

The hard one is 2.8/2.9. "Why is my kick distorting" retrieves Saturator, Drum Buss and Overdrive at
*high* relevance, and all three are wrong. The relevance threshold in 2.7 cannot catch it, by 2.8's
own words: the scores are high. Distinguishing `out-of-domain` from `refused-not-covered` requires
knowing whether any reference manual could ever hold the answer, which is a property of the
question, not of a score.

### Decision

Split §6. **Ten** outcomes are engine-determined by gates — four pre-flight, six in-flight. Six
content outcomes are chosen by the synthesis model and carried as the bare first line of its stream,
validated against a six-member enum. The split is disjoint on every path but one: where the model's
first line is not a valid outcome, the engine derives `answered` or `refused-not-covered` from its
own coverage signal.

A question over 1000 characters is **not** among the sixteen: it is rejected before a turn exists
(9.12), which is exactly what makes it distinguishable from every member of §6.

### Rationale

The responsiveness test in 2.8 needs the question and the passage text together, which is exactly
the input the synthesis call already has. Putting the decision there costs nothing: no extra call,
no extra token, no extra millisecond. Any other placement pays for information the synthesis model
is about to derive anyway.

Splitting the set disjointly is what makes totality provable rather than asserted. The engine's
gates are a terminating fixed-order chain with a default, and the model's contribution is a
validated enum with a default, so "exactly one member of §6" is a property a generator can attack
rather than a claim in prose.

The `out-of-domain` versus `refused-not-covered` test is then expressible as a prompt question the
model can actually answer — *do these passages answer what was asked, or merely share its
vocabulary, and could any reference manual ever cover this?* — with 2.9's carve-out stated
alongside: an `authored-triage` passage that matches means never out-of-domain.

### Alternatives Considered

- **A pre-flight classifier call on a cheap model**: A dedicated decision with its own prompt, and
  the outcome known before synthesis starts - Rejected on latency: even a fast model's first token
  is a few hundred milliseconds, against a 1.2 s end-to-end first-token budget it would consume a
  quarter to a third of, for a decision the synthesis model must make regardless.
- **Engine heuristics over retrieval scores**: Deterministic, testable, no model involved -
  Rejected because it cannot work. 2.8 exists precisely because the wrong passages score highly;
  a score-based rule is blind to the failure it is meant to catch.
- **Classify the finished answer post-hoc**: The engine sees the whole output before deciding -
  Rejected: the outcome selects the caller's renderer, and it must arrive before the first painted
  token, not after the last one.
- **Let the model emit any §6 member**: One uniform mechanism - Rejected: the model would be able to
  claim `timeout` or `provider-error`, which are facts about the engine's own execution and not
  about the answer.

### Consequences

**Positive:**
- Zero latency and zero cost for the classification.
- The engine can never emit a content outcome and the model can never emit an engine outcome, so the
  totality property has a clean proof shape.
- The 2.8 test is posed as responsiveness rather than similarity, to the only component that has
  both the question and the passages.

**Negative:**
- Six of sixteen outcomes are decided by a model and are therefore not reproducible across model
  versions. `out-of-domain` versus `refused-not-covered` in particular will move when the model
  moves, and the only defence is the evaluation set's outcome-labelled bands.
- A model that emits an invalid first line degrades to the engine's coverage-derived default, which
  can only ever produce `answered` or `refused-not-covered` — never `needs-narrowing` or
  `out-of-domain`.

---

## Decision 4: The provider interface carries text deltas and nothing else

**Date**: 2026-08-14
**Status**: accepted

### Context

6.1 requires three provider kinds behind one contract and 6.2 requires the same response shape —
streamed text, citations, timings, refusal signalling — regardless of which is configured. The
question is where the boundary sits: how much of the envelope a provider produces, and how much the
engine derives.

### Decision

`Provider.stream()` yields `str` text deltas. Framing, parsing, citation resolution, grounding,
outcome extraction and timings are engine-side for every provider. Failures are raised as a
four-member `ProviderFailure` that the engine maps onto §6. No third-party LLM abstraction layer is
used.

### Rationale

If a provider produced structured events, 6.2 would become an obligation each provider must
independently honour, and the third one to be written would be the one that quietly diverges. With
the boundary at text, 6.2 is a structural fact: there is only one parser, one citation resolver and
one grounding check on the machine, and a provider has no way to produce a differently shaped
envelope.

It also keeps the surface a new provider must implement to four methods, and keeps the two things
this design most needs to control — cancellation within 250 ms and a first-token watchdog at 10 s —
in engine code rather than distributed across provider implementations with different underlying
clients.

### Alternatives Considered

- **Providers return structured envelope events**, each using its own native structured-output or
  grammar feature: Better per-provider fidelity; the hosted provider could enforce the schema -
  Rejected: it makes 6.2 a per-provider promise rather than a property, and triples what a new
  provider must implement.
- **LangChain or a similar multi-provider abstraction**: Providers, streaming and retries already
  written - Rejected: a dependency and a configuration surface for three providers on one machine,
  and its streaming and cancellation semantics are precisely what 4.9 and 4.10 need direct control
  over.
- **One provider only (hosted), local deferred**: Less to build - Rejected: 6.14's zero-outbound
  local path is the privacy posture the whole loopback design rests on, and retrofitting it later
  would mean redesigning the boundary.

### Consequences

**Positive:**
- 6.2 holds by construction. A provider cannot produce a differently shaped answer.
- Cancellation, the first-token watchdog and the rate-limit policy are written once.
- Adding a fourth provider is one class with four methods.

**Negative:**
- The hosted provider's structured-output feature is unused, so nothing enforces the framing
  server-side. Decision 2 accepts that cost, and this decision inherits it.
- Provider-specific niceties — Anthropic prompt caching, `usage.iterations`, refusal fallbacks —
  need per-provider handling outside the shared interface, so the interface is not the whole story.

---

## Decision 5: Send eight passages to synthesis, raised only by the per-source floor and by a narrowing turn

**Date**: 2026-08-14
**Status**: accepted

### Context

1.3 caps a turn at 12 passages; 5.6's per-source inclusion floor takes precedence over that cap when
qualifying sources exceed it, and the caller may put 12–16 sources in scope at once. The research
note's central finding is that retrieval is ~4 ms of a ~1,500 ms answer, and that the only
retrieval-side lever on wall-clock time is how many context tokens are emitted, because prefill —
and therefore time to first token — scales linearly with prompt length.

### Decision

Default cap **8**. One slot per qualifying source first (5.6), then fused rank. Effective cap is
`max(8, |qualifying sources|)`, and **12** on a turn that expands a triage entry's fix pointers.

### Rationale

At the 350-word chunk size `data/manual-corpus` Decision 3 fixes, a passage is about 420 tokens.
Eight passages is ~3,400 tokens; twelve is ~5,000. Against a ~600-token cached system prompt and an
800-token history budget, moving from 8 to 12 adds roughly 1,700 prefill tokens, which is on the
order of 100–200 ms of the 1.2 s hosted first-token budget — 8% to 17% of it, spent on passages
ranked 9th to 12th by a retriever whose top-8 the model is going to re-select from anyway.

Anthropic's published finding that k=20 was most performant optimised recall on a corpus far larger
and more heterogeneous than three gear manuals. Over ~1,000 chunks drawn from documents about
distinct devices, with hybrid retrieval and citation headers already disambiguating near-identical
parameter sections, the marginal passages are unlikely to carry the answer.

The 5.6 floor is what makes a small cap safe: the 5-page APC guide is guaranteed a slot whenever it
has anything above the threshold, so shrinking the cap cannot reintroduce small-source drowning.
A narrowing turn is the one case where more passages are load-bearing rather than marginal — 7.6
requires each cause to carry its confirming check *and* its vendor-manual fix citation — so it uses
1.3's full ceiling.

### Alternatives Considered

- **12 always** (1.3's ceiling): Maximum recall within the criterion; no second number to justify -
  Rejected: ~1,700 extra prefill tokens on every turn to raise recall on a corpus where the top-8 of
  a hybrid retriever should already contain the answer. It spends the headline property to buy an
  unmeasured one.
- **10** (the research note's own figure): Splits the difference - Rejected as a number with no
  argument behind it; the note's k=10 was reasoned against a k=20 baseline, not against 8.
- **Adaptive k — send passages until a fused-score elbow**: Spends tokens only where the retrieval
  is genuinely uncertain - Rejected: an elbow on RRF scores measures retriever agreement, not
  relevance, and there is no evaluation set to calibrate the cut against. Revisit once one exists.
- **Truncate passages instead of dropping them**: More sources represented per token - Rejected: a
  truncated passage can be cited, and a citation whose passage the user opens and finds does not
  contain the claim is the failure mode 3.4 exists to prevent.

### Consequences

**Positive:**
- The single highest-leverage latency decision is taken in the direction the measurements point.
- Small sources stay represented, because the floor is allocated before rank.
- The narrowing path gets the passages it needs without raising the default for every turn.

**Negative:**
- A question whose answer sits at fused rank 9 is answered from weaker passages or refused. Nothing
  currently measures how often that happens.
- Two effective caps (8 and 12) is one more number than a single ceiling would be, and the
  narrowing-turn exception has to be remembered when reading `timings`.
- With 16 sources in scope the floor pushes the passage count to 16 and the prompt to ~6,700 tokens,
  which is the worst latency case in the design and is mandated by 5.6, not chosen here.

---

## Decision 6: Store provider keys in the macOS Keychain, never in a file

**Date**: 2026-08-14
**Status**: accepted

### Context

6.11 to 6.13 and 9.8 form the strictest constraint set in the spec: a key may not reach logs,
traces, errors, telemetry, crash reports or answer output; it may be transmitted only to its own
provider's endpoint and only over an encrypted transport; and it may never be returned through any
read interface. The engine now exposes operations that set, clear and test credentials (9.4), so
every one of those paths is reachable from a browser page on the same machine.

### Decision

Store keys in the macOS Keychain through `keyring`, service `dawmans`, one account per provider
kind. No key is written to any configuration file, environment variable or log. Reads return a
masked form — the last four characters — everywhere except the single call site that constructs a
provider's HTTP client.

### Rationale

A file is the wrong container for this on a developer machine even at mode 0600: it is included in
backups, in Time Machine snapshots, in `tar` of the project directory, and in any editor or agent
that indexes the repository. `manuals/` is already gitignored and `index/` is derived, so a
credentials file would be the only secret in the tree and the only thing an accidental `git add -A`
could publish. The Keychain is the platform's answer, is already unlocked for the logged-in user,
and needs no permissions logic of our own.

`ANTHROPIC_API_KEY` in the process environment is tempting because the SDK reads it with no code,
but the environment of a long-lived server process is readable by anything running as the user, is
inherited by every subprocess, and appears in crash reports — which 6.11 names explicitly.

Masking on read is enforced at the type level rather than by discipline: `ProviderStatus` has a
`masked: str | None` field and no field that can hold a full key, so no response model is capable of
carrying one.

### Alternatives Considered

- **A `0600` file under `~/.config/dawmans/`**: No new dependency; works headless and on Linux if
  the project ever moves - Rejected on backup and repository exposure, and because file permissions
  do not survive a copy.
- **`ANTHROPIC_API_KEY` in the environment**: Zero code — the SDK already reads it - Rejected: 6.11
  names crash reports, and process environments appear in them; it is also inherited by every
  subprocess and cannot express a per-provider key.
- **Prompt for the key each session, hold in memory only**: Nothing persisted at all - Rejected as
  hostile to the actual use, which is a tool opened on a second screen mid-session; and 9.4's
  set-credential operation implies persistence.

### Consequences

**Positive:**
- No secret exists in the repository tree or in any file the user might copy or back up.
- The masked-read rule is structural: no response model can carry a full key.
- Keychain access is per-application and prompts on first use, so the user sees the grant.

**Negative:**
- `keyring` is a dependency, and it binds the design to a platform keystore. A future Linux port
  needs a working Secret Service, which is not guaranteed on a headless machine.
- Keychain access can prompt at unexpected moments — a first read after a system update — which will
  look like a hang inside a turn. Mitigated by reading the key once at provider construction rather
  than per turn.
- Tests must stub `keyring`, so the credential path is never exercised end to end in CI.

---

## Decision 7: A state value is a flat key, value and provenance triple, not a DAW-shaped object model

**Date**: 2026-08-14
**Status**: accepted

### Context

8.4 requires the `StateSource` contract to admit, **without redefinition**, both an implementation
reading a saved Ableton project file and one receiving live state from a running DAW. Only the null
implementation ships (8.3). The verified facts about the two future sources differ sharply: Live's
`Log.txt` is plain text appended live and yields the open Set's path and the active audio device;
an `.als` is gzipped XML whose freeze-sequencer section duplicates monitoring and armed values and
stores mute inverted.

### Decision

`StateValue` is `(key, value, observed_at, origin, origin_kind)` where `key` is a dotted string and
`value` is a scalar. A `StateSnapshot` is a tuple of those plus an acquisition time. No track,
device, clip or chain types exist in the contract.

### Rationale

The two future sources agree on almost nothing. A log tail can produce two facts about the whole
application; an `.als` parse can produce hundreds about tracks that may not be the tracks currently
loaded. Any object model rich enough for the second would be almost entirely null for the first, and
a model shaped around the first would have to be redefined for the second — which is exactly what
8.4 forbids.

The `.als` duplication is the decisive case. Monitoring and armed appear twice, once in the
freeze-sequencer section, and mute is stored inverted. Under an object model, resolving which copy
is authoritative would either leak into the contract as a discriminator field or be resolved
inconsistently by each implementation. Under a flat triple it is a parsing question, wholly inside
`AlsStateSource`, invisible to the engine, and the engine's behaviour is identical either way.

`origin_kind` is the one field that is not raw provenance, and it earns its place: it is what makes
8.7 automatic. A saved-file source is stale by definition, so the warning fires from the record's
own shape rather than from a rule the engine has to know about each implementation.

### Alternatives Considered

- **A typed session model** (`Project(tracks=[Track(monitor=…, armed=…)])`): Type-safe, expressive,
  and the natural shape for prompt assembly - Rejected on 8.4: it would be nearly all-null for a log
  tail, and the `.als` duplicate-values problem would surface as a contract field.
- **Raw provider-shaped payloads passed through to the prompt**: Zero contract; each implementation
  emits whatever it has - Rejected: 8.5 requires freshness and origin on *every* value, and 8.6
  requires attribution, neither of which a pass-through can guarantee.
- **A JSON Schema per source kind, negotiated at registration**: Full expressiveness with
  validation - Rejected as machinery for a seam with one implementation and no live consumer.

### Consequences

**Positive:**
- Both named future implementations fit without changing the contract, which is 8.4's actual test.
- 8.7's staleness warning falls out of `origin_kind` rather than needing per-implementation
  knowledge in the engine.
- The null path is trivially total, so 8.2's "no degradation" holds without a special case.

**Negative:**
- Key naming becomes an unversioned convention shared between an implementation and the prompt. Two
  sources could name the same fact differently, and nothing catches it.
- A rich source must flatten a hierarchy into dotted keys, which loses structure a future feature
  might want — for example, iterating every track's monitor state.
- Scalar-only values cannot express a list or a nested record without encoding it into a string.

---

## Decision 8: Count the history token budget locally, never with a provider endpoint

**Date**: 2026-08-14
**Status**: accepted

### Context

10.8 bounds carried conversation history to a fixed 800-token budget, truncated oldest-first. An
earlier draft of this design enforced that budget with `client.messages.count_tokens`, described as
"checked rather than estimated" — accurate about the count, wrong about the cost.

`messages.count_tokens` is an HTTP endpoint, not a local tokeniser. Two independent reviews of this
design reached that finding first and independently of each other.

### Decision

Count the history budget locally, with the BGE tokeniser already resident for retrieval, and enforce
the 800-token budget with a 10% safety margin against under-count. No provider SDK call occurs
anywhere in a turn before `stream()`. `count_tokens` is used only in offline `make bench`
calibration of that margin.

### Rationale

The endpoint call fails three separate obligations at once, and no amount of caching fixes it. It is
an unbudgeted network round trip inside 4.3's 150 ms engine-overhead cap, on every turn, before the
provider call that the budget exists to protect. It breaks 6.14, which requires *no outbound network
request for the whole turn* on a local provider. And it would ship question and history text to a
hosted provider on a turn the user configured as local, or as a shared backend whose disclosure they
have not acknowledged — defeating 6.15's gate by a mechanism the user cannot see.

It also made prompt assembly provider-specific, which Decision 4 exists to prevent: a component that
counts tokens through the Anthropic client cannot serve a local provider unchanged.

The resident tokeniser is a different tokeniser from any provider's, so its count is an estimate. The
margin is the price of that, and it is a cheap price: 800 tokens is a self-imposed budget, not a
model limit, so being 10% conservative costs a little history and risks nothing.

### Alternatives Considered

- **Keep `count_tokens`, cache the result per turn**: Caching does not help — history changes every
  turn, so the call happens every turn. It addresses none of the three failures.
- **Characters-per-token estimate with no tokeniser**: Simpler and dependency-free, but the error
  bound is much wider than a real tokeniser's, so the margin would have to be large enough to waste
  a meaningful share of the 800 tokens.
- **Drop the token budget and bound history by turn count alone (10.1's six turns)**: Rejected
  because turns vary in length by an order of magnitude, so a six-turn bound does not bound tokens,
  which is the thing that costs prefill latency.

### Consequences

**Positive:**
- 6.14's no-outbound-request guarantee becomes structural: there is no SDK call to make before
  `stream()`, so a local turn cannot leak by oversight.
- The engine-overhead cap loses a network round trip it could not have absorbed.
- Prompt assembly is provider-agnostic, as Decision 4 requires.

**Negative:**
- The count is an estimate, so the 800-token budget is enforced approximately rather than exactly.
- The 10% margin is a guess until `make bench` calibrates it against a real tokeniser.
- Retrieval's tokeniser is now load-bearing for prompt assembly, coupling two stages that were
  otherwise independent.

---

## Decision 9: Build narrowing candidates in the engine from the triage entry, not from model output

**Date**: 2026-08-14
**Status**: accepted

### Context

The answer framing gives the model a `?narrow` sigil plus `* ` lines, hoisted into the envelope's
`narrowing`. The narrowing section separately specifies that the engine derives candidates from the
triage sidecar: label from each cause's `check`, value from its `statement`, in the entry's own
order. Both cannot be true, and the design did not say which wins.

7.2 requires that "that entry's ranked causes and their confirming checks SHALL be the source of the
candidates, taken in the entry's own order"; 7.6 requires the ranking be preserved; and
`ui/ask-and-source-picker` 6.2 forbids the surface reordering, merging or adding candidates. Model
output satisfies none of these by construction.

### Decision

Where a triage entry matched, the engine constructs `narrowing` from the sidecar and the model is
not asked for candidates at all; `?narrow` is used **only** on the no-entry fallback path.

### Rationale

Candidates are not prose — they are selectable controls that decide the next retrieval. Promoting
model-authored text into an actionable affordance is the one place in this design where model output
would escape the `supplied`-set check that makes 3.6 airtight everywhere else. A hallucinated cause
would be indistinguishable from an authored one at the point the user acts on it.

Constructing candidates in the engine is also what makes 7.8 executable. That criterion requires
suppressing a candidate whose value session state already supplies, and suppressing the whole
question when every candidate goes — the engine cannot suppress a question the model has already
chosen to ask and begun streaming.

The asymmetry with the fallback path is honest rather than awkward: the entry path is the one the
requirements call satisfiable, and it is the one that gets the structural guarantee.

### Alternatives Considered

- **Let the model emit `?narrow` and reconcile its lines against the entry afterwards**: Requires
  matching free text to causes, which is the fuzzy judgement the sidecar exists to avoid, and it
  cannot recover the ranking when the match is partial.
- **Put the entry's causes in the prompt and instruct the model to echo them verbatim**: Cheaper to
  build, but "the model reliably echoes" is not a guarantee, and 6.2's no-reorder rule would rest on
  an instruction rather than on construction.
- **Always use the model path, dropping the sidecar derivation**: Rejected outright — it contradicts
  7.2's text and removes the only mechanism that makes narrowing satisfiable against the real corpus.

### Consequences

**Positive:**
- 7.2, 7.6 and UI 6.2 hold by construction rather than by prompt discipline.
- 7.8's suppression becomes implementable, and the "all candidates removed ⇒ no question" case works.
- A candidate is always traceable to an authored cause, so it can always carry that cause's citation.

**Negative:**
- Two code paths produce `narrowing`, and the fallback path keeps only prompt-level guarantees.
- The engine now decides `needs-narrowing` on the entry path while the model decides it on the
  fallback path, which is a second exception to Decision 3's clean split.
- A narrowing question the model would have phrased better is not available; the wording comes from
  the author's `check` text, so a badly written entry produces a badly worded question.

---

## Decision 10: Filter triage fix pointers through the turn's source scope, carrying the cause as unbacked

**Date**: 2026-08-14
**Status**: accepted

### Context

A triage entry's causes carry `fix[].passage_ids` pointing into vendor manuals. Narrowing expansion
resolves those pointers and admits the passages to `supplied` so the fix can be cited. The design
did so without checking the turn's source scope.

Selecting only the authored triage source is not an exotic scope — it is the ordinary diagnostic
one, and 5.4 covers it explicitly. On that scope, unfiltered expansion injects vendor-manual passages
into synthesis from sources the user deselected.

### Decision

Resolve fix pointers, then filter the result through the same source scope mask retrieval uses. Where
a cause's fix passage is out of scope, carry the cause as if `unbacked` **for that turn** and name
the holding source through 2.3's suggestion path.

### Rationale

1.1, 5.1 and 2.4 all say the selected sources are the complete grounding scope for a turn, and this
design's own scope-soundness invariant states that no returned passage's `source_id` lies outside the
selected set. Unfiltered expansion breaks all four, and it corrupts `contributing_sources[]`, which
CONTRACTS §4 defines over *selected* sources — the user would be told a source contributed that they
had switched off.

The `unbacked` treatment is the right degradation because it is the one the user already understands:
CONTRACTS §2 defines `unbacked` as a cause resting on no vendor-manual passage, and the UI marks it
inline. A cause whose fix is out of scope is, for this turn, exactly that. The suggestion path then
tells the user which source to select, which turns a silent gap into a one-activation fix.

Marking it per-turn rather than mutating the flag matters: the engine reads `unbacked` and never sets
it (1.13, 3.3), and the entry itself is not broken — only out of scope.

### Alternatives Considered

- **Admit fix passages regardless of scope, as a deliberate carve-out**: Defensible on the grounds
  that the user asked a diagnostic question and wants the fix. Rejected because it would require
  reconciling 1.1, 2.4, 5.1 and CONTRACTS §4 simultaneously, and because a citation to a manual the
  user deselected is exactly the surprise source scoping exists to prevent.
- **Drop the cause entirely when its fix is out of scope**: Rejected as a worse answer — the cause
  may still be the right one, and the check is still observable; only the documented fix is missing.
- **Auto-widen scope to include the pointed-at source**: Rejected because it overrides a deliberate
  narrowing without asking, which §3 of the UI spec treats as the failure mode to avoid.

### Consequences

**Positive:**
- Scope soundness holds on every path, including the narrowing expansion that previously bypassed it.
- `contributing_sources[]` stays truthful to its CONTRACTS §4 definition.
- The user is told what to select rather than silently given an uncited fix.

**Negative:**
- A triage-only scope yields causes whose fixes are all unbacked, which reads as a weaker answer than
  the corpus could actually give.
- `unbacked` now has two meanings at the point of rendering — genuinely unbacked, and out of scope
  for this turn — and the UI cannot currently distinguish them.
- The suggestion path carries more weight than 2.3 was written for, since it is now the mechanism
  that recovers a fix rather than merely proposing a better source.
