---
references:
    - specs/api/answer-engine/requirements.md
    - specs/api/answer-engine/design.md
    - specs/api/answer-engine/decision_log.md
    - specs/CONTRACTS.md
---
# Answer Engine

## Phase 1: Package scaffold and the envelope records

- [x] 1. Scaffold the dawmans.answer package and the serve dependency group <!-- id:f3kp001 -->
  - Create the src/dawmans/answer/ module tree of design 'Module placement' with empty modules; register `dawmans serve` as a stub subcommand on the existing cli.py.
  - Split [project.optional-dependencies]: pymupdf, lingua-py and fontTools under `ingest`; fastembed, bm25s, numpy, anthropic, starlette, uvicorn and keyring under `serve` - the API host runs `uv sync --extra serve` and PyMuPDF is never installed.
  - Add the confinement test: every dawmans.answer.* module and dawmans/triage/ import in a subprocess with a sys.meta_path finder that raises on `fitz` - this catches the accidental corpus.pdf import a dual-group dev environment hides.
  - Stream: 1
  - References: specs/api/answer-engine/design.md

- [x] 2. Write tests for the Citation, AnswerEnvelope and Cause records <!-- id:f3kp002 -->
  - Fields exactly the CONTRACTS 3, 4, 4c and 4e tables; no field outside them can be set; reason, retry_after, detail and framing are flat optional members of the one envelope.
  - Pageless citation: section_number, page and doc_version absent - never empty strings, never synthesised; entry_location present on authored-triage only and absent on a vendor-manual; kind always present.
  - Cause: rank always present and equal to its position in causes[]; cites[] and fix_cites[] are passage_id lists, never nested citation records.
  - The outcome enum is exactly the 17 members of CONTRACTS 6 and reason exactly the five values of 6a - assert an unlisted member cannot be constructed, because the caller cannot render an outcome the engine has not named.
  - Blocked-by: f3kp001 (Scaffold the dawmans.answer package and the serve dependency group)
  - Stream: 1
  - Requirements: [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.8](requirements.md#3.8), [9.9](requirements.md#9.9)
  - References: specs/CONTRACTS.md

- [x] 3. Implement envelope.py and the outcome and reason enums <!-- id:f3kp003 -->
  - Frozen dataclasses for Citation, AnswerEnvelope, Cause and RequiredManual per CONTRACTS 3, 4, 4c, 4e; StrEnums for outcome and reason.
  - Blocked-by: f3kp002 (Write tests for the Citation, AnswerEnvelope and Cause records)
  - Stream: 1
  - Requirements: [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.8](requirements.md#3.8), [9.9](requirements.md#9.9)

## Phase 2: The corpus view

- [x] 4. Write tests for CorpusView load, refusal and the revision watch <!-- id:f3kp004 -->
  - Load order of design 'What the engine reads': manifest first, refuse to serve when index_version differs; an unreadable new manifest keeps the live view in place and records the mismatch for GET /sources - never mapped to corpus-empty, which would be a lie.
  - Row slices come from manifest.sources row_start/row_count, so source scoping is a slice, not a scan.
  - The sidecar name is derived by the slug rule from the constant `authored/triage`, never spelled: a view whose authored sidecar is written `authored-triage.json` fails loudly at load rather than serving with no device declarations - the silent failure 5.13 exists to prevent.
  - os.stat on the manifest before each turn: a corpus_revision change discards the view wholesale - vectors, lexical, passages, sources, gaps, sidecar - and loads manifest.view_dir; nothing partial is reused, so no answer can mix revisions.
  - The reload is never charged to a turn: the swap happens before the turn's timer starts, corpus_reload_ms is run-level, and an in-flight turn keeps its files.
  - Blocked-by: f3kp003 (Implement envelope.py and the outcome and reason enums)
  - Stream: 1
  - Requirements: [5.10](requirements.md#5.10), [5.13](requirements.md#5.13)

- [x] 5. Implement view.py <!-- id:f3kp005 -->
  - mmap vectors.npy, read passages.jsonl, load lexical/, sources.json, gaps.json and the triage sidecar; the stat-based revision watch and the wholesale swap.
  - Blocked-by: f3kp004 (Write tests for CorpusView load, refusal and the revision watch)
  - Stream: 1
  - Requirements: [5.10](requirements.md#5.10), [5.13](requirements.md#5.13)

## Phase 3: Retrieval and scoping

- [ ] 6. Write tests for device scope derivation and the passage predicate <!-- id:f3kp006 -->
  - Scope over source kind: the selected vendor-manual records' hardware_applicability.device unioned with gaps.owned_but_undocumented; the authored source contributes nothing - reading a device off it would yield None and poison the set.
  - No vendor-manual selected: the scope is every indexed vendor-manual device plus the gaps, derivable from sources.json and gaps.json alone; rig.yaml is never read.
  - The union is computed even though owned-but-undocumented is empty today - assert against a fixture gaps report declaring a device that the union admits it (the Decision 12 dormancy the live corpus cannot produce).
  - A passage declaring devices disjoint from the scope is excluded from the turn entirely - filter, never merely ranked lower; a passage declaring none is scoped by its source alone; selecting the triage source does not put every entry in scope.
  - Device-match closeness is not used at all - 5.13 permits it for ranking and there is no evaluation set to tune it with.
  - Blocked-by: f3kp005 (Implement view.py)
  - Stream: 1
  - Requirements: [5.12](requirements.md#5.12), [5.13](requirements.md#5.13)

- [ ] 7. Implement scope.py <!-- id:f3kp007 -->
  - Device scope derivation and the passage predicate, applied inside the candidate mask - the only place where "filter, not rank" holds by construction.
  - Blocked-by: f3kp006 (Write tests for device scope derivation and the passage predicate)
  - Stream: 1
  - Requirements: [5.12](requirements.md#5.12), [5.13](requirements.md#5.13)

- [ ] 8. Write tests for masked hybrid retrieval and RRF fusion <!-- id:f3kp008 -->
  - Masking precedes top-k on both retrievers: out-of-scope and device-filtered rows never consume the depth-50 slots - retrieve-then-mask would make a narrow scope look like poor coverage, and that failure is asserted against.
  - Fusion properties at k=10 (Decision 1): monotonicity - improving a rank never lowers the fused rank; input invariance with ties broken by passage_id; decisiveness - a sole rank-1 hit outranks every double hit at ranks worse than (k+2, k+2), the arithmetic the decision rests on, stated executably.
  - Ranking across selected sources is on relevance alone, never weighted by page or chunk count; one selected source and all selected sources are the same mask path, so 5.4 and 5.8 have no special case and none exists.
  - Scope soundness property: no returned passage's source_id is outside the selected set; retrieval makes no outbound network request and operates wholly on the loaded view.
  - The question is embedded with the BGE query prefix, not the passage prefix.
  - Blocked-by: f3kp007 (Implement scope.py)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.7](requirements.md#1.7), [5.1](requirements.md#5.1), [5.4](requirements.md#5.4), [5.5](requirements.md#5.5), [5.8](requirements.md#5.8)

- [ ] 9. Implement retrieve.py dense, lexical and fusion <!-- id:f3kp009 -->
  - Candidate mask, `vectors @ q` with argpartition to depth 50, bm25s with the mask as a weight mask, RRF at k=10.
  - Blocked-by: f3kp008 (Write tests for masked hybrid retrieval and RRF fusion)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.7](requirements.md#1.7), [5.1](requirements.md#5.1), [5.4](requirements.md#5.4), [5.5](requirements.md#5.5), [5.8](requirements.md#5.8)

- [ ] 10. Write tests for the relevance threshold and passage allocation <!-- id:f3kp010 -->
  - Two threshold arms, either qualifies: cosine >= 0.30, or BM25 rank 1 within its own source sharing a query term of document frequency <= 5% - per-source rank 1, not global, or the 5-page APC guide would qualify for nothing and the floor would never fire on it.
  - Both constants are configuration, not literals - they are guesses until the evaluation set exists.
  - No qualifying in-scope candidate means the turn is uncovered per 2.1, never synthesised from weak matches.
  - Floor/cap precedence property (Decision 5): one slot per qualifying source first, qualification evaluated per source rather than over the fused pool; cap = max(8, |qualifying|, 12 on a narrowing expansion); qualifying sources over 12 raise the cap exactly as 5.6 directs over 1.3, and every qualifying source contributes >= 1.
  - Blocked-by: f3kp009 (Implement retrieve.py dense, lexical and fusion)
  - Stream: 1
  - Requirements: [1.3](requirements.md#1.3), [2.7](requirements.md#2.7), [5.6](requirements.md#5.6)

- [ ] 11. Implement the threshold and the allocation rule <!-- id:f3kp011 -->
  - The two arms, per-source qualification, and the floor-then-fused-rank allocation in retrieve.py.
  - Blocked-by: f3kp010 (Write tests for the relevance threshold and passage allocation)
  - Stream: 1
  - Requirements: [1.3](requirements.md#1.3), [2.7](requirements.md#2.7), [5.6](requirements.md#5.6)

## Phase 4: Narrowing from triage entries

- [ ] 12. Write tests for narrowing candidates and the ranked-causes builder <!-- id:f3kp012 -->
  - Narrowing provenance property (Decision 9): on the entry path the candidate list equals, in order, the entry's first 2-4 causes - label from `check`, value from `statement`; no reorder, merge or addition, and the model is not asked for candidates at all.
  - Fix pointers are resolved against the view then filtered through the turn's source scope mask (Decision 10): fix-pointer scope property - no fix passage admitted to supplied lies outside the selected set; an out-of-scope fix carries the cause as unbacked for this turn and names the holding source through the suggestion path.
  - The expansion bound is over resolved passages, not pointers - a section pointer resolves to every chunk it produced; excess drops in cause order, within a cause in section order.
  - A state value that already supplies a candidate's value removes that candidate; all removed means no narrowing question is asked - only engine-built candidates make this executable.
  - Cause provenance property: causes[] equals the entry's first <= 4 causes in order, every rank equals its 1-based position, every passage_id in cites[] and fix_cites[] resolves into the turn's citations[], and an empty fix_cites[] implies the cause's citation carries unbacked - the engine reads the flag and never sets it.
  - 7.7 is structural on the entry path: each cause carries its own check and fix pointer, so every candidate changes what is retrieved or reported.
  - Blocked-by: f3kp011 (Implement the threshold and the allocation rule)
  - Stream: 1
  - Requirements: [1.13](requirements.md#1.13), [7.2](requirements.md#7.2), [7.6](requirements.md#7.6), [7.7](requirements.md#7.7), [7.8](requirements.md#7.8)

- [ ] 13. Implement narrow.py <!-- id:f3kp013 -->
  - Sidecar lookup by passage_id, candidate construction, scope-filtered fix expansion, state-value suppression, and the engine-built causes[] for the terminal form.
  - Blocked-by: f3kp012 (Write tests for narrowing candidates and the ranked-causes builder)
  - Stream: 1
  - Requirements: [1.13](requirements.md#1.13), [7.2](requirements.md#7.2), [7.6](requirements.md#7.6), [7.7](requirements.md#7.7), [7.8](requirements.md#7.8)

## Phase 5: Prompt, parser, grounding and the outcome procedure

- [ ] 14. Write tests for prompt assembly and the history budget <!-- id:f3kp014 -->
  - Cache ordering: static system prompt (the cache prefix), then passages, history, question; the assembled prompt carries the framing spec, the no-uncited-facts rule with the facts-versus-reasoning split, the 400-word cap, the 25-word direct-answer instruction, ordered steps for procedures, the edition/add-on caveat direction, the kind trust split, refusal without speculation, and the out-of-domain responsiveness test with 2.9's authored-entry carve-out.
  - The unselected-source roster is metadata only - source_id, display_name, product, kind - so 2.4 holds by construction; suggestions are forbidden outright on out-of-domain.
  - The no-XML instruction is present, and no "do not think" or "do not reason" instruction is - that measurably worsens the tag leak.
  - History enters in a block the framing spec marks uncitable; state values enter a separate labelled block with origin and age, with the staleness direction for saved-file origins or values older than 60 s and the state-versus-manual conflict direction (state side unattributed to any citation).
  - History truncated oldest-first to 800 tokens counted locally with the resident BGE tokeniser at a 10% margin; no provider SDK call occurs before stream() (Decision 8) - count_tokens is reserved for offline bench calibration.
  - The narrowing counter is carried into assembly: at 2 the prompt forbids ?narrow and directs ranked-causes - without that carriage 7.5 has no mechanism at all.
  - Blocked-by: f3kp013 (Implement narrow.py)
  - Stream: 1
  - Requirements: [1.2](requirements.md#1.2), [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.9](requirements.md#1.9), [1.12](requirements.md#1.12), [1.13](requirements.md#1.13), [2.1](requirements.md#2.1), [2.4](requirements.md#2.4), [2.6](requirements.md#2.6), [2.8](requirements.md#2.8), [2.9](requirements.md#2.9), [7.5](requirements.md#7.5), [8.6](requirements.md#8.6), [8.7](requirements.md#8.7), [8.10](requirements.md#8.10), [10.3](requirements.md#10.3), [10.8](requirements.md#10.8)

- [ ] 15. Implement prompt.py <!-- id:f3kp015 -->
  - System prompt, framing spec, roster, state and history blocks, and the local token budget.
  - Blocked-by: f3kp014 (Write tests for prompt assembly and the history budget)
  - Stream: 1
  - Requirements: [1.2](requirements.md#1.2), [1.6](requirements.md#1.6), [1.9](requirements.md#1.9), [2.6](requirements.md#2.6), [10.8](requirements.md#10.8)

- [ ] 16. Write tests for the framing parser <!-- id:f3kp016 -->
  - Parser totality property: for any byte string parse.py yields a well-formed envelope, never raises, never emits a partial Citation.
  - Line 1 validated against the seven-member content enum; invalid means the unparsed path - whole stream as body, direct_answer the first sentence, outcome from the coverage signal restricted to answered/refused-not-covered, framing: unparsed on the envelope.
  - Block classification at column 0 from the closed CONTRACTS 4d set; an unknown first line becomes a paragraph, never dropped; !conflict arity is a producer obligation checked and reported through framing - a block already emitted is never re-typed.
  - Sigil hoists: ~uncovered into uncovered_parts[]; ?narrow (fallback path only) into narrowing; ?cause into the fallback causes[] with rank equal to emitted order; @device into required_device; !suggest into suggested_sources[] resolved against sources.json with non-resolving ids dropped, at most 3, and the field absent - never an empty array - when none survives; !caveat and !conflict stay in body as their 4d blocks.
  - Inline forms: [[p:passage_id]] markers and backtick key-term spans, no other emphasis; the outcome token precedes direct_answer and direct_answer precedes every body block, so 1.8's ordering holds in the stream itself.
  - Blocked-by: f3kp003 (Implement envelope.py and the outcome and reason enums)
  - Stream: 1
  - Requirements: [1.4](requirements.md#1.4), [1.8](requirements.md#1.8), [1.10](requirements.md#1.10), [1.11](requirements.md#1.11), [2.2](requirements.md#2.2), [2.3](requirements.md#2.3), [2.5](requirements.md#2.5), [7.1](requirements.md#7.1)

- [ ] 17. Implement parse.py <!-- id:f3kp017 -->
  - The incremental line-oriented parser for dawmans/answer-framing/1: total over bytes, sigil hoisting, block typing, inline markers.
  - Blocked-by: f3kp016 (Write tests for the framing parser)
  - Stream: 1
  - Requirements: [1.4](requirements.md#1.4), [1.8](requirements.md#1.8), [1.10](requirements.md#1.10), [1.11](requirements.md#1.11), [2.2](requirements.md#2.2), [2.3](requirements.md#2.3), [2.5](requirements.md#2.5), [7.1](requirements.md#7.1)

- [ ] 18. Write tests for grounding and citation assembly <!-- id:f3kp018 -->
  - Citation round-trip property: for any supplied set and any stream of markers drawn from supplied and unknown, every emitted Citation resolves to a supplied passage and every unknown marker is stripped from the streamed text and counted - 3.6 holds by construction because a Citation is assembled only from supplied.
  - Field copy from Passage and SourceRecord: source_id, display_name, section, page, passage_id, doc_version, hardware_applicability with confirmed/assumed, degraded, has_figures, unbacked, kind and entry_location; pageless-citation property - absent fields are absent, never empty strings, never synthesised.
  - The ungrounded rule, evaluated per block after message_stop: arm (a) fact-shaped tokens using dawmans.triage.terms as the term extractor - reused, never reimplemented; arm (b) an uncited ordered-step block, because an uncited "Click it to re-enable the track" carries no fact-shaped token and is exactly what the user acts on.
  - A prose block that only orders or eliminates causes over cited facts is never marked - the CONTRACTS 8 split made executable; the signal is emitted after the last body delta and before done, never deferred past the turn.
  - History non-citability property: markers appearing in history text never produce a Citation.
  - State-value non-citability property: a marker appearing in a state block never produces a Citation - state values are never in supplied, the structural half of 8.6 alongside task 14's prompt-level attribution direction.
  - Blocked-by: f3kp017 (Implement parse.py)
  - Stream: 1
  - Requirements: [3.1](requirements.md#3.1), [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.6](requirements.md#3.6), [3.7](requirements.md#3.7), [3.8](requirements.md#3.8), [8.6](requirements.md#8.6), [10.3](requirements.md#10.3)

- [ ] 19. Implement ground.py and citation assembly <!-- id:f3kp019 -->
  - The supplied dict, marker resolution and stripping, the two-arm ungrounded rule, and the Citation field copy.
  - Blocked-by: f3kp018 (Write tests for grounding and citation assembly)
  - Stream: 1
  - Requirements: [3.1](requirements.md#3.1), [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.6](requirements.md#3.6), [3.7](requirements.md#3.7), [3.8](requirements.md#3.8)

- [ ] 20. Write tests for the outcome procedure and required_manual <!-- id:f3kp020 -->
  - Outcome totality and disjointness properties: for any gate state and any provider transcript exactly one CONTRACTS 6 member, never raised; no engine outcome reachable from a model line and no content outcome from a gate, except the framing-unparsed path restricted to answered and refused-not-covered.
  - Pre-flight gates in fixed order: corpus-empty; unknown-source-id naming the id rather than silently dropping it; no-sources-selected (including a scope emptied by 5.11); provider-unconfigured with reason no-provider-kind, missing-credential or disclosure-unacknowledged.
  - In-flight: cancelled is first in the fixed order - a turn that is both cancelled and has failed after partial output classifies cancelled, never incomplete (the in-flight table's row 5 ahead of row 6); then the streamed-output check precedes every error-kind gate - incomplete precedence property, any provider failure after >= 1 streamed token yields incomplete whatever the failure kind; then unreachable, rate-limited carrying retry_after, the 10 s timeout naming the provider as the stalled component, and provider-error including 401 as authentication-failed - distinguishable from missing-credential by the sub-code, never by the wording in detail.
  - required_device: an @device name matching gaps.owned_but_undocumented substitutes the canonical id and rig display name; an unmatched name is carried free-form and is valid output, not an error.
  - required_manual: assembled with named placeholders inside the filename string and placeholders[] listing exactly the placeholder fields; absent altogether where the device does not resolve to a canonical id - tested against a fixture gaps report, since the live report is empty and the field is dormant, not removed (CONTRACTS 4e).
  - Blocked-by: f3kp019 (Implement ground.py and citation assembly)
  - Stream: 1
  - Requirements: [2.10](requirements.md#2.10), [4.9](requirements.md#4.9), [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [6.6](requirements.md#6.6), [6.7](requirements.md#6.7), [6.9](requirements.md#6.9), [6.10](requirements.md#6.10), [9.9](requirements.md#9.9)

- [ ] 21. Implement outcome.py and required_manual assembly <!-- id:f3kp021 -->
  - The fixed-order gate chain, the seven-member model enum validation, the unparsed-path coverage fallback, and the resolver against gaps.owned_but_undocumented.
  - Blocked-by: f3kp020 (Write tests for the outcome procedure and required_manual)
  - Stream: 1
  - Requirements: [2.10](requirements.md#2.10), [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [6.6](requirements.md#6.6), [6.10](requirements.md#6.10), [9.9](requirements.md#9.9)

## Phase 6: Providers, credentials and the state seam

- [ ] 22. Define the provider and StateSource seam types <!-- id:f3kp022 -->
  - provider/base.py: ProviderKind, SynthesisRequest, the Provider protocol (status/probe/stream) and the four-kind ProviderFailure - the design's Provider abstraction verbatim. stream() yields text deltas and nothing else, which is what makes 6.2 structural rather than a per-provider obligation (Decision 4).
  - requires_key is derived from the kind; max_words is fixed at 400 - 1.6's longer form has no transport in the MVP and the deferral is recorded in the design, so no request field is invented here.
  - state/base.py and state/null.py: StateValue as the flat (key, value, observed_at, origin, origin_kind) triple (Decision 7), StateSnapshot, the StateSource protocol, and NullStateSource returning an empty snapshot immediately - the flat shape is what admits LogTail and Als implementations without redefinition.
  - Interfaces plus a trivial null return - no behaviour to fail a test against, so no preceding test task; the null path's no-degradation guarantee is asserted in the turn-pipeline tests.
  - Blocked-by: f3kp001 (Scaffold the dawmans.answer package and the serve dependency group)
  - Stream: 2
  - Requirements: [6.1](requirements.md#6.1), [8.1](requirements.md#8.1), [8.3](requirements.md#8.3), [8.4](requirements.md#8.4), [8.5](requirements.md#8.5)

- [ ] 23. Write tests for the Anthropic provider <!-- id:f3kp023 -->
  - Settings pinned so a drift fails a test: thinking disabled with effort low, max_retries=0 - the SDK's default retries would apply their own backoff inside the 10 s window and make 6.8's retry-at-most-once unenforceable - and httpx timeout 30 s with 2 s connect so the engine's watchdog fires first and attributes the stall to the provider.
  - Rate-limit policy: a 429 with retry-after <= 3 s retries once after sleeping it; over 3 s surfaces the rate-limited failure carrying the value unrounded on both branches - rounding before the comparison would change which branch runs; absent where the provider stated none, and nothing is invented.
  - cache_control on the last system block; a selected model whose cache minimum the ~600-token prompt does not clear reports prompt_cache: unavailable rather than silently losing the cache.
  - Connection refused/DNS/TLS raise the unreachable kind; a 401 with a key present raises the auth kind, feeding 6.6's distinction; deltas stream via text_stream.
  - CI runs against a scripted SDK; the live Keychain read and a real-key call run on a developer machine only - see prerequisites.md.
  - Blocked-by: f3kp022 (Define the provider and StateSource seam types)
  - Stream: 2
  - Requirements: [6.7](requirements.md#6.7), [6.8](requirements.md#6.8)
  - References: specs/api/answer-engine/prerequisites.md

- [ ] 24. Implement provider/anthropic.py <!-- id:f3kp024 -->
  - AsyncAnthropic against claude-opus-5 with the settings table of design 'Anthropic provider specifics'; the single-retry rate-limit policy.
  - Verifying against the real API needs the Keychain key of prerequisites.md; nothing in CI does.
  - Blocked-by: f3kp023 (Write tests for the Anthropic provider)
  - Stream: 2
  - Requirements: [6.7](requirements.md#6.7), [6.8](requirements.md#6.8)
  - References: specs/api/answer-engine/prerequisites.md

- [ ] 25. Write tests for the local and shared-backend providers <!-- id:f3kp025 -->
  - Local: requires_key False and a configured keyless provider is a fully configured state - status() returns configured=True, credential=None, and nothing reports it as unconfigured or missing a credential.
  - Local: the client is constructed against a loopback base URL only, so no outbound network request occurs for the whole turn - 6.14 holds by construction, asserted with networking poisoned.
  - Shared backend: a stub behind the disclosure gate - selecting it returns requires_disclosure_ack: true and records nothing; a turn attempted before acknowledgement fails as provider-unconfigured with reason disclosure-unacknowledged.
  - The same scripted stream through each of the three provider classes yields the same envelope shape - streamed text, citations, timings, refusal signalling - because the one parser sits engine-side.
  - Blocked-by: f3kp022 (Define the provider and StateSource seam types)
  - Stream: 2
  - Requirements: [6.1](requirements.md#6.1), [6.2](requirements.md#6.2), [6.4](requirements.md#6.4), [6.14](requirements.md#6.14), [6.15](requirements.md#6.15)

- [ ] 26. Implement provider/local.py and provider/shared.py <!-- id:f3kp026 -->
  - OpenAI-compatible client on a loopback base URL; the shared-backend stub and its acknowledgement gate.
  - Blocked-by: f3kp025 (Write tests for the local and shared-backend providers)
  - Stream: 2
  - Requirements: [6.1](requirements.md#6.1), [6.2](requirements.md#6.2), [6.4](requirements.md#6.4), [6.14](requirements.md#6.14), [6.15](requirements.md#6.15)

- [ ] 27. Write tests for credential storage and masking <!-- id:f3kp027 -->
  - keyring under service dawmans, one account per provider kind; no key is written to any configuration file or environment variable (Decision 6) - keyring is stubbed, so state the CI limitation in the test rather than pretending the Keychain path runs.
  - Masking is structural: ProviderStatus carries masked: str | None and no field that can hold a full key; every read path returns the last-4 masked form or None, and the full value has exactly one reader - the provider's client constructor.
  - The logging.Filter backstop drops any record whose formatted output contains the stored secret; the raw key appears in no log record at any level, and the same predicate filters detail - no credential material, no stack trace, no raw provider payload, no path outside the two store roots.
  - Each provider constructs its own client against its own base URL; no shared send-the-key-to-the-configured-URL path exists for a misconfiguration to redirect.
  - Blocked-by: f3kp022 (Define the provider and StateSource seam types)
  - Stream: 2
  - Requirements: [6.11](requirements.md#6.11), [6.12](requirements.md#6.12), [6.13](requirements.md#6.13)

- [ ] 28. Implement provider/credentials.py and the logging filter <!-- id:f3kp028 -->
  - The keyring wrapper, the masked-only ProviderStatus, and the secret-dropping filter applied to log records and to detail.
  - Blocked-by: f3kp027 (Write tests for credential storage and masking)
  - Stream: 2
  - Requirements: [6.11](requirements.md#6.11), [6.12](requirements.md#6.12), [6.13](requirements.md#6.13)

## Phase 7: Conversation and the turn pipeline

- [ ] 29. Write tests for conversation state <!-- id:f3kp029 -->
  - Last 6 turns retained and used to interpret a follow-up; in-memory per process, gone on restart; starting a new conversation discards prior turns.
  - The carried scope persists until the caller changes it; a mid-conversation change applies from the next turn and passages from now-deselected sources are not retained.
  - Retrieval re-runs every turn: a narrowing answer re-retrieves with the original question plus the answer and never reuses the previous turn's passages unchanged.
  - Corpus-change pruning: a source removed from the corpus drops from the carried scope and is reported through scope_dropped rather than applied silently; none remaining yields no-sources-selected.
  - The per-symptom consecutive-narrowing counter increments across narrowing turns and resets on an answer - the mechanism 7.5 rides on.
  - Blocked-by: f3kp005 (Implement view.py)
  - Stream: 1
  - Requirements: [5.11](requirements.md#5.11), [7.4](requirements.md#7.4), [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.4](requirements.md#10.4), [10.5](requirements.md#10.5), [10.6](requirements.md#10.6), [10.7](requirements.md#10.7)

- [ ] 30. Implement conversation.py <!-- id:f3kp030 -->
  - History, carried scope, the narrowing counter, and the corpus-change scope prune.
  - Follow-up query assembly lives here: a turn answering a narrowing question retrieves with the original question plus the narrowing answer - the 7.4 construction the pipeline hands to retrieve.py, never a reuse of the previous turn's passages.
  - Blocked-by: f3kp029 (Write tests for conversation state)
  - Stream: 1
  - Requirements: [5.11](requirements.md#5.11), [7.4](requirements.md#7.4), [10.1](requirements.md#10.1), [10.4](requirements.md#10.4), [10.5](requirements.md#10.5), [10.6](requirements.md#10.6), [10.7](requirements.md#10.7)

- [ ] 31. Write tests for the turn pipeline <!-- id:f3kp031 -->
  - Retrieval runs under asyncio.to_thread gathered with StateSource.snapshot under wait_for(0.100) - synchronous numpy work in a bare coroutine would never yield, the state task would not be scheduled, and the timeout could not fire; assert state is acquired concurrently, not serially.
  - A state failure, timeout or malformed snapshot degrades the turn to manual-only with a note and never fails it; with the null source there is no degradation in latency, citation quality or refusal behaviour.
  - The 10 s first-token watchdog abandons the turn naming the provider; cancellation stops streaming and releases the provider within 250 ms - a close, not a drain; cancellation property - for any stream prefix, cancelling yields cancelled, retains the partial, and emits nothing after done.
  - A new question on a conversation still streaming cancels the in-flight turn, reports it cancelled, then begins the new one - no interleaving, no queue.
  - A provider change applies to the next turn without restart and without invalidating the view or retrieval state; with no provider configured, passage lookup still works; no provider error substitutes a synthesised or cached answer - there is no answer cache at all; a mid-stream failure marks the turn incomplete and retains what streamed.
  - timings records retrieval, state acquisition, engine overhead, first token and completion as durations only.
  - A question spanning two selected sources synthesises one answer citing both, with the small guide represented under the floor.
  - contributing_sources[] equals the set of source_id over supplied and is reported with every answer - supplied-derived, never citation-derived (design 'contributing_sources[]').
  - Blocked-by: f3kp015 (Implement prompt.py), f3kp021 (Implement outcome.py and required_manual assembly), f3kp022 (Define the provider and StateSource seam types), f3kp030 (Implement conversation.py)
  - Stream: 1
  - Requirements: [4.4](requirements.md#4.4), [4.9](requirements.md#4.9), [4.10](requirements.md#4.10), [4.11](requirements.md#4.11), [5.7](requirements.md#5.7), [5.9](requirements.md#5.9), [6.3](requirements.md#6.3), [6.5](requirements.md#6.5), [6.9](requirements.md#6.9), [6.10](requirements.md#6.10), [8.2](requirements.md#8.2), [8.8](requirements.md#8.8), [8.9](requirements.md#8.9), [9.13](requirements.md#9.13)

- [ ] 32. Implement the turn pipeline <!-- id:f3kp032 -->
  - src/dawmans/answer/turn.py - the design's Module placement list names no pipeline module, so it is pinned here rather than landing ad hoc in http/app.py; the gather, the gates, prompt assembly, the provider call with watchdog and cancellation, the parser pass, the grounding check, and timings.
  - Emits contributing_sources[] as the set of source_id over supplied on every answer (5.9).
  - Blocked-by: f3kp031 (Write tests for the turn pipeline)
  - Stream: 1
  - Requirements: [4.4](requirements.md#4.4), [4.9](requirements.md#4.9), [4.10](requirements.md#4.10), [4.11](requirements.md#4.11), [5.9](requirements.md#5.9), [6.3](requirements.md#6.3), [6.5](requirements.md#6.5), [8.8](requirements.md#8.8), [8.9](requirements.md#8.9), [9.13](requirements.md#9.13)

## Phase 8: The local HTTP surface

- [ ] 33. Write tests for binding and the loopback guard <!-- id:f3kp033 -->
  - A configured non-loopback bind exits non-zero naming the address and the constraint; there is no fallback bind; the service listens on loopback only.
  - Host: evil.example is 403 - the Host check is what closes DNS rebinding, since a hostname resolving to 127.0.0.1 reaches the socket carrying the attacker's Host; Origin: null (a file:// page) is 403; 127.0.0.1, localhost and [::1] with the port pass.
  - A cross-port Origin: http://localhost:5173 is 403 - what the dev proxy's Origin rewrite exists to avoid, and what a same-port-only test would miss.
  - The 403 is machine-readable with no outcome field: a request rejection, not a turn.
  - Blocked-by: f3kp001 (Scaffold the dawmans.answer package and the serve dependency group)
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1), [9.2](requirements.md#9.2), [9.3](requirements.md#9.3)

- [ ] 34. Implement http/guard.py and the bind check <!-- id:f3kp034 -->
  - The Host/Origin middleware and the pre-uvicorn loopback address check.
  - Blocked-by: f3kp033 (Write tests for binding and the loopback guard)
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1), [9.2](requirements.md#9.2), [9.3](requirements.md#9.3)

- [ ] 35. Write tests for fetch-passage, list-sources and the gap relay <!-- id:f3kp035 -->
  - GET /passages/{id} is a dict lookup routed on the source_id prefix; an unknown id, or one whose source is no longer in the corpus, returns a 404 not-found body and never a substitute; the route runs the same stat change check as a turn, so a passage removed by a re-ingest stops resolving immediately rather than at the next question.
  - GET /sources returns, for every source of both kinds: source_id, display_name, kind, doc_version where the kind carries one, and hardware_applicability including confirmed/assumed - a field this operation omits reaches nobody.
  - Both gap reports are relayed alongside, never derived: owned-but-undocumented returned as an empty list rather than omitted - it is the sole resolver of a canonical device id and refills the day a device is declared ahead of its manual; documented-but-unconfirmed names the assumed APC guide.
  - An unreadable new manifest is reported here while the live view keeps serving; no filesystem path appears in any payload.
  - Blocked-by: f3kp005 (Implement view.py), f3kp034 (Implement http/guard.py and the bind check)
  - Stream: 1
  - Requirements: [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [9.5](requirements.md#9.5), [9.6](requirements.md#9.6), [9.7](requirements.md#9.7)

- [ ] 36. Implement the passage and sources routes <!-- id:f3kp036 -->
  - GET /passages/{passage_id} and GET /sources with both gap reports on http/app.py.
  - Blocked-by: f3kp035 (Write tests for fetch-passage, list-sources and the gap relay)
  - Stream: 1
  - Requirements: [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [9.5](requirements.md#9.5), [9.6](requirements.md#9.6), [9.7](requirements.md#9.7)

- [ ] 37. Write tests for the provider configuration routes <!-- id:f3kp037 -->
  - GET /provider, PUT /provider, PUT and DELETE /provider/credential, POST /provider/test: every response carries at most the masked form; the raw key appears in no response body and no log record from any of these operations.
  - PUT /provider to shared-backend returns requires_disclosure_ack: true and records nothing; test-provider reports reachability without synthesising a turn.
  - Question, answer and passage text log at DEBUG only; credentials at no level.
  - Blocked-by: f3kp028 (Implement provider/credentials.py and the logging filter), f3kp034 (Implement http/guard.py and the bind check)
  - Stream: 1
  - Requirements: [9.4](requirements.md#9.4), [9.8](requirements.md#9.8), [9.11](requirements.md#9.11)

- [ ] 38. Implement the provider routes <!-- id:f3kp038 -->
  - The five provider operations on http/app.py, masked-only throughout.
  - Blocked-by: f3kp037 (Write tests for the provider configuration routes)
  - Stream: 1
  - Requirements: [9.4](requirements.md#9.4), [9.8](requirements.md#9.8), [9.11](requirements.md#9.11)

- [ ] 39. Write tests for serve-document <!-- id:f3kp039 -->
  - A known vendor-manual returns its PDF inline - Content-Type application/pdf, no Content-Disposition filename (an attachment disposition downloads the file and silently defeats #page=N), Range honoured so a 96 MB manual pages without being fetched whole.
  - An authored-triage id, an unknown id and a renamed file each 404, so the caller degrades the citation to its string form rather than a broken action; no request body or path parameter can reach the filesystem - the loaded index is the allowlist - and a realpath outside the manuals root is refused.
  - Filename round-trip: for every ingested vendor-manual, rebuilding `<vendor>_<product>_<doctype>_v<doc_version>_<lang>.pdf` from its SourceRecord fields names the ingested file - doc_version arrives without the leading v, so there is one reconstruction rule and no `_vv1.0_`.
  - The route streams bytes and parses nothing, so the PyMuPDF confinement test still passes.
  - Blocked-by: f3kp036 (Implement the passage and sources routes)
  - Stream: 1
  - Requirements: [9.4](requirements.md#9.4)

- [ ] 40. Implement the serve-document route <!-- id:f3kp040 -->
  - GET /sources/{source_id}/document: resolve against sources.json, rebuild the filename, realpath-confine to the manuals root, stream with Range.
  - Blocked-by: f3kp039 (Write tests for serve-document)
  - Stream: 1
  - Requirements: [9.4](requirements.md#9.4)

- [ ] 41. Write tests for the turn stream <!-- id:f3kp041 -->
  - POST /turn streams SSE over the POST response (EventSource cannot POST); stream completeness property - every envelope field the engine produced is carried by exactly one of the sixteen CONTRACTS 4b events, no event outside that set is emitted, and done occurs exactly once carrying {"complete": true} - a payload-free terminator is never dispatched by a conforming reader and a completed turn would be indistinguishable from a truncated one.
  - Ordering: scope_dropped before outcome; outcome before every other event; direct_answer before the first body_delta, so 1.8 holds on the wire; cause events in rank order; ungrounded after the last body_delta; done last.
  - dawmans/turn-stream/1 is declared in a response header readable before the first body byte.
  - Body deltas arrive incrementally as the scripted provider emits them, never withheld until synthesis completes; a caller disconnect mid-stream is treated as cancellation.
  - A 1001-character question is rejected with HTTP 422 and {"rejected": "question-too-long", "limit": 1000, "received": N} - no outcome field, no envelope, no truncation: no turn was started and the taxonomy does not describe it.
  - The static mount serves web/build at / so the surface is same-origin - listed here because ui/ask-and-source-picker depends on it.
  - Blocked-by: f3kp032 (Implement the turn pipeline), f3kp034 (Implement http/guard.py and the bind check)
  - Stream: 1
  - Requirements: [1.8](requirements.md#1.8), [4.5](requirements.md#4.5), [9.10](requirements.md#9.10), [9.12](requirements.md#9.12), [9.14](requirements.md#9.14), [9.15](requirements.md#9.15)

- [ ] 42. Implement POST /turn and the SSE emitter <!-- id:f3kp042 -->
  - The request validator, the SSE event writer for the CONTRACTS 4b set, the version header, and the static mount.
  - Blocked-by: f3kp041 (Write tests for the turn stream)
  - Stream: 1
  - Requirements: [4.5](requirements.md#4.5), [9.10](requirements.md#9.10), [9.12](requirements.md#9.12), [9.14](requirements.md#9.14), [9.15](requirements.md#9.15)

## Phase 9: End-to-end, serve wiring and timing

- [ ] 43. Write end-to-end tests over a synthetic view and scripted providers <!-- id:f3kp043 -->
  - Startup order: manifest read, view load, model loaded and warmed with a throwaway encode, bind last - a listener that accepts before the warm promises a budget it cannot meet, and the 7.2 s cold load must not be paid on the first question.
  - One turn per content outcome against scripted streams: answered with citations from both kinds carrying kind, doc_version and applicability; a conflict rendered as !conflict with both readings and separate citations; a partial answer naming uncovered_parts; a refusal with up to 3 suggestions; out-of-domain with suggestions suppressed; no-manual-for-device with required_device and required_manual against a fixture gaps report; the narrowing entry path run to the limit and terminating in ranked-causes whose direct_answer states the rank-1 check as an instruction.
  - contributing_sources[] is the set of source_id over supplied, reported with every answer.
  - Corpus swap mid-conversation: the view is discarded before the next turn retrieves, a removed source drops from the carried scope with a scope_dropped event, and removing the last one yields no-sources-selected.
  - Blocked-by: f3kp038 (Implement the provider routes), f3kp040 (Implement the serve-document route), f3kp042 (Implement POST /turn and the SSE emitter)
  - Stream: 1
  - Requirements: [1.4](requirements.md#1.4), [2.1](requirements.md#2.1), [2.2](requirements.md#2.2), [2.3](requirements.md#2.3), [2.9](requirements.md#2.9), [2.10](requirements.md#2.10), [5.9](requirements.md#5.9), [5.10](requirements.md#5.10), [5.11](requirements.md#5.11), [7.1](requirements.md#7.1), [7.5](requirements.md#7.5), [7.6](requirements.md#7.6)

- [ ] 44. Implement dawmans serve and the startup wiring <!-- id:f3kp044 -->
  - The serve subcommand on cli.py: configuration (port, manuals root), the four-step startup order, uvicorn bound after the warm.
  - Blocked-by: f3kp024 (Implement provider/anthropic.py), f3kp026 (Implement provider/local.py and provider/shared.py), f3kp043 (Write end-to-end tests over a synthetic view and scripted providers)
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1)

- [ ] 45. Add the timing tests and the bench target <!-- id:f3kp045 -->
  - 4.2 (retrieval <= 10 ms median, <= 50 ms p95) and 4.3 (engine overhead <= 150 ms p95 with a stub provider) run in CI against a synthetic 1,200-chunk index; the overhead cap excludes retrieval and state acquisition, each measured against its own budget, or the cap would be consumed before any engine work began.
  - 4.1 and 4.6-4.8 need a real provider and a real index: `make bench`, skipped when either is absent - the same honest limitation the sibling specs accept for their full-corpus budgets.
  - A narrowing question is measured against the same first-token target for the provider class, never against a completion target that would have to precede it.
  - `make bench` also calibrates Decision 8's history-token margin: compare the resident BGE tokeniser's counts against the provider's count_tokens over sample prompts and report whether the configured 10% covers the observed divergence - the margin is a guess until this runs.
  - The real-provider and real-index runs need the Keychain key and an ingested corpus - see prerequisites.md.
  - Blocked-by: f3kp044 (Implement dawmans serve and the startup wiring)
  - Stream: 1
  - Requirements: [4.1](requirements.md#4.1), [4.2](requirements.md#4.2), [4.3](requirements.md#4.3), [4.6](requirements.md#4.6), [4.7](requirements.md#4.7), [4.8](requirements.md#4.8), [7.3](requirements.md#7.3)
  - References: specs/api/answer-engine/prerequisites.md
