# Requirements: Answer Engine

**Domain:** `api` · **Capability:** answer-engine · **Status:** draft

## Purpose

The answer engine is the middle layer of DAWMans. It takes a question plus a caller-supplied
set of in-scope sources, retrieves grounded passages from the ingested manual corpus,
synthesises a cited answer through a pluggable LLM provider, and exposes that over a
localhost-only HTTP interface.

It is used by one person, on one machine, in a browser tab on a second screen while they are
producing music. **Speed is the headline property**: an answer that arrives after the user has
context-switched back to the DAW has failed even if it is correct.

## Scope boundaries

This spec owns: retrieval over already-ingested chunks, grounding and refusal behaviour,
citation assembly, provider abstraction and credential handling, the `StateSource` seam, and the
local HTTP contract.

It does **not** own:

- **PDF ingestion, chunking, section/page metadata extraction** — owned by
  [`data/manual-corpus`](../../data/manual-corpus/requirements.md). This spec consumes its output
  and its criteria are not restated here.
- **The content, structure and validation of the authored triage source** — owned by
  [`data/symptom-triage`](../../data/symptom-triage/requirements.md). This spec retrieves and cites
  its entries through the same `Passage` and `Citation` records as any manual, and does not restate
  what an entry must contain.
- **Any browser surface** — owned by
  [`ui/ask-and-source-picker`](../../ui/ask-and-source-picker/requirements.md). This spec defines
  what that surface can call, not how it looks or behaves.

## Terms

| Term | Meaning |
|---|---|
| **Source** | One ingested source of either kind (`CONTRACTS.md` §4a), identified by a stable source ID: a vendor manual (Live 12 reference manual, APC Key 25 user guide, Alesis Nitro Max user guide) or the authored triage source. |
| **Source kind** | What a source *is*, and therefore what it is trusted for: `vendor-manual` or `authored-triage` (`CONTRACTS.md` §4a). Kind is carried on every source and every citation ([1.13](#1.13), [3.8](#3.8)). |
| **Triage entry** | One symptom-to-cause record in an `authored-triage` source: candidate causes ranked by likelihood, the observable check that confirms or eliminates each, and where present a vendor-manual pointer for the fix. Retrieved and cited as an ordinary passage. |
| **Selected sources** | The subset of sources the caller has put in scope for a given question. Only these may ground the answer. |
| **Passage** | A retrieved chunk carrying source ID, section number, section title, page number, flags for unrepairable characters and for figures in the section, the `unbacked` marking of an authored cause resting on no manual, and, where the passage declares one, the devices it applies to. A pageless source's passages carry no section number and no page (`CONTRACTS.md` §2). |
| **Citation** | A reference from a claim in the answer to the passage that supports it, carrying the passage's location *and* the source's kind, document version and hardware applicability ([3.2](#3.2)–[3.3](#3.3), [3.8](#3.8)). |
| **Provider kind** | What the LLM backend is, and therefore whether it needs a credential: **keyed hosted**, **local**, or **shared backend** ([6.4](#6.4)). |
| **Answer envelope** | The record returned for a turn (`CONTRACTS.md` §4): outcome, `direct_answer`, `body`, `citations[]`, `contributing_sources[]`, `uncovered_parts[]` ([2.2](#2.2)), `timings` ([4.11](#4.11)), and any narrowing, `required_device` or `ungrounded` signal. |
| **Rig inventory** | The declared list of hardware the user owns, held by `data/manual-corpus` (its §11) separately from the corpus inventory of what is indexed. This spec neither owns nor derives it; it relays the two gap reports computed over it ([9.6](#9.6), [9.7](#9.7)). |
| **Device scope** | The devices and software a turn is asked about, derived from the selected sources and the rig inventory ([5.12](#5.12)), against which a passage's own device declaration is tested ([5.13](#5.13)). |
| **Session state** | Optional, out-of-band knowledge of the user's live or saved DAW project, supplied through the `StateSource` seam. |
| **Turn** | One question-and-answer exchange within a conversation. |

---

## Requirements

### 1. Grounded Question Answering and Answer Shape

**User Story:** As a producer mid-session, I want an answer built from what my manuals actually
say, so that I can act on it without second-guessing whether the tool made it up.

**Acceptance Criteria:**

1. <a name="1.1"></a>WHEN the system receives a question and a non-empty set of selected sources,
   the system SHALL retrieve passages only from those sources and SHALL synthesise the answer
   using only the retrieved passages as factual content.
2. <a name="1.2"></a>The system SHALL NOT introduce product facts, parameter names, menu paths, key
   commands or numeric values that do not appear in the retrieved passages.
3. <a name="1.3"></a>The system SHALL pass no more than 12 passages to synthesis for a single turn,
   and SHALL rank them by relevance to the question before truncation, subject to the source
   inclusion floor in [5.6](#5.6), which takes precedence over this cap.
4. <a name="1.4"></a>WHEN retrieved passages conflict with one another, the system SHALL present
   both readings with their separate citations rather than silently selecting one.
5. <a name="1.5"></a>WHERE the question asks for a procedure, the system SHALL express the answer as
   ordered steps, each step traceable to at least one retrieved passage.
6. <a name="1.6"></a>The system SHALL cap a synthesised answer at 400 words unless the caller
   requests a longer form, so that the latency budget in §4 remains achievable.
7. <a name="1.7"></a>The system SHALL make no outbound network request to perform retrieval;
   retrieval SHALL operate wholly on locally held corpus data.
8. <a name="1.8"></a>The system SHALL return every answer as an answer envelope carrying a distinct
   `direct_answer` — the actionable answer itself — and SHALL emit `direct_answer` before any
   qualification, caveat, restatement of the question or supporting context in the stream.
9. <a name="1.9"></a>The `direct_answer` SHALL reach its first actionable instruction within 25
   words, so that the caller can render an instruction the user can act on without scrolling.
10. <a name="1.10"></a>The system SHALL carry the remainder of the answer in a `body` bearing
    machine-identifiable structure — headings, ordered steps and key terms — such that the caller can
    identify each without applying heuristics to prose.
11. <a name="1.11"></a>The system SHALL declare, in its response, the text format of `direct_answer`
    and `body`, and SHALL use one declared format for every provider and every outcome.
12. <a name="1.12"></a>WHEN an answer's recommended course of action depends on a Live edition or
    add-on the user does not have — a Suite-only device, or a Max for Live feature under Live 12
    Standard — the system SHALL flag that dependency in the answer, since the recommendation is
    manual-accurate and unusable on the declared rig.
13. <a name="1.13"></a>The system SHALL treat a `vendor-manual` source as authoritative for what a
    control **is** and **does**, and an `authored-triage` source as authoritative for **which
    documented control to check, and in what order**, for a given symptom (`CONTRACTS.md` §4a). The
    system SHALL NOT present a causal claim drawn from an `authored-triage` source as though the
    manufacturer had stated it, and SHALL NOT treat an authored entry as evidence of a control's
    behaviour where no vendor passage states it. Where an entry names a fix, the fact behind the fix
    SHALL still carry its vendor-manual citation ([3.1](#3.1)). WHERE a cause is marked `unbacked` —
    no vendor passage backs it, because the device has no ingested manual or the pointer has stopped
    resolving (`CONTRACTS.md` §2) — the system SHALL carry that marking through to the citation
    ([3.3](#3.3)) rather than presenting the fix as documented.

### 2. Honest Refusal, Out-of-Domain and Source Suggestion

**User Story:** As a producer, I want the tool to tell me it does not know, so that I never act on a
confident answer that is wrong — a wrong answer about gain staging costs me more than no answer.

**Acceptance Criteria:**

1. <a name="2.1"></a>WHEN no retrieved passage from the selected sources supports an answer, the
   system SHALL state plainly that the selected sources do not cover the question and SHALL NOT
   produce a speculative answer.
2. <a name="2.2"></a>WHEN the retrieved passages support only part of the question, the system SHALL
   answer the supported part with citations and SHALL name every part that is not covered in
   `uncovered_parts[]` on the answer envelope (`CONTRACTS.md` §4), so that the caller renders the
   gap subordinate to the answer rather than as a refusal.
3. <a name="2.3"></a>WHEN the system refuses under [2.1](#2.1) or partially refuses under
   [2.2](#2.2), the system SHALL name up to 3 unselected sources whose content is likely to hold
   the answer, ordered by likelihood.
4. <a name="2.4"></a>WHEN naming an unselected source under [2.3](#2.3), the system SHALL NOT quote,
   paraphrase or otherwise use that source's content in the answer.
5. <a name="2.5"></a>IF no unselected source is a plausible holder of the answer, THEN the system
   SHALL say that no ingested manual appears to cover the question rather than suggesting a source
   at random, unless [2.9](#2.9) or [2.10](#2.10) applies.
6. <a name="2.6"></a>The system SHALL NOT state a product fact — behaviour, parameter name, menu
   path, key command or numeric value — that is not carried by a retrieved passage, under any
   condition, including when the user asks it to. This constraint governs **facts**. Deciding
   **which documented control to check**, and in what order, is reasoning over cited facts: it is
   permitted, it is required by [7.2](#7.2), and it SHALL NOT be treated as general knowledge. The
   reasoning SHALL rest only on cited facts, and every fact it rests on SHALL carry its citation.
7. <a name="2.7"></a>WHEN the highest-ranked retrieved passage falls below the configured relevance
   threshold, the system SHALL treat the question as uncovered per [2.1](#2.1) rather than
   synthesising from weak matches.
8. <a name="2.8"></a>The system SHALL judge retrieved passages on whether they are responsive to the
   question's intent, not on topical similarity alone, and SHALL NOT synthesise an answer from
   passages that score highly yet answer a different question — a question about why a recorded kick
   is distorting retrieves Saturator, Drum Buss and Overdrive, devices that produce distortion
   deliberately and are not responsive to it. This guard operates independently of [2.7](#2.7),
   which does not catch passages that score highly. WHERE an `authored-triage` entry matches the
   symptom, that entry SHALL outrank topically-similar control documentation for a diagnostic
   question: the entry names the cause, while the device passage merely shares its vocabulary.
9. <a name="2.9"></a>WHEN a question asks how to achieve a production outcome rather than what a
   documented control does — a technique question, not a control question — AND **neither** a
   vendor manual **nor** an `authored-triage` entry covers it, the system SHALL return an
   out-of-domain result stating plainly that the ingested sources document what controls do and not
   what constitutes good practice, and SHALL suppress the source suggestion in [2.3](#2.3), because
   no reference manual in the corpus will ever cover it. This outcome exists because no vendor
   manual documents practice; IF an `authored-triage` entry does cover the question, the system
   SHALL answer from that entry under [1.1](#1.1) and SHALL NOT return out-of-domain, which would
   refuse a question its own corpus answers.
10. <a name="2.10"></a>WHEN a question is answerable from documentation but that documentation is
    for a device with **neither** an ingested manual **nor** `authored-triage` coverage, the system
    SHALL return a no-manual-for-device result and SHALL populate `required_device` naming the
    **device** whose documentation is needed — for example the audio interface whose
    direct-monitoring switch governs monitoring latency. This names a device, not an ingested source
    ID, and it takes precedence over [2.5](#2.5), which otherwise terminates with no path forward.
    An `authored-triage` entry may legitimately cover a device whose manual is absent — an entry may
    direct the user to check DIRECT MONITOR on the Focusrite Scarlett Solo without quoting
    Focusrite — and WHERE such an entry answers the question, the system SHALL answer from it and
    SHALL NOT return no-manual-for-device. WHERE the entry narrows the question but the remaining
    fix needs the absent manual, the system SHALL answer what the entry supports and name the
    uncovered part per [2.2](#2.2).

### 3. Citations and Passage Retrieval

**User Story:** As a producer, I want every claim tied to a page I can open, so that I can verify it
or read around it when the answer is not quite the case I am in.

**Acceptance Criteria:**

1. <a name="3.1"></a>The system SHALL attach at least one citation to every substantive claim in an
   answer, where a substantive claim is any statement of product behaviour, setting, value or
   procedure step.
2. <a name="3.2"></a>Each citation SHALL carry the source ID, display name, section number, section
   title, page number and a stable passage identifier, sufficient for the caller to render a
   reference such as "Live 12 §24.9 p400". WHERE the source is pageless — an `authored-triage`
   source has neither section numbering nor pages (`CONTRACTS.md` §2, §3) — the system SHALL emit
   the section number and the page as **absent**, SHALL NOT synthesise either, and SHALL NOT
   withhold the citation for lacking them; the section title, which is the entry's symptom
   statement, occupies the location slot the section and page would otherwise fill.
3. <a name="3.3"></a>Each citation SHALL additionally carry the `doc_version` of the source, its
   `hardware_applicability` — including whether that applicability is confirmed or assumed — the
   `degraded` and `has_figures` flags of the cited passage, and its `unbacked` flag, which marks an
   authored cause resting on no vendor-manual passage (`CONTRACTS.md` §2, [1.13](#1.13)). These are
   produced upstream and every one of them is rendered by the caller; the system SHALL NOT drop
   them. `doc_version` is load-bearing: it is the sole mitigation for a document that describes a
   different hardware revision from the one the user owns, and the mitigation only works if the
   version reaches the user with the claim. A pageless source carries no `doc_version`
   (`CONTRACTS.md` §3), which SHALL be emitted as absent rather than substituted.
4. <a name="3.4"></a>The system SHALL expose an operation that returns the full text of a cited
   passage given its passage identifier, in under 50 ms at p95.
5. <a name="3.5"></a>WHEN a passage identifier is unknown or refers to a source no longer in the
   corpus, the system SHALL return a not-found result and SHALL NOT return a substitute passage.
6. <a name="3.6"></a>The system SHALL NOT emit a citation that does not resolve to a passage
   supplied to synthesis for that turn.
7. <a name="3.7"></a>WHEN a synthesised answer contains a substantive claim with no resolvable
   citation, the system SHALL set an `ungrounded` signal after streaming completes and before the
   turn is reported complete, so that the caller marks an answer it has already rendered. Because
   the answer is streamed as it is synthesised ([4.5](#4.5)), the text is on screen before the check
   can run; withholding it is not available, and the signal SHALL NOT be deferred past the turn's
   completion.
8. <a name="3.8"></a>Each citation SHALL additionally carry the **kind** of the source it is drawn
   from — `vendor-manual` or `authored-triage` (`CONTRACTS.md` §4a). The corpus produces it and the
   caller renders it **inline, never behind a disclosure** (`CONTRACTS.md` §3), so that a causal
   claim resting on the user's own note is never presented as a manufacturer's statement
   ([1.13](#1.13)). Kind changes what the citation *asserts*, not how it is assembled: an authored
   citation carries the same fields as any other ([3.2](#3.2)), with the pageless ones absent, and
   is subject to the same resolution rules ([3.6](#3.6)).

### 4. Latency

**User Story:** As a producer with a track playing, I want the answer to start appearing almost
immediately, so that asking costs me less attention than reaching for the manual.

**Budget and justification.** The reference corpus is ~1068 pages / ~330k tokens of vendor manuals
plus the authored triage source, whose entries are passages retrieval scans on every turn like any
other — small enough, at both kinds together, that retrieval is a local, in-memory operation and
should never be the bottleneck. Essentially all wall-clock time therefore belongs to the provider. Stage budgets are stated so that
they **compose into the only figure the user experiences** — keypress to first painted token — rather
than at an engine boundary that quietly excludes transport and render:

| Stage | p95 |
|---|---|
| Retrieval ([4.2](#4.2)) | 50 ms |
| Session state acquisition ([4.4](#4.4)) — **excluded** from the overhead cap | 100 ms |
| Engine overhead: prompt assembly, citation resolution, framing, stream setup ([4.3](#4.3)) | 150 ms |
| Provider time to first token ([4.6](#4.6), [4.7](#4.7)) | 1.2 s hosted / 2.5 s local |
| Transport and paint (owned by `ui/ask-and-source-picker`) | 100 ms |
| **Keypress → first painted token ([4.1](#4.1))** | **1.5 s hosted / 2.8 s local** |

The perceived-speed target is first token, not completion. "Under ~1 s reads as instant" is not a
claim this spec can make: measured at the engine boundary it excludes transport and paint, and with a
hosted provider in the path it is unreachable. The honest composed target is **1.5 s hosted**, and
what preserves the sense of immediacy from there is streaming ([4.5](#4.5)) — an answer that begins
at 1.5 s and continues reads faster than a complete one delivered in a block at 4 s. Past ~10 s the
user has already switched back to the DAW, which is why completion is capped and answers are
length-limited ([1.6](#1.6)). The engine's own share is held to 150 ms so that a slow answer is
always attributable to the provider and diagnosable as such.

**Acceptance Criteria:**

1. <a name="4.1"></a>The system SHALL deliver its first token to the caller in time for the caller to
   paint it within 1.5 s at p95 on a hosted provider and 2.8 s at p95 on a local provider, measured
   from the keypress that submits the question, allowing 100 ms at p95 for transport and paint by
   `ui/ask-and-source-picker`. Every other budget in this section is a stage of this one.
2. <a name="4.2"></a>The system SHALL complete retrieval — question received to ranked passages
   selected — in ≤ 10 ms median and ≤ 50 ms at p95, measured on the reference machine over the
   full reference corpus, both source kinds included: the authored triage source's entries are
   scanned within this budget, not alongside it.
3. <a name="4.3"></a>The system SHALL keep engine-side overhead per turn — prompt assembly, citation
   resolution, framing and stream setup — at ≤ 150 ms at p95. This cap EXCLUDES retrieval
   ([4.2](#4.2)) and session state acquisition ([4.4](#4.4)), which carry their own budgets; were
   either counted against it, the cap would be fully consumed before any engine work began.
4. <a name="4.4"></a>The system SHALL complete session state acquisition within 100 ms at p95, and
   SHALL acquire state concurrently with retrieval so that it does not extend the composed budget in
   [4.1](#4.1). Enforcement of the bound is [8.9](#8.9).
5. <a name="4.5"></a>The system SHALL stream the answer to the caller incrementally as it is
   synthesised, rather than withholding it until synthesis completes.
6. <a name="4.6"></a>WHEN a hosted provider is configured and reachable, the system SHALL emit the
   first answer token within 1.2 s at p95, measured from the provider call being issued.
7. <a name="4.7"></a>WHERE a local provider is configured, the first-token target SHALL be 2.5 s at
   p95 on the same measure, recognising that local inference trades latency for privacy and zero
   marginal cost.
8. <a name="4.8"></a>The system SHALL deliver a complete answer within 6 s at p95 for a hosted
   provider and 15 s at p95 for a local provider.
9. <a name="4.9"></a>IF no first token has been emitted within 10 s, THEN the system SHALL abandon
   the turn and return a timeout result naming the provider as the stalled component.
10. <a name="4.10"></a>The system SHALL allow the caller to cancel an in-flight turn, and SHALL stop
    streaming and release provider resources within 250 ms of the cancellation.
11. <a name="4.11"></a>The system SHALL record per-turn timings for retrieval, state acquisition,
    engine overhead, first token and completion, and SHALL expose them to the caller as `timings` on
    the answer envelope (`CONTRACTS.md` §4) so latency regressions are observable without
    instrumenting the provider.

### 5. Source Scoping

**User Story:** As a producer, I want to choose which manuals a question is asked against, so that I
can exclude noise from the 1009-page Live manual when the question is really about my controller.

**Acceptance Criteria:**

1. <a name="5.1"></a>The system SHALL accept an explicit set of selected source IDs with every
   question and SHALL treat that set as the complete grounding scope for that turn.
2. <a name="5.2"></a>WHEN the selected set is empty, the system SHALL decline to answer, SHALL state
   that at least one source must be selected, and SHALL NOT fall back to all sources or to model
   general knowledge. This path is defence in depth and is expected to be unreachable in normal
   operation, because `ui/ask-and-source-picker` never submits an empty scope; it is retained so
   that a defect in the caller cannot silently widen the grounding scope.
3. <a name="5.3"></a>WHEN the selected set names a source ID that is not in the corpus, the system
   SHALL return an error identifying the unknown ID and SHALL NOT silently drop it.
4. <a name="5.4"></a>WHEN exactly one source is selected, the system SHALL answer or refuse entirely
   within that source, applying the suggestion behaviour in [2.3](#2.3) on refusal.
5. <a name="5.5"></a>WHEN more than one source is selected, the system SHALL rank passages across
   all selected sources on relevance alone and SHALL NOT weight a source by its page count or chunk
   count.
6. <a name="5.6"></a>WHERE a selected source contains at least one passage above the relevance
   threshold, the system SHALL include at least one of that source's passages in the set supplied to
   synthesis, so that a 5-page guide is not drowned by a 1009-page manual. This floor takes
   precedence over the 12-passage cap in [1.3](#1.3): WHEN the number of qualifying sources exceeds
   the cap, the system SHALL raise the cap to one passage per qualifying source and SHALL admit no
   further passages beyond that. The caller may put 12–16 sources in scope at once, so the two rules
   collide in ordinary use and the precedence SHALL NOT be left to implementation.
7. <a name="5.7"></a>WHEN a question spans two selected sources — for example record-arming a track
   from the controller, which needs both the controller guide and the Live manual — the system SHALL
   synthesise a single answer citing both sources rather than answering from whichever ranks highest.
8. <a name="5.8"></a>WHEN all sources are selected, the system SHALL apply the same ranking and
   inclusion rules as any other multi-source selection, with no special-case behaviour.
9. <a name="5.9"></a>The system SHALL report, alongside each answer, which selected sources actually
   contributed passages. This report is rendered by `ui/ask-and-source-picker` and is not
   diagnostic-only output: it is how the user notices that a question about the controller was
   answered from the Live manual, and that the controller guide contributed nothing.
10. <a name="5.10"></a>WHEN the corpus changes while the system is running — a source added, removed
    or re-ingested — the system SHALL detect the change before the next turn retrieves, and SHALL
    discard any cached retrieval state derived from the previous corpus, so that no answer is
    grounded in passages that no longer exist.
11. <a name="5.11"></a>WHEN a corpus change removes a source that a conversation is carrying forward
    in its scope ([10.4](#10.4)), the system SHALL drop that source from the carried scope, SHALL
    report the drop to the caller rather than applying it silently, and SHALL answer from the
    remaining sources — or, IF none remain, decline per [5.2](#5.2).
12. <a name="5.12"></a>The system SHALL derive a **device scope** for each turn from the selected
    source IDs: the devices and software the selected sources document, together with every
    owned-but-undocumented device in the rig inventory ([9.6](#9.6)). The undocumented devices are
    included deliberately — a triage passage naming DIRECT MONITOR on the Focusrite Scarlett Solo
    must stay reachable although no Focusrite source is selectable ([2.10](#2.10)).
13. <a name="5.13"></a>WHERE a retrieved passage declares the devices or software it applies to, the
    system SHALL **exclude it from the turn entirely** — filter, not merely rank lower — WHEN none
    of its declared devices is in the turn's device scope ([5.12](#5.12)). A passage that declares
    no devices is scoped by its source alone per [5.1](#5.1). Source selection alone is not
    sufficient scope for such a passage: `data/symptom-triage` registers every authored entry as one
    source (its 3.1) while requiring an entry to be unretrievable for a turn none of its declared
    devices is in scope (its 4.3), so selecting the triage source SHALL NOT put every entry in
    scope. Among passages that survive the filter, closeness of device match MAY inform ranking
    under [5.5](#5.5), but SHALL NOT be used in place of the filter.

### 6. Provider Abstraction and Credential Handling

**User Story:** As the owner of the machine, I want to point the tool at my own hosted provider key,
at a local model, or at the shared backend, so that I control cost, privacy and quality without the
tool changing how it behaves.

**Acceptance Criteria:**

1. <a name="6.1"></a>The system SHALL support at least these provider kinds behind one contract:
   user-keyed hosted provider, locally-run model, and shared public backend.
2. <a name="6.2"></a>The system SHALL produce responses in the same shape — streamed text, citations,
   timings, refusal signalling — regardless of which provider is configured.
3. <a name="6.3"></a>WHEN the configured provider is changed, the system SHALL apply the change to
   the next turn without restart and without invalidating the ingested corpus or retrieval state.
4. <a name="6.4"></a>The system SHALL express provider configuration in terms of **provider kind** —
   keyed hosted, local, or shared backend — and SHALL derive whether a credential is required from
   the kind. A configured provider whose kind requires no credential SHALL be a valid, fully
   configured state: the system SHALL NOT report it as unconfigured or as missing a credential.
5. <a name="6.5"></a>WHEN no provider kind is selected, the system SHALL return a result stating that
   a provider must be configured, and SHALL still permit retrieval-only operations such as passage
   lookup ([3.4](#3.4)).
6. <a name="6.6"></a>WHEN a provider whose kind requires a key is configured without one, the system
   SHALL fail the turn as `provider-unconfigured` carrying a missing-credential reason, and SHALL
   make that reason distinguishable by the caller from an authentication failure, which is a
   `provider-error`.
7. <a name="6.7"></a>WHEN a provider is unreachable, the system SHALL fail the turn within 10 s
   ([4.9](#4.9)) and SHALL return a result identifying the provider and the failure kind.
8. <a name="6.8"></a>WHEN a provider returns a rate-limit response, the system SHALL retry at most
   once, honouring any stated retry interval up to 3 s, and SHALL otherwise surface a rate-limited
   result including any retry-after value.
9. <a name="6.9"></a>WHEN a provider returns any other error, the system SHALL surface the provider's
   error kind and SHALL NOT substitute a synthesised answer or a cached answer from a different turn.
10. <a name="6.10"></a>WHEN a provider fails mid-stream after partial output, the system SHALL mark
    the answer as incomplete and SHALL NOT present the truncated text as a finished answer.
11. <a name="6.11"></a>The system SHALL NOT write provider keys to logs, traces, error messages,
    telemetry, crash reports or answer output, in whole or in part.
12. <a name="6.12"></a>The system SHALL transmit a provider key only to the endpoint of the provider
    that key belongs to, and only over an encrypted transport.
13. <a name="6.13"></a>The system SHALL NOT return a stored key through any read interface; where a
    key must be displayed, the system SHALL return only a masked form.
14. <a name="6.14"></a>WHERE a local provider is configured, the system SHALL require no key and
    SHALL make no outbound network request for the whole turn.
15. <a name="6.15"></a>WHERE the shared public backend is selected, the system SHALL disclose
    explicitly, before the first turn on that provider kind is sent, that question text and retrieved
    passages leave the machine, and SHALL NOT send that turn until the caller has acknowledged the
    disclosure. A provider kind that exports the user's questions off a loopback-only tool is not a
    default the user may discover after the fact.

### 7. Symptom-Shaped Questions

**User Story:** As a producer, I ask "the kick is distorting" or "no sound from track 3", not a
well-formed manual query — I want the tool to narrow it down with me rather than guess.

**Acceptance Criteria:**

1. <a name="7.1"></a>WHEN a question describes a symptom without enough detail to identify a single
   documented cause, the system SHALL respond with one narrowing question instead of an answer.
2. <a name="7.2"></a>WHEN asking a narrowing question, the system SHALL offer between 2 and 4
   concrete candidate answers. WHERE an `authored-triage` entry matches the symptom, that entry's
   ranked causes and their confirming checks SHALL be the source of the candidates, taken in the
   entry's own order of likelihood; otherwise the candidates SHALL be drawn from the distinguishing
   conditions in the retrieved passages. **The triage source is what makes this criterion
   satisfiable against the real corpus.** No vendor passage states the distinguishing conditions:
   the Live manual documents the Track Activator as the control that mutes a track's output and
   nowhere names it as a cause of silence, so a candidate asking whether it is off rests on an
   inference no manual passage states, and against manuals alone there is nothing to draw the
   candidates from. A matching entry supplies that inference as a retrieved, citable passage in its
   own right (`CONTRACTS.md` §4a). Selecting which documented control a candidate names remains
   reasoning over cited passages and is permitted by [2.6](#2.6); the fact that the control mutes
   the track SHALL still carry its vendor-manual citation, and the causal claim SHALL be attributed
   to the authored entry rather than to the manufacturer ([1.13](#1.13)).
3. <a name="7.3"></a>The system SHALL hold a narrowing question to the same first-token budget as any
   other response for the configured provider kind ([4.6](#4.6), [4.7](#4.7)), and SHALL NOT be held
   to a completion target that would necessarily precede it. A complete short response cannot arrive
   before another response's first token on the same provider.
4. <a name="7.4"></a>WHEN the caller answers a narrowing question, the system SHALL re-retrieve using
   the original question plus the answer, and SHALL NOT reuse the previous turn's passages unchanged.
5. <a name="7.5"></a>The system SHALL ask at most 2 consecutive narrowing questions for a single
   symptom before producing an answer.
6. <a name="7.6"></a>WHEN the narrowing limit in [7.5](#7.5) is reached and the cause is still
   ambiguous, the system SHALL return a ranked list of at most 4 documented candidate causes, each
   with its citations and the check that would confirm or eliminate it. WHERE the causes come from
   an `authored-triage` entry, the system SHALL preserve that entry's ranking, and SHALL carry with
   each cause its confirming check and — where the entry names one — the vendor-manual citation for
   the fix.
7. <a name="7.7"></a>The system SHALL NOT ask a narrowing question whose answer would not change
   which passages are retrieved or which cause is reported.
8. <a name="7.8"></a>WHEN session state ([§8](#8-session-state-context)) already supplies the value a
   narrowing question would ask for, the system SHALL use the state value and skip the question.

### 8. Session State Context

**User Story:** As a producer, I eventually want the tool to know that track 3's monitor is off
rather than asking me — but today it answers from manuals only, and I do not want that later
capability to require a rewrite.

**Acceptance Criteria:**

1. <a name="8.1"></a>The system SHALL accept an optional session-state context with each turn,
   supplied through a single abstraction (`StateSource`) whose contract does not vary by
   implementation.
2. <a name="8.2"></a>WHEN no session state is available, the system SHALL answer from manuals alone
   and SHALL NOT degrade in latency, citation quality or refusal behaviour.
3. <a name="8.3"></a>The MVP SHALL ship a null implementation that reports no session state, and the
   system SHALL be fully functional with it.
4. <a name="8.4"></a>The contract SHALL admit, without redefinition, an implementation that reads
   state from a saved Ableton project file and an implementation that receives live state from a
   running DAW.
5. <a name="8.5"></a>Every state value supplied to the system SHALL carry a freshness timestamp and
   an origin identifying which implementation produced it.
6. <a name="8.6"></a>WHEN an answer uses a state value, the system SHALL attribute that value to
   session state and SHALL NOT present it as a manual citation.
7. <a name="8.7"></a>WHEN a state value's freshness exceeds 60 s, or its origin is a saved file, the
   system SHALL state in the answer that the value may not reflect the current project.
8. <a name="8.8"></a>WHEN a state source fails, times out or returns malformed state, the system
   SHALL proceed manual-only for that turn and SHALL note that state was unavailable, rather than
   failing the turn.
9. <a name="8.9"></a>The system SHALL apply a state-retrieval timeout of 100 ms per turn, enforcing
   the budget line in [4.4](#4.4). State acquisition is excluded from the engine overhead cap in
   [4.3](#4.3) and is not charged against it.
10. <a name="8.10"></a>WHEN state contradicts a manual passage, the system SHALL report both and
    SHALL identify which is state and which is documentation.

### 9. Local HTTP Contract

**User Story:** As the owner of the machine, I want the engine reachable from my own browser tab and
from nothing else, so that neither my questions nor my provider keys are exposed to my network.

**Acceptance Criteria:**

1. <a name="9.1"></a>The system SHALL expose its operations over HTTP on a loopback interface only.
2. <a name="9.2"></a>The system SHALL refuse to start IF configured to bind a non-loopback address,
   and SHALL report why rather than binding a fallback.
3. <a name="9.3"></a>The system SHALL reject any request whose `Host` or `Origin` header does not
   correspond to the local loopback service, so that a page on another site cannot drive the engine
   through the user's browser.
4. <a name="9.4"></a>The system SHALL expose, at minimum: submit-question (streaming), fetch-passage
   by identifier, list-sources, get-provider-status, set-provider (choosing a provider kind),
   set-credential, clear-credential, and test-provider (reporting reachability without synthesising
   a turn). Every one of these is required by the configuration surface in
   `ui/ask-and-source-picker`; without them that surface has nothing to call.
5. <a name="9.5"></a>The list-sources operation SHALL return, for every source in the corpus and for
   **both** kinds: `source_id`, `display_name`, `kind` (`vendor-manual` or `authored-triage`),
   `doc_version` where the kind carries one, and `hardware_applicability` including whether it is
   `confirmed` or `assumed`. `data/manual-corpus` publishes all of these to this spec (its 11.6 and
   12.7) and `ui/ask-and-source-picker` renders each of them in the picker; list-sources is the only
   counterpart that browser page can reach, so a field this operation omits reaches nobody.
6. <a name="9.6"></a>The system SHALL return, alongside the source list, the
   **owned-but-undocumented** report published by `data/manual-corpus` (its §11, `CONTRACTS.md` §5)
   — each device in the declared **rig inventory** for which no source is indexed, today the
   Focusrite Scarlett Solo — naming each such device. The engine relays this report; it does not own
   the rig inventory and SHALL NOT derive it from the corpus. Both the device scope in
   [5.12](#5.12) and the `required_device` in [2.10](#2.10) draw on it, and the picker names the gap
   so the user does not spend a question discovering it.
7. <a name="9.7"></a>The system SHALL return, alongside the source list, the
   **documented-but-unconfirmed** report published by `data/manual-corpus` (its §11) — each indexed
   source whose `hardware_applicability` is `assumed`, or whose declared revision differs from the
   revision owned, today the Akai APC Key 25 guide against an owned mk2 — so that the mismatch is
   visible before the question is asked rather than only in the citation ([3.3](#3.3)).
8. <a name="9.8"></a>The system SHALL return provider status, and the result of set-credential and
   test-provider, without ever including credential material; where a stored key is referenced at
   all, only the masked form in [6.13](#6.13) SHALL be returned.
9. <a name="9.9"></a>The system SHALL return a machine-readable outcome with every response, drawn
   from exactly this set and no other: `answered`, `partially-answered`, `needs-narrowing`,
   `refused-not-covered`, `out-of-domain` ([2.9](#2.9)), `no-manual-for-device` ([2.10](#2.10)),
   `no-sources-selected` ([5.2](#5.2)), `unknown-source-id` ([5.3](#5.3)), `corpus-empty`,
   `provider-unconfigured`, `provider-unreachable`, `provider-rate-limited` (carrying any
   retry-after value, [6.8](#6.8)), `provider-error`, `timeout` (attributed to the provider and
   distinct from unreachable, [4.9](#4.9)), `incomplete` ([6.10](#6.10)) and `cancelled`
   ([4.10](#4.10)). The caller cannot render an outcome the engine has not named, so the system
   SHALL NOT hold a private outcome outside this set.
10. <a name="9.10"></a>WHEN the caller disconnects mid-stream, the system SHALL treat this as
    cancellation per [4.10](#4.10).
11. <a name="9.11"></a>The system SHALL NOT log question text, answer text or passage content at
    default log level, and SHALL never log credentials at any level ([6.11](#6.11)).
12. <a name="9.12"></a>The system SHALL accept a question of up to 1000 characters and SHALL reject a
    longer one **before a turn exists**, on the submit-question request itself, stating the limit and
    the length received. Such a rejection SHALL NOT be truncated to fit, SHALL NOT produce an answer
    envelope, and SHALL NOT carry an outcome from [9.9](#9.9): no turn was started, so the taxonomy
    in `CONTRACTS.md` §6 does not describe it and SHALL NOT be extended to. Because the caller's
    outcome renderer therefore cannot surface it, the system SHALL return it in a machine-readable
    form distinguishable from every outcome, so the caller can report it against the question input
    as a rejected submission rather than as an answer or a refusal.
13. <a name="9.13"></a>WHEN a new question arrives for a conversation whose previous turn is still
    streaming, the system SHALL cancel the in-flight turn per [4.10](#4.10), report it as
    `cancelled`, and begin the new turn; it SHALL NOT interleave two streams on one conversation and
    SHALL NOT queue the new question behind the old one.

### 10. Conversation Continuity

**User Story:** As a producer, I want to say "and what about the return track?" without restating the
whole question, so that follow-ups cost me one line rather than a paragraph.

**Position.** Follow-ups retain context, bounded and in-memory. Continuity is required by the
narrowing behaviour in [§7](#7-symptom-shaped-questions) — a clarifying question is meaningless
without it — but history is never a grounding source, and it never survives a restart.

**Acceptance Criteria:**

1. <a name="10.1"></a>The system SHALL retain the last 6 turns of the current conversation and SHALL
   use them to interpret a follow-up question.
2. <a name="10.2"></a>The system SHALL re-run retrieval on every turn, and SHALL NOT reuse a prior
   turn's passages as the grounding for a new answer.
3. <a name="10.3"></a>The system SHALL treat conversation history as context for interpreting the
   question only, and SHALL NOT treat any statement in history as a citable fact.
4. <a name="10.4"></a>The system SHALL carry the selected source set forward across turns until the
   caller changes it.
5. <a name="10.5"></a>WHEN the caller changes the selected sources mid-conversation, the system SHALL
   apply the new set from the next turn onward and SHALL NOT retain passages from now-deselected
   sources.
6. <a name="10.6"></a>The system SHALL allow the caller to start a new conversation, discarding prior
   turns.
7. <a name="10.7"></a>The system SHALL NOT persist conversation history across a restart of the
   service.
8. <a name="10.8"></a>The system SHALL keep the tokens contributed by history within a fixed budget,
   dropping oldest turns first, so that continuity cannot erode the latency budget in [§4](#4-latency).

---

## Non-Goals

- **General music-production advice.** The engine answers from its ingested sources. Questions about
  mixing taste, arrangement or genre convention that **no** ingested source covers are out of scope
  and are answered honestly as out-of-domain ([2.9](#2.9)) rather than as an uncovered question
  ([2.1](#2.1)) — no manual will ever cover them, so suggesting other sources would be a lie. A
  question the user's own `authored-triage` source does cover is answered from it and cited to it;
  out-of-domain is reserved for what neither kind of source holds.
- **Authoring or validating the triage source.** Owned by `data/symptom-triage`. The engine
  retrieves and cites its entries like any other source and never writes to it.
- **Controlling the DAW.** The engine reads context at most; it never sends commands to Ableton Live
  or any hardware.
- **Live DAW state in the MVP.** Only the null state source ships ([8.3](#8.3)).
- **Multi-user or remote access.** One user, one machine, loopback only ([9.1](#9.1)).
- **Account management, billing or key provisioning.** The user brings a key or uses the shared
  backend; the engine does not create, purchase or rotate credentials.
- **Ingestion, chunking and metadata extraction.** Owned by `data/manual-corpus`.
- **Declaring or maintaining the rig inventory, and computing the coverage gaps over it.** Owned by
  `data/manual-corpus` (its §11) and `data/symptom-triage` (its §6). The engine relays both gap
  reports to the browser surface ([9.6](#9.6)–[9.7](#9.7)) because it is the only counterpart that
  surface can reach; it neither derives nor edits them.
- **Rendering, source pickers and answer presentation.** Owned by `ui/ask-and-source-picker`.
- **Offline evaluation harnesses and answer-quality benchmarking** beyond the observable behaviour
  stated above.

## Assumptions and Risks

### Assumptions

- The reference corpus is small: three vendor manuals at ~1068 pages / ~330k tokens, plus one
  authored triage source in the tens to low hundreds of entries. Retrieval budgets in
  [§4](#4-latency) cover both kinds at that scale and would need revisiting if either grew by an
  order of magnitude. The corpus is **not** assumed static — re-ingestion can happen while the
  engine runs, and [5.10](#5.10)–[5.11](#5.11) define what that does to cached retrieval state and
  to a conversation's carried scope.
- Chunks arrive with source ID, source kind, section number, section title, page number, document
  version, hardware applicability, declared devices where the passage has them, and the degraded,
  figure and `unbacked` flags already attached, so citations ([3.2](#3.2)–[3.3](#3.3),
  [3.8](#3.8)) are assemblable without re-parsing the PDFs. On a pageless source the section
  number, page and document version arrive absent, and are emitted absent.
- The corpus holds two kinds of source, not one. `data/symptom-triage` supplies an `authored-triage`
  source whose entries reach this engine as ordinary passages through `data/manual-corpus`. Nothing
  here assumes it is present — with no matching entry the engine falls back to the manual-only
  behaviour these criteria already describe — but the narrowing flow ([7.2](#7.2)) is only
  satisfiable in practice when it is.
- The rig is fixed and known: Ableton Live 12 **Standard** (no Max for Live), Akai APC Key 25 mk2,
  Focusrite Scarlett Solo, macOS. The Live manual documents the full product, so edition gating
  ([1.12](#1.12)) is a permanent requirement, not a transitional one; and the Scarlett Solo is
  owned-but-undocumented, which is the standing case for [2.10](#2.10). The rig inventory this rests
  on is declared and maintained by hand in `data/manual-corpus` (its §11); the engine reads it only
  through the reports in [9.6](#9.6)–[9.7](#9.7), so a device never declared is invisible here too.
- One user, one conversation at a time. No contention, no isolation between tenants — [9.13](#9.13)
  resolves overlap by cancellation rather than by concurrency.
- The reference machine for all latency figures is the user's own macOS development machine; the
  figures are not portable claims about arbitrary hardware.
- **Open question — the shared public backend.** [6.1](#6.1) and [6.15](#6.15) mandate a provider
  kind that sends question text and retrieved passages off a machine whose defining property is that
  it is loopback-only ([9.1](#9.1)). No other spec in the project acknowledges it, and it is not
  costed, hosted or owned. It is retained here because the criteria depend on it, but it needs its
  own entry in the decision log before implementation; the disclosure in [6.15](#6.15) is a
  safeguard, not that decision.

### Risks

| Risk | Impact | Mitigation in these requirements |
|---|---|---|
| **Hallucination despite grounding.** A provider can still invent a parameter name or menu path that reads plausibly, particularly for Live, whose documentation it has almost certainly seen in training. | A confidently wrong answer is worse than no answer — the stated failure mode this spec is written against. | [1.2](#1.2), [2.6](#2.6), [3.6](#3.6), [3.7](#3.7) — citation resolution is checked, not trusted, and unresolvable claims mark the answer after streaming rather than passing silently. |
| **Topical similarity mistaken for an answer.** A technique question retrieves high-scoring passages about devices that do something adjacent — asking why a kick distorts surfaces Saturator and Drum Buss, which distort deliberately. The relevance threshold does not catch it because the scores are high. | The tool answers confidently and completely wrongly, with citations that make it more convincing. | [2.8](#2.8) tests responsiveness to intent, not similarity, and ranks a matching `authored-triage` entry above topically-similar device documentation; [2.9](#2.9) returns out-of-domain and suppresses the source suggestion only where neither kind of source covers the question, because "gain staging" appears **zero** times in the 1009-page Live manual and no vendor manual will ever cover it. |
| **Provider cost and latency variance.** Hosted providers vary by an order of magnitude in time-to-first-token and can degrade without notice; local models are slower but free and private. | The headline latency property is partly outside the engine's control. | Separate budgets for hosted and local ([4.6](#4.6), [4.7](#4.7)) composed into one end-to-end figure ([4.1](#4.1)); engine overhead isolated at ≤ 150 ms ([4.3](#4.3)) so blame is attributable; streaming ([4.5](#4.5)) protects perceived speed; per-turn timings exposed ([4.11](#4.11)). |
| **Manual-accurate, rig-wrong answers.** The corpus documents hardware revisions and Live editions the user does not have: the Akai guide describes the original APC Key 25 while the user owns the mk2, and the Live manual documents Suite devices and Max for Live under a Standard licence. | A cited procedure for the wrong revision is worse than a refusal, because the citation raises the user's confidence in it. | Every citation carries `doc_version` and `hardware_applicability` ([3.3](#3.3)) so the version travels with the claim; edition dependencies are flagged in the answer ([1.12](#1.12)); undocumented devices route to [2.10](#2.10) with the device named. |
| **An authored claim read as the manufacturer's.** A triage entry is cited by exactly the same machinery as a vendor manual, so a causal claim the user wrote themselves can arrive looking as authoritative as a page of the Live manual — and a wrong entry, unlike a wrong manual, has no external check on it. | The user's own guess is laundered into a manufacturer's statement, and the citation raises their confidence in it. | [1.13](#1.13) fixes what each kind is trusted for; [3.8](#3.8) carries the kind on every citation and requires it shown inline rather than behind a disclosure; [3.3](#3.3) carries `unbacked` so a cause resting on no manual is never read as documented; the fix an entry points at still cites a vendor manual ([7.6](#7.6)). |
| **Undocumented Ableton control API.** A future live state feed cannot use Max for Live on Live 12 Standard, leaving an undocumented remote-control scripting interface that Ableton changes without notice or versioning guarantees. | A later `LiveFeedStateSource` could break on any Live point release, or prove unbuildable. | No requirement commits to a live feed. The seam is defined so it is additive ([8.4](#8.4)); the null path is fully functional ([8.3](#8.3)); state failures degrade to manual-only ([8.8](#8.8)). |
| **Manual content going stale.** Live 12.x point releases change behaviour and renumber sections; the ingested PDF is a snapshot, and a manual can be re-ingested underneath a running conversation. | Answers stay confidently correct against a version the user is no longer running, or are grounded in passages that no longer exist. | Citations carry section, page and document version so the user can check against their own build ([3.2](#3.2)–[3.3](#3.3)); source contribution is reported per answer ([5.9](#5.9)); corpus change invalidates cached retrieval state and prunes carried scope ([5.10](#5.10)–[5.11](#5.11)). Version-aware corpus refresh belongs to `data/manual-corpus`, not here. |
| **Every authored entry arrives as one source.** `data/symptom-triage` registers the whole entry store as a single source, so selecting it would otherwise put an entry about Live's routing in scope for a question about the drum module. | Triage widens the problem instead of narrowing it, and the wrong entry outranks the right documentation on a diagnostic question ([2.8](#2.8)). | [5.12](#5.12)–[5.13](#5.13) — a passage's own device declaration is a filter within its source, and the device scope includes owned-but-undocumented gear ([9.6](#9.6)) so a Scarlett Solo entry stays reachable. |
| **Corpus gaps invisible to the browser surface.** The picker can reach no counterpart but this engine, so anything the corpus computes and this spec does not relay reaches nobody. | The user spends a question discovering that a device has no manual, or trusts a source written for a revision they do not own. | [9.5](#9.5) fixes the list-sources payload field by field; [9.6](#9.6)–[9.7](#9.7) relay both gap reports; [3.3](#3.3) repeats applicability on the citation for the case caught only at answer time. |
| **Small-source drowning.** The Live manual is ~200× the size of the APC guide; naive relevance ranking will rarely surface the small guide. | Cross-device questions — the user's most common diagnostic shape — answer from the wrong manual. | [5.5](#5.5), [5.6](#5.6), [5.7](#5.7). |
| **Over-questioning.** Narrowing questions that do not discriminate are worse than a ranked guess, because each one costs a round trip during a session. | The tool feels obstructive and the user stops asking it things. | [7.5](#7.5), [7.6](#7.6), [7.7](#7.7), [7.8](#7.8). |
| **Credential leakage.** Keys are the highest-value secret on the machine and pass through logs, errors and status endpoints by default in most designs — and the engine now exposes operations that set, clear and test them ([9.4](#9.4)). | Financial and privacy exposure. | [6.11](#6.11)–[6.14](#6.14), [9.8](#9.8), [9.11](#9.11) — the masked-read rule applies to every configuration operation, not only to status. |
| **Questions leaving the machine.** The shared public backend ([6.15](#6.15)) contradicts the loopback-only posture the rest of the spec is built on, and no other spec acknowledges it. | The user's questions and manual passages reach a third party without a recorded decision behind it. | Acknowledged disclosure required before the first such turn ([6.15](#6.15)); flagged in Assumptions as needing its own decision-log entry before implementation. |
