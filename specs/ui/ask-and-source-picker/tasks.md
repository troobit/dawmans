---
references:
    - specs/ui/ask-and-source-picker/requirements.md
    - specs/ui/ask-and-source-picker/design.md
    - specs/ui/ask-and-source-picker/decision_log.md
    - specs/CONTRACTS.md
---
# Ask and Source Picker

## Phase 1: Scaffold, contract types and design tokens

- [x] 1. Scaffold the SvelteKit surface and its tooling <!-- id:f9ae010 -->
  - web/ with pnpm; adapter-static, `ssr = false` and `prerender = true` in +layout.ts so the static shell paints before any network call — that headroom is what 8.7's 150 ms acknowledgement budget spends (Decision 1).
  - Vite dev proxy for /turn, /passages, /sources, /provider that rewrites `Origin` as well as `Host` in a proxyReq hook: `changeOrigin: true` alone forwards the browser's Origin and the engine's rebinding guard rejects it (Decision 1).
  - vitest + @testing-library/svelte + Playwright + axe-core as dev dependencies; Makefile targets for web install/build/test and the `make dev` pairing that runs both processes.
  - The engine mounting web/build at `/` is api/answer-engine's route table — depended on, not tasked here.
  - Stream: 1
  - Requirements: [8.7](requirements.md#8.7)
  - References: specs/ui/ask-and-source-picker/design.md

- [x] 2. Implement records.ts contract types <!-- id:f9ae011 -->
  - CONTRACTS §1–§4e as types, the only place they are written down: SourceRecord, Passage, Citation, AnswerEnvelope, Cause, required_manual; `outcome` as the union of §6's 17 members and `reason` as the union of §6a.
  - Optionality follows the contract's own rules, and absent is absent — never empty string, zero or empty array; an empty `suggested_sources[]` would claim the engine looked and found nothing, a different claim from making no suggestion.
  - Types only — no behaviour, so no preceding test task.
  - Blocked-by: f9ae010 (Scaffold the SvelteKit surface and its tooling)
  - Stream: 1
  - Requirements: [9.4](requirements.md#9.4)
  - References: specs/CONTRACTS.md

- [x] 3. Write the token contrast and luminance tests <!-- id:f9ae012 -->
  - WCAG relative luminance and contrast computed from the declared token values in a unit test that fails the build on a breach — the floors are arithmetic, and leaving them observational is the silent-drift risk the requirements name (Decision 6).
  - Body text ≥ 7:1 and every other text element ≥ 4.5:1 (11.3); non-text indicators and the focus ring ≥ 3:1 (11.4); background relative luminance ≤ 0.08 with text lighter than background (11.5); interactive-state token variants included so 13.8 holds at rest and in hover/focus/active/disabled.
  - Assert the 11.3-versus-11.5 resolution as two enforced bounds: background at the lighter end of its band, body text short of maximal white.
  - Size tokens declare 11.1's scale — body inside 16–22 px, nothing needed to act on an answer below 16 px, secondary metadata no lower than 14 px — but the band itself is verified by the stand-back loop, not asserted here: the design classifies 11.1 as observed, and Decision 6 scopes token assertion to 11.3–11.5 plus 13.8. 11.2's stand-back verification is likewise the iterative loop, not this suite.
  - Blocked-by: f9ae010 (Scaffold the SvelteKit surface and its tooling)
  - Stream: 2
  - Requirements: [11.1](requirements.md#11.1), [11.2](requirements.md#11.2), [11.3](requirements.md#11.3), [11.4](requirements.md#11.4), [11.5](requirements.md#11.5), [13.2](requirements.md#13.2), [13.8](requirements.md#13.8)

- [x] 4. Implement the design tokens <!-- id:f9ae013 -->
  - One CSS file of custom properties: background, surface, body text, secondary text, accent, the four state colours, focus ring, and the type scale — components consume tokens and declare no colours of their own, or the floors become uncheckable in principle.
  - Blocked-by: f9ae012 (Write the token contrast and luminance tests)
  - Stream: 2
  - Requirements: [11.1](requirements.md#11.1), [11.3](requirements.md#11.3), [11.4](requirements.md#11.4), [11.5](requirements.md#11.5), [13.2](requirements.md#13.2), [13.8](requirements.md#13.8)

## Phase 2: Engine client and the turn stream

- [x] 5. Write tests for the engine client <!-- id:f9ae014 -->
  - The nine operations of api/answer-engine 9.4 mapped to their routes, all relative — no host and no port hard-coded anywhere (Decision 1).
  - No retries: an unasked retry would duplicate a turn or mask the provider-unreachable state 9.6 requires the user to see.
  - The serve-document href is the route plus the fragment `#page=N` and nothing else — appending a zoom, view or text directive disables the jump in at least one browser's viewer (5.5).
  - Non-envelope HTTP failures — 422 question-too-long, 403 host/origin rejection — surface as typed rejections carrying what was rejected, distinct from any outcome (9.15).
  - Blocked-by: f9ae011 (Implement records.ts contract types)
  - Stream: 1
  - Requirements: [5.5](requirements.md#5.5), [5.6](requirements.md#5.6), [9.15](requirements.md#9.15)

- [x] 6. Implement client.ts <!-- id:f9ae015 -->
  - Stateless typed wrappers returning parsed records; no state, no retries, no fetching from components.
  - Blocked-by: f9ae014 (Write tests for the engine client)
  - Stream: 1
  - Requirements: [5.5](requirements.md#5.5), [5.6](requirements.md#5.6), [9.15](requirements.md#9.15)

- [x] 7. Write tests for the SSE frame reader <!-- id:f9ae016 -->
  - Frames split across chunk boundaries reassemble; a multi-byte character split across two network chunks never paints as U+FFFD — otherwise indistinguishable from a `degraded` passage (Decision 2).
  - An unknown event name is ignored and never fails the turn; end-of-stream without `done` yields `incomplete`, never a settled turn — a stream truncated mid-event discards the pending event silently (9.14).
  - The `dawmans/turn-stream/*` response header is checked before the body is read; an unknown version refuses the turn naming both versions (9.19). No reconnection and no resumption exist.
  - Blocked-by: f9ae011 (Implement records.ts contract types)
  - Stream: 1
  - Requirements: [4.1](requirements.md#4.1), [9.14](requirements.md#9.14), [9.19](requirements.md#9.19)

- [x] 8. Implement sse.ts <!-- id:f9ae017 -->
  - `fetch` + ReadableStream — EventSource cannot POST the question and scope; TextDecoder with `{stream: true}`, split on `\n\n`, yield `{event, data}`.
  - Blocked-by: f9ae016 (Write tests for the SSE frame reader)
  - Stream: 1
  - Requirements: [4.1](requirements.md#4.1), [9.14](requirements.md#9.14), [9.19](requirements.md#9.19)

- [x] 9. Write tests for the append-only block parser and citation markers <!-- id:f9ae018 -->
  - A block's type is fixed by its first line within at most 10 characters (the longest prefix is `!conflict `) and never revised across any chunk split — a re-typed block moves painted text, which is the failure 4.2 names (Decision 2).
  - An unknown first line renders its text as a paragraph and never emits nothing (4.4); a `!conflict` arriving with other than two readings is rendered as the conflict it declared itself, never re-typed.
  - `!caveat` renders in reading order, visually distinct, never behind a disclosure; ordered steps are separately identifiable (4.5); backtick key-term spans become discrete elements — the inline form 4.12's key styling builds on.
  - `[[p:<passage_id>]]` is buffered from `[` until complete or disproved; each distinct id takes the next integer at first appearance and paints immediately — width stable when the `citation` event lands late, so late resolution cannot reflow the line (Decision 3).
  - Blocked-by: f9ae011 (Implement records.ts contract types)
  - Stream: 1
  - Requirements: [4.2](requirements.md#4.2), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [5.17](requirements.md#5.17)

- [x] 10. Implement the block parser <!-- id:f9ae019 -->
  - A small state machine over CONTRACTS §4d's closed set, all decidable at column 0; blocks held in `$state.raw` and replaced by append, never mutated after their text is final.
  - Blocked-by: f9ae018 (Write tests for the append-only block parser and citation markers)
  - Stream: 1
  - Requirements: [4.2](requirements.md#4.2), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [5.17](requirements.md#5.17)

- [x] 11. Write tests for the turn reducer and outcome totality <!-- id:f9ae01a -->
  - One rendering path per CONTRACTS §4b event — the consumer-side test §4b itself mandates, since nothing on the wire detects a client that quietly stops rendering `scope_dropped`. A governed event with no path fails here, not in review.
  - Totality over the §6 union: all 17 outcomes map to a renderer as a total function, so a new member fails the type check; an outcome outside the union renders as a broken state carrying `detail` (9.4) — deliberately the opposite of the ignored unknown event.
  - Ordering honoured: `outcome` fixes the renderer before the first word paints; `direct_answer` precedes body (4.3); `done` settles the turn (4.6); `cause` rank is asserted equal to array position (6.6).
  - `scope_dropped[]` filled and reported with the turn as the engine's prune, never the user's own narrowing (3.11); `ungrounded` marks text already on screen without blanking it (5.13); a settled turn with `citations.size === 0` is marked uncited (5.12).
  - Blocked-by: f9ae017 (Implement sse.ts), f9ae019 (Implement the block parser)
  - Stream: 1
  - Requirements: [3.11](requirements.md#3.11), [4.3](requirements.md#4.3), [4.6](requirements.md#4.6), [5.12](requirements.md#5.12), [5.13](requirements.md#5.13), [6.6](requirements.md#6.6), [9.4](requirements.md#9.4)

- [x] 12. Implement turn.svelte.ts <!-- id:f9ae01b -->
  - The event → Turn reducer, append-only, filling `Partial<AnswerEnvelope>` as events arrive; the citation map keyed by passage_id and the marker order list.
  - Blocked-by: f9ae01a (Write tests for the turn reducer and outcome totality)
  - Stream: 1
  - Requirements: [3.11](requirements.md#3.11), [4.3](requirements.md#4.3), [4.6](requirements.md#4.6), [5.12](requirements.md#5.12), [5.13](requirements.md#5.13), [6.6](requirements.md#6.6), [9.4](requirements.md#9.4)

## Phase 3: Scope, sources and history stores

- [x] 13. Write tests for the scope store, persistence and decay <!-- id:f9ae01c -->
  - The session boundary is `sessionStorage` presence, not a clock: cleared by a browser restart, survives a reload — exactly 3.6's first clause. The 8-hour clause reads `lastQuestionAt`. Either releases the narrowing into `released` for a one-activation reinstate; a stored scope already equal to all available releases nothing, so the notice never appears spuriously (Decision 4).
  - No stored scope starts with all available sources (3.7); a stored id the engine no longer reports drops silently at load (3.8) — a different subject from 3.11's engine-side prune, which is reported.
  - Scope survives successive questions unchanged (3.4) and reloads within a session (3.5); a change while an answer is on screen touches only the next question (3.9).
  - Zero sources in scope blocks submission — the client never sends an empty scope (3.1); a widen-and-retry persists like any scope change and decays at the next session (7.9).
  - Blocked-by: f9ae011 (Implement records.ts contract types)
  - Stream: 2
  - Requirements: [3.1](requirements.md#3.1), [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [3.6](requirements.md#3.6), [3.7](requirements.md#3.7), [3.8](requirements.md#3.8), [3.9](requirements.md#3.9), [7.9](requirements.md#7.9)

- [x] 14. Implement scope.svelte.ts <!-- id:f9ae01d -->
  - A class instance, not a bare `$state` export — a reassigned module-level `$state` is not reactive across the module boundary. localStorage `dawmans.scope`, sessionStorage `dawmans.session`.
  - Blocked-by: f9ae01c (Write tests for the scope store, persistence and decay)
  - Stream: 2
  - Requirements: [3.1](requirements.md#3.1), [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [3.6](requirements.md#3.6), [3.7](requirements.md#3.7), [3.8](requirements.md#3.8), [3.9](requirements.md#3.9), [7.9](requirements.md#7.9)

- [x] 15. Write tests for the sources store and gap reports <!-- id:f9ae01e -->
  - Everything comes from GET /sources — `display_name` rendered, no fixed source count anywhere in the code (2.1); an added or removed source of either kind is reflected on the next load with no change to the interface (2.3).
  - Newness is `source_id ∉ seen[]`, and `seen[]` updates on the next submit, not on render — a source glimpsed but not acted on stays new (2.4). A new source enters scope only where the stored scope was all available; under a narrowed scope it stays out with a one-activation add, so a fresh ingestion never silently undoes a deliberate narrowing.
  - Both gap reports carried: owned-but-undocumented (2.9) and assumed `hardware_applicability` with the revision it describes (2.10), plus `low_text`. The empty owned-but-undocumented report is the live case (OVERVIEW, Decision 12) — the populated path is exercised against a fixture payload, never hardcoded empty.
  - A failed GET /sources puts the store in an engine-unreachable state that the picker reports and that blocks submission — distinct from `corpus-empty`, which is the engine answering that nothing is ingested (9.13); the failure never renders as an empty picker.
  - Blocked-by: f9ae015 (Implement client.ts)
  - Stream: 2
  - Requirements: [2.1](requirements.md#2.1), [2.3](requirements.md#2.3), [2.4](requirements.md#2.4), [2.9](requirements.md#2.9), [2.10](requirements.md#2.10), [9.13](requirements.md#9.13)

- [x] 16. Implement sources.svelte.ts <!-- id:f9ae01f -->
  - Available sources plus both gap reports as a class-instance store consumed by the picker and the empty-corpus state, carrying the fetch-failed engine-unreachable state distinct from corpus-empty.
  - Blocked-by: f9ae01e (Write tests for the sources store and gap reports)
  - Stream: 2
  - Requirements: [2.1](requirements.md#2.1), [2.3](requirements.md#2.3), [2.4](requirements.md#2.4), [2.9](requirements.md#2.9), [2.10](requirements.md#2.10), [9.13](requirements.md#9.13)

- [x] 17. Write tests for the history store <!-- id:f9ae01g -->
  - localStorage, read lazily when the panel first opens — parsing 50 exchanges on boot would come out of 8.7's acknowledgement budget for nothing on screen at rest (12.1).
  - An entry stores the question, the envelope, the citation records, the scope at ask time and a timestamp — never passage text, which is refetched on demand; trimmed to the most recent 50 on `settled`; a QuotaExceededError drops oldest entries until the write succeeds rather than failing the turn (12.9).
  - Cancelled and failed exchanges are not retained as answers; a partial retained under 9.14 is marked incomplete (12.7).
  - Blocked-by: f9ae011 (Implement records.ts contract types)
  - Stream: 2
  - Requirements: [12.1](requirements.md#12.1), [12.7](requirements.md#12.7), [12.9](requirements.md#12.9)

- [x] 18. Implement history.svelte.ts <!-- id:f9ae01h -->
  - The persisted exchange store; write on settle, lazy read, quota fallback.
  - Blocked-by: f9ae01g (Write tests for the history store)
  - Stream: 2
  - Requirements: [12.1](requirements.md#12.1), [12.7](requirements.md#12.7), [12.9](requirements.md#12.9)

## Phase 4: Keyboard routing and the ask surface

- [x] 19. Write tests for the keyboard router and arming registry <!-- id:f9ae01i -->
  - The decision table in order: modifier held passes through; a text-entry target passes through; Escape dismisses the topmost region returning focus to its opener (13.3); digits 1–4 activate an entry only while the registry holds an armed set (1.11); any other printable focuses the input and inserts the character manually — `preventDefault` then append, because the keydown already happened on another element (1.2, Decision 5).
  - Registry invariant: at most one armed set ever — shortcuts show only on an empty input and a narrowing turn has a question in flight, so the ambiguous case cannot arise.
  - `svelte:window onfocus` restores focus to the input unless an overlay region holds it — stealing it would break 13.3's return-focus contract (1.1).
  - A missed unregister leaving a stale armed digit is the named failure mode: assert unmount clears the registration.
  - Blocked-by: f9ae011 (Implement records.ts contract types)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2), [1.11](requirements.md#1.11), [13.3](requirements.md#13.3)

- [x] 20. Implement keys.ts <!-- id:f9ae01j -->
  - One `keydown` listener on `window` with the explicit arming registry; components register and unregister, never handling these keys themselves — per-component handlers cannot know what another has armed (Decision 5).
  - Blocked-by: f9ae01i (Write tests for the keyboard router and arming registry)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2), [1.11](requirements.md#1.11), [13.3](requirements.md#13.3)

- [x] 21. Write tests for the ask input, symptom shortcuts and thread shell <!-- id:f9ae01k -->
  - Focus lands in the input on load and window focus without a click (1.1); unmodified Enter submits, Shift+Enter inserts a line break (1.3); empty or whitespace-only submit does nothing and contacts no engine (1.5); submitted text stays inspectable and re-editable (1.4); on `done`, focus returns to an empty input without discarding the answer (1.6).
  - A question over a rendered answer is a follow-up, indicated on screen, with a single keyboard-and-pointer control that starts a fresh context-free thread (1.7, 1.8); a keyboard-reachable stop control retains whatever text arrived (1.9).
  - The four symptom shortcuts — no sound, distorting, latency, wrong drum sound — render on an empty input, each submitting in one keypress via the arming registry and equally by pointer and normal navigation (1.10).
  - Losing window focus changes nothing: the fetch stream runs to completion, answer, question and scope are retained, and no state needed to read or act depends on hover or tab focus (1.12).
  - Zero-scope submit is blocked with a message and a single select-all control preserving the typed text (3.2); the 1000-character limit is enforced client-side, stating limit and typed length while the question stays editable (9.15).
  - Blocked-by: f9ae01b (Implement turn.svelte.ts), f9ae01d (Implement scope.svelte.ts), f9ae01j (Implement keys.ts)
  - Stream: 1
  - Requirements: [1.3](requirements.md#1.3), [1.4](requirements.md#1.4), [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.7](requirements.md#1.7), [1.8](requirements.md#1.8), [1.9](requirements.md#1.9), [1.10](requirements.md#1.10), [1.12](requirements.md#1.12), [3.2](requirements.md#3.2), [9.15](requirements.md#9.15)

- [x] 22. Implement the ask input, symptom shortcuts and thread shell <!-- id:f9ae01l -->
  - The ask input, the shortcut row, and thread.svelte.ts holding the conversation on screen; submission goes through the scope store's block and the turn state machine.
  - Blocked-by: f9ae01k (Write tests for the ask input, symptom shortcuts and thread shell)
  - Stream: 1
  - Requirements: [1.3](requirements.md#1.3), [1.4](requirements.md#1.4), [1.5](requirements.md#1.5), [1.6](requirements.md#1.6), [1.7](requirements.md#1.7), [1.8](requirements.md#1.8), [1.9](requirements.md#1.9), [1.10](requirements.md#1.10), [1.12](requirements.md#1.12), [3.2](requirements.md#3.2), [9.15](requirements.md#9.15)

## Phase 5: Answer rendering and citations

- [x] 23. Write tests for the answer renderer <!-- id:f9ae01m -->
  - Partial content paints progressively (4.1); `direct_answer` renders first with detail and citations following in supplied order (4.3); every §4d block and inline type renders visually distinct — `!caveat` in reading position and never behind a disclosure, `!conflict` with both readings and their separate citations, neither chosen (4.4); steps separately identifiable (4.5); finished distinguishable from streaming (4.6).
  - `contributing_sources` named distinctly from merely-in-scope sources (4.7); `partially-answered` renders as an answer with each `uncovered_parts[]` entry visually subordinate, never as a refusal or error (4.8); a per-part control re-asks the uncovered part alone, widening to the engine-named sources, with the answered part left on screen (4.9).
  - A turn carrying `scope_dropped[]` names the dropped sources with that turn and states the corpus no longer holds them (3.11).
  - Key names and combinations render as discrete key-styled elements, named as the manual names them, never smaller than body text (4.12); measure and instruction-first layout are built toward 4.10/4.11/11.7 — band verification is the iterative loop's stand-back tests, recorded in decision_log.md when hit.
  - Blocked-by: f9ae01b (Implement turn.svelte.ts)
  - Stream: 1
  - Requirements: [3.11](requirements.md#3.11), [4.1](requirements.md#4.1), [4.2](requirements.md#4.2), [4.3](requirements.md#4.3), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [4.6](requirements.md#4.6), [4.7](requirements.md#4.7), [4.8](requirements.md#4.8), [4.9](requirements.md#4.9), [4.10](requirements.md#4.10), [4.11](requirements.md#4.11), [4.12](requirements.md#4.12), [11.7](requirements.md#11.7)

- [x] 24. Implement the answer renderer <!-- id:f9ae01n -->
  - Presentation only — no fetching, no persistence; consumes the reducer's blocks and envelope.
  - Blocked-by: f9ae01m (Write tests for the answer renderer)
  - Stream: 1
  - Requirements: [3.11](requirements.md#3.11), [4.1](requirements.md#4.1), [4.2](requirements.md#4.2), [4.3](requirements.md#4.3), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [4.6](requirements.md#4.6), [4.7](requirements.md#4.7), [4.8](requirements.md#4.8), [4.9](requirements.md#4.9), [4.10](requirements.md#4.10), [4.11](requirements.md#4.11), [4.12](requirements.md#4.12), [11.7](requirements.md#11.7)

- [x] 25. Write tests for the citation list and its inline marks <!-- id:f9ae01o -->
  - The location slot renders `section_number` and `section_title` as the two fields they are, with only what exists — an unnumbered document shows no invented number (5.1); a pageless authored citation puts the entry's symptom title in the slot with page and section absent, never 0 and never empty (5.15).
  - The five inline obligations render on the citation entry with no disclosure in the path: `doc_version` (5.2), assumed `hardware_applicability` naming the revision described (5.3), "figure on pN" (5.4), `kind` as the user's own note, distinguishable from a manufacturer citation in greyscale (5.14), and `unbacked` (5.16). Inline means on the citation, not mid-prose — five caveats in the sentence would breach 11.7 on the first citation (Decision 3).
  - `entry_location` shows file and line beside the open action, copyable in one activation; never in the location slot, never rendered as a section or page (5.19).
  - A settled answer with no citations is marked uncited (5.12); `ungrounded` marks the rendered answer as unverified without withholding or blanking it (5.13); markers stay ≤ body text size (5.17).
  - Blocked-by: f9ae01b (Implement turn.svelte.ts)
  - Stream: 1
  - Requirements: [5.1](requirements.md#5.1), [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [5.4](requirements.md#5.4), [5.12](requirements.md#5.12), [5.13](requirements.md#5.13), [5.14](requirements.md#5.14), [5.15](requirements.md#5.15), [5.16](requirements.md#5.16), [5.17](requirements.md#5.17), [5.19](requirements.md#5.19)

- [x] 26. Implement the citation list <!-- id:f9ae01p -->
  - The list below the answer, one entry per marker integer in first-appearance order, carrying every §3 rendering obligation.
  - Blocked-by: f9ae01o (Write tests for the citation list and its inline marks)
  - Stream: 1
  - Requirements: [5.1](requirements.md#5.1), [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [5.4](requirements.md#5.4), [5.12](requirements.md#5.12), [5.13](requirements.md#5.13), [5.14](requirements.md#5.14), [5.15](requirements.md#5.15), [5.16](requirements.md#5.16), [5.17](requirements.md#5.17), [5.19](requirements.md#5.19)

- [x] 27. Write tests for passage expansion and open-at-source <!-- id:f9ae01q -->
  - Expansion fetches GET /passages/{passage_id} on activation and shows the text verbatim, visually distinguishable from summary text (5.6), revealed in place without navigating away (5.7); collapse restores the citation element's viewport offset via its rect, not `scrollY` — content above may have grown while streaming continued (5.8).
  - A session `Map` cache, prefetched on focus and never on hover (1.12): focus precedes activation by a keystroke, so the 150 ms target is a cache hit in the ordinary case, and a miss shows the working indicator past 300 ms rather than an empty area (5.18).
  - `degraded` marks the expanded passage distinctly from the unavailable state (5.10); a failed fetch keeps the source, its cited location and the open action — never a hidden citation or empty area (5.11); focus, expand and open all work by keyboard alone (5.9).
  - openAtSource is two branches and no third (5.5): vendor-manual is a plain link activation — `target="_blank"`, `rel="noopener"`, href the serve-document route at exactly `#page=N`; authored-triage is the 5.6 expansion plus the copyable `entry_location`. No `file://` URL is ever attempted; a serve-document 404 degrades the citation to its string form, never to a broken action.
  - Blocked-by: f9ae015 (Implement client.ts), f9ae01p (Implement the citation list)
  - Stream: 1
  - Requirements: [5.5](requirements.md#5.5), [5.6](requirements.md#5.6), [5.7](requirements.md#5.7), [5.8](requirements.md#5.8), [5.9](requirements.md#5.9), [5.10](requirements.md#5.10), [5.11](requirements.md#5.11), [5.18](requirements.md#5.18), [5.19](requirements.md#5.19)

- [x] 28. Implement passage expansion and openAtSource <!-- id:f9ae01r -->
  - Expansion, the passage cache, the focus prefetch and both open-at-source branches on the citation entry.
  - Blocked-by: f9ae01q (Write tests for passage expansion and open-at-source)
  - Stream: 1
  - Requirements: [5.5](requirements.md#5.5), [5.6](requirements.md#5.6), [5.7](requirements.md#5.7), [5.8](requirements.md#5.8), [5.9](requirements.md#5.9), [5.10](requirements.md#5.10), [5.11](requirements.md#5.11), [5.18](requirements.md#5.18), [5.19](requirements.md#5.19)

## Phase 6: Narrowing, ranked causes and coverage failure

- [x] 29. Write tests for the narrowing renderer <!-- id:f9ae01s -->
  - `needs-narrowing` renders the question and candidates visually distinct from an answer, a coverage failure and an error (6.1); the 2–4 candidates are separately activatable controls numbered in engine order — never reordered, merged or added to (6.2); digits 1–4 select via the arming registry, as do navigation and pointer, with armed keys indicated (6.3).
  - Selection submits a follow-up turn in the current thread against unchanged scope, keeping the question and chosen candidate visible (6.4); typing any printable other than an armed digit begins a free-text reply without dismissing the list — this falls out of the keyboard router at no extra cost (6.5).
  - The exchange is retained in history as part of its thread, never as a standalone unanswered question (6.7); the narrowing question paints from its first token and is not held back until candidates complete (6.8 — the latency figure itself is the engine's, measured in the iterative loop).
  - Blocked-by: f9ae01b (Implement turn.svelte.ts), f9ae01j (Implement keys.ts)
  - Stream: 1
  - Requirements: [6.1](requirements.md#6.1), [6.2](requirements.md#6.2), [6.3](requirements.md#6.3), [6.4](requirements.md#6.4), [6.5](requirements.md#6.5), [6.7](requirements.md#6.7), [6.8](requirements.md#6.8)

- [x] 30. Implement the narrowing renderer <!-- id:f9ae01t -->
  - The candidate list wired to the arming registry and the follow-up submit path.
  - Blocked-by: f9ae01s (Write tests for the narrowing renderer)
  - Stream: 1
  - Requirements: [6.1](requirements.md#6.1), [6.2](requirements.md#6.2), [6.3](requirements.md#6.3), [6.4](requirements.md#6.4), [6.5](requirements.md#6.5), [6.7](requirements.md#6.7), [6.8](requirements.md#6.8)

- [x] 31. Write tests for the ranked-causes renderer <!-- id:f9ae01u -->
  - `causes[]` renders in array order with each `rank` shown; causes are findings to read, never the digit-armed controls of 6.2/6.3 — the affordance split is the only thing keeping the two candidate-bearing shapes apart, and its failure mode is a ranked list that invites answering a question the engine stopped asking (6.6).
  - `causes[0]` is never promoted to an answer; the rank-1 cause's `check` arrives as `direct_answer` and paints first, which is what keeps 4.10 and 11.7 reachable on this outcome.
  - `cites[]` and `fix_cites[]` resolve through the turn's citation map by `passage_id` — no second citation channel; a cause with empty `fix_cites[]` carries the `unbacked` mark rather than simply appearing without a fix (5.16); the fix citation renders as an ordinary citation, distinct from the authored cause it belongs to.
  - Blocked-by: f9ae01p (Implement the citation list)
  - Stream: 1
  - Requirements: [5.16](requirements.md#5.16), [6.6](requirements.md#6.6)

- [x] 32. Implement the ranked-causes renderer <!-- id:f9ae01v -->
  - The `ranked-causes` renderer over `causes[]` and the shared citation entries.
  - Blocked-by: f9ae01u (Write tests for the ranked-causes renderer)
  - Stream: 1
  - Requirements: [5.16](requirements.md#5.16), [6.6](requirements.md#6.6)

- [x] 33. Write tests for the coverage-failure states <!-- id:f9ae01w -->
  - `refused-not-covered` states plainly that the in-scope sources do not cover the question, with no synthesised answer beside it (7.1); the state is visually distinct from error, narrowing and answer (7.2) and names the sources in scope at ask time (7.3).
  - `suggested_sources[]` offers add-to-scope-and-re-ask in one activation from addressable values (7.4); with no suggestion and out-of-scope sources existing, widen-all-and-re-ask is offered — except on `out-of-domain` and `no-manual-for-device`, where it is suppressed rather than costing a wasted turn (7.5); `out-of-domain` states technique-not-control wording with suggestions and widen suppressed and the question re-editable (7.6).
  - `no-manual-for-device` names `required_device` and that ingestion must re-run; where `required_manual` arrives, its `filename` is copyable in one activation and `placeholders[]` names the fields the user fills — never derived by splitting the filename, and never synthesised where the field is absent, where the convention and device are named instead (7.7). The field is dormant today (CONTRACTS §4e) and is exercised against fixture payloads, never hardcoded absent.
  - All-sources-already-in-scope says so, drops widen, and falls through to the filename action or re-editing — the state never dead-ends (7.8, 9.2); under a narrowed scope the gap is attributed to the narrowing in force, not to missing documentation (3.10); every control is keyboard-reachable from the state without traversing the picker (7.10); the widened scope persists and decays per session (7.9).
  - Blocked-by: f9ae01b (Implement turn.svelte.ts), f9ae01d (Implement scope.svelte.ts)
  - Stream: 1
  - Requirements: [3.10](requirements.md#3.10), [7.1](requirements.md#7.1), [7.2](requirements.md#7.2), [7.3](requirements.md#7.3), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [7.6](requirements.md#7.6), [7.7](requirements.md#7.7), [7.8](requirements.md#7.8), [7.9](requirements.md#7.9), [7.10](requirements.md#7.10)

- [x] 34. Implement the coverage-failure renderer <!-- id:f9ae01x -->
  - One renderer with the per-outcome action table of the design: add-and-re-ask, widen-all, suppressed variants, the copyable filename.
  - Blocked-by: f9ae01w (Write tests for the coverage-failure states)
  - Stream: 1
  - Requirements: [3.10](requirements.md#3.10), [7.1](requirements.md#7.1), [7.2](requirements.md#7.2), [7.3](requirements.md#7.3), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [7.6](requirements.md#7.6), [7.7](requirements.md#7.7), [7.8](requirements.md#7.8), [7.9](requirements.md#7.9), [7.10](requirements.md#7.10)

## Phase 7: Waiting states and errors

- [ ] 35. Write tests for waiting states, thresholds and perf marks <!-- id:f9ae01y -->
  - `acknowledged` is entered synchronously in the submit handler, before `fetch` is called, so the acknowledgement paint never waits on the network (8.1, 8.7); the working indicator is unmistakably live and sits below the thread so its removal cannot shift text (8.2, Decision 2); the submitted question stays visible while waiting (8.3).
  - Working, finished and broken are mutually distinguishable by at least two channels each — shape and text, never colour alone (8.4, the channel design behind 8.11); past the per-provider-class threshold, plain "taking longer than usual" text and a cancel control appear — hosted and local thresholds differ and sit above that class's observed median (8.5, 8.10).
  - A user cancel returns to ready with the question preserved and never presents partial output as finished (8.6).
  - Under `prefers-reduced-motion` the indicator becomes an elapsed-seconds counter paired with the static shape — live without motion, still satisfying 8.4; the counter is excluded from the announcement region so it never announces each tick (13.6, Decision 7); no animation exists beyond the indicator and arriving text (11.9).
  - One `aria-live="polite"` region announces state transitions once each — streaming started, finished, failed, coverage failure, partial answer, narrowing with its candidates and that digits select them — while the streamed body stays `aria-live="off"` with `aria-busy` (13.5).
  - perf.svelte.ts marks `submit`, `firstByte` and `firstPaint` (a requestAnimationFrame after DOM insert): 8.9 is firstPaint − firstByte, 8.8 is firstPaint − submit, breaches attributed with the engine's `timings` before any work here; the marks feed 9.3's disclosure. Real-provider p95 measurement is the iterative loop, not this suite.
  - Blocked-by: f9ae01b (Implement turn.svelte.ts)
  - Stream: 1
  - Requirements: [8.1](requirements.md#8.1), [8.2](requirements.md#8.2), [8.3](requirements.md#8.3), [8.4](requirements.md#8.4), [8.5](requirements.md#8.5), [8.6](requirements.md#8.6), [8.7](requirements.md#8.7), [8.8](requirements.md#8.8), [8.9](requirements.md#8.9), [8.10](requirements.md#8.10), [8.11](requirements.md#8.11), [11.9](requirements.md#11.9), [13.5](requirements.md#13.5), [13.6](requirements.md#13.6)

- [ ] 36. Implement the waiting states and perf.svelte.ts <!-- id:f9ae01z -->
  - The turn state machine's visible states, the working indicator with its reduced-motion counter variant, the per-provider-class threshold, the announcement region, and the per-turn marks.
  - Blocked-by: f9ae01y (Write tests for waiting states, thresholds and perf marks)
  - Stream: 1
  - Requirements: [8.1](requirements.md#8.1), [8.2](requirements.md#8.2), [8.3](requirements.md#8.3), [8.4](requirements.md#8.4), [8.5](requirements.md#8.5), [8.6](requirements.md#8.6), [8.7](requirements.md#8.7), [8.8](requirements.md#8.8), [8.9](requirements.md#8.9), [8.10](requirements.md#8.10), [8.11](requirements.md#8.11), [11.9](requirements.md#11.9), [13.5](requirements.md#13.5), [13.6](requirements.md#13.6)

- [ ] 37. Write tests for the error states <!-- id:f9ae020 -->
  - No raw exception text, stack trace or payload as the primary message (9.1); every state states what happened plainly and offers at least one action (9.2); the diagnostic disclosure renders exactly the engine's `detail`, `framing` and `timings` plus the client's per-turn marks — nothing else, nothing parsed out of `detail` — and is also available on any turn carrying `framing: unparsed` (9.3).
  - `provider-unconfigured` keys on the `reason` sub-code and never the wording: no-provider-kind, missing-credential, disclosure-unacknowledged — each opening provider configuration with the typed question preserved; a configured local provider or the shared backend is never unconfigured for lacking a key (9.5).
  - `provider-unreachable` names the provider with retry (9.6); `timeout` attributes the stall to the provider, distinct from unreachable (9.7); `provider-rate-limited` counts down `retry_after` where supplied, enabling retry when it elapses, and states honestly when the provider gave no interval — absence is never a fault and never invented, rounding permitted for display (9.8); `provider-error` with provider-rejected retries with `detail` behind the disclosure (9.9); authentication-failed offers configuration in place of retry — a retry on the same credential cannot succeed — keyed on the sub-code alone (9.10).
  - `unknown-source-id` names the rejected id, drops it from the stored scope, and offers a one-activation re-ask against the remainder (9.11); `no-sources-selected` renders as the 3.2 empty-scope state, never as an unexplained failure (9.12); `corpus-empty` names the manuals/ directory and the ingestion step and disables submission until a source is reported (9.13).
  - `incomplete` and a mid-stream drop retain and mark the partial text with a retry (9.14); a malformed-request rejection renders as a broken state naming what was rejected, never a refusal (9.15); engine-reported `cancelled` for a turn the user did not cancel marks it abandoned — distinct from incomplete and from an error, not disturbing the replacing turn; the client knows who cancelled because it issued the cancellation (9.16).
  - No message contains any part of a key — structural, since the renderer never receives a value that could contain one (9.17); the one-line summary and its action carry the layout 9.18's stand-back test measures; an unknown turn-stream version renders broken naming both versions while an unknown event name within a known version is ignored (9.19).
  - Blocked-by: f9ae01b (Implement turn.svelte.ts)
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1), [9.2](requirements.md#9.2), [9.3](requirements.md#9.3), [9.5](requirements.md#9.5), [9.6](requirements.md#9.6), [9.7](requirements.md#9.7), [9.8](requirements.md#9.8), [9.9](requirements.md#9.9), [9.10](requirements.md#9.10), [9.11](requirements.md#9.11), [9.12](requirements.md#9.12), [9.13](requirements.md#9.13), [9.14](requirements.md#9.14), [9.15](requirements.md#9.15), [9.16](requirements.md#9.16), [9.17](requirements.md#9.17), [9.18](requirements.md#9.18), [9.19](requirements.md#9.19)

- [ ] 38. Implement the error renderers and diagnostics disclosure <!-- id:f9ae021 -->
  - The per-outcome error renderers of the design's outcome table, the reason-keyed wording and controls, the countdown, and the disclosure.
  - Blocked-by: f9ae020 (Write tests for the error states)
  - Stream: 1
  - Requirements: [9.1](requirements.md#9.1), [9.2](requirements.md#9.2), [9.3](requirements.md#9.3), [9.5](requirements.md#9.5), [9.6](requirements.md#9.6), [9.7](requirements.md#9.7), [9.8](requirements.md#9.8), [9.9](requirements.md#9.9), [9.10](requirements.md#9.10), [9.11](requirements.md#9.11), [9.12](requirements.md#9.12), [9.13](requirements.md#9.13), [9.14](requirements.md#9.14), [9.15](requirements.md#9.15), [9.16](requirements.md#9.16), [9.17](requirements.md#9.17), [9.18](requirements.md#9.18), [9.19](requirements.md#9.19)

## Phase 8: Picker, provider configuration and history panel

- [ ] 39. Write tests for the source picker component <!-- id:f9ae022 -->
  - Every source independently toggleable by keyboard alone (2.2); single all and none controls (2.8); indicator states: all-sources stated explicitly (2.7), ≤3 sources named rather than counted (2.6, 3.3), otherwise n of m, visible while asking and reading (2.5); the narrowed state is distinct from all-sources by shape and label, not colour, and survives greyscale (3.10, 11.6).
  - An `authored-triage` source lists alongside the manuals with its kind stated, selectable by exactly the same controls — never a gap, never unselectable, never always-in-scope (2.12).
  - The known-gaps group lists owned-but-undocumented hardware apart and never selectable, and is omitted entirely — heading included — when the report is empty, which is the live case; the populated group is exercised against a fixture (2.9); assumed-applicability sources carry the revision they are taken to describe (2.10), and `low_text` marks a sparse source on its entry — picker marking is the whole consumption obligation CONTRACTS §1 places on the field.
  - Collapsible to the one-line indicator, collapsed at rest once a scope is chosen, one activation each way (2.11); the substring filter over `display_name` appears past the 2.13 threshold and costs no chrome below it; in/out-of-scope is carried by a filled-versus-hollow marker plus the word — the across-the-room read of 2.14 is the iterative loop's stand-back test.
  - Every control exposes an accessible name and every toggle its state (13.4).
  - Blocked-by: f9ae01d (Implement scope.svelte.ts), f9ae01f (Implement sources.svelte.ts)
  - Stream: 2
  - Requirements: [2.2](requirements.md#2.2), [2.5](requirements.md#2.5), [2.6](requirements.md#2.6), [2.7](requirements.md#2.7), [2.8](requirements.md#2.8), [2.9](requirements.md#2.9), [2.10](requirements.md#2.10), [2.11](requirements.md#2.11), [2.12](requirements.md#2.12), [2.13](requirements.md#2.13), [2.14](requirements.md#2.14), [3.3](requirements.md#3.3), [3.10](requirements.md#3.10), [11.6](requirements.md#11.6), [13.4](requirements.md#13.4)

- [ ] 40. Implement the source picker <!-- id:f9ae023 -->
  - The three groups of the design — selectable, marked selectable (assumed applicability and `low_text`), known gaps — plus the scope indicator and the collapse behaviour.
  - Blocked-by: f9ae022 (Write tests for the source picker component)
  - Stream: 2
  - Requirements: [2.2](requirements.md#2.2), [2.5](requirements.md#2.5), [2.6](requirements.md#2.6), [2.7](requirements.md#2.7), [2.8](requirements.md#2.8), [2.9](requirements.md#2.9), [2.10](requirements.md#2.10), [2.11](requirements.md#2.11), [2.12](requirements.md#2.12), [2.13](requirements.md#2.13), [2.14](requirements.md#2.14), [3.3](requirements.md#3.3), [3.10](requirements.md#3.10), [11.6](requirements.md#11.6), [13.4](requirements.md#13.4)

- [ ] 41. Write tests for provider configuration <!-- id:f9ae024 -->
  - Kind is chosen first — keyed hosted, local, or the shared backend — and credential entry is requested only for the keyed hosted kind (10.1); a local provider is configured once its endpoint or model is chosen and is never asked for a key (10.3).
  - The shared-backend disclosure that question text and passages leave the machine blocks the first turn until explicitly acknowledged, stays readable afterwards, and the acknowledgement is stored against the backend's identity so changing backend re-arms it (10.4).
  - The key input masks by default with a momentary reveal of the value being typed (10.5); a saved key is never displayed in full again and no input is ever pre-populated — the field is always empty on open and the engine's masked tail is the only representation (10.6); the indication renders from GET /provider, the engine's reported status, never the browser's stored settings, showing kind, provider and at most the final four characters (10.7).
  - Replace and clear both work, clearing effective on the next submission (10.8); the key travels only in the PUT body — never the title, URL, browser history or question history (10.9); test-provider reports reachable-as-configured without echoing any credential (10.10); saving returns to the ask surface with question and scope intact (10.2, 10.11).
  - Blocked-by: f9ae015 (Implement client.ts)
  - Stream: 2
  - Requirements: [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.3](requirements.md#10.3), [10.4](requirements.md#10.4), [10.5](requirements.md#10.5), [10.6](requirements.md#10.6), [10.7](requirements.md#10.7), [10.8](requirements.md#10.8), [10.9](requirements.md#10.9), [10.10](requirements.md#10.10), [10.11](requirements.md#10.11)

- [ ] 42. Implement provider.svelte.ts and the configuration surface <!-- id:f9ae025 -->
  - The provider status store and the configuration region, kind-first, backed by the five provider operations.
  - Blocked-by: f9ae024 (Write tests for provider configuration)
  - Stream: 2
  - Requirements: [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.3](requirements.md#10.3), [10.4](requirements.md#10.4), [10.5](requirements.md#10.5), [10.6](requirements.md#10.6), [10.7](requirements.md#10.7), [10.8](requirements.md#10.8), [10.9](requirements.md#10.9), [10.10](requirements.md#10.10), [10.11](requirements.md#10.11)

- [ ] 43. Write tests for the history panel <!-- id:f9ae026 -->
  - Reverse-chronological entries showing at least the question text and when it was asked (12.2); selecting one re-displays the stored answer with its citations and no engine query (12.3); the scope in force at ask time is shown (12.4).
  - Re-ask runs against the current scope and begins a new conversation — `conversation_id: null` — producing a new exchange rather than overwriting the old; continuing a thread stays available by typing a follow-up (12.5).
  - Clear-all in one action behind a confirmation step (12.6); the panel is off the ask surface, reachable and dismissible in one activation each (12.8).
  - Blocked-by: f9ae01h (Implement history.svelte.ts)
  - Stream: 2
  - Requirements: [12.2](requirements.md#12.2), [12.3](requirements.md#12.3), [12.4](requirements.md#12.4), [12.5](requirements.md#12.5), [12.6](requirements.md#12.6), [12.8](requirements.md#12.8)

- [ ] 44. Implement the history panel <!-- id:f9ae027 -->
  - The panel region over history.svelte.ts, with re-display, re-ask and clear.
  - Blocked-by: f9ae026 (Write tests for the history panel)
  - Stream: 2
  - Requirements: [12.2](requirements.md#12.2), [12.3](requirements.md#12.3), [12.4](requirements.md#12.4), [12.5](requirements.md#12.5), [12.6](requirements.md#12.6), [12.8](requirements.md#12.8)

## Phase 9: Assembly and browser verification

- [ ] 45. Write integration tests over a stubbed engine <!-- id:f9ae028 -->
  - A fake SSE server standing in for the engine, per the design's testing strategy — no provider, corpus or key needed by any test; full turns exercised through client → sse → reducer → renderer for each renderer family: answer, partial, narrowing, ranked causes, coverage failure, and each error outcome.
  - The keyboard-only core loop asserted end to end at component level — ask, narrow, cancel, widen scope, expand a citation and open it (1.13).
  - Region transitions preserve the typed question and the scope: into and out of provider configuration and history (10.2, 10.11).
  - Event coverage re-checked at the integrated level: every CONTRACTS §4b event discharges into something visible, so a wiring gap cannot pass the unit suites and still drop an event.
  - Blocked-by: f9ae01l (Implement the ask input, symptom shortcuts and thread shell), f9ae01n (Implement the answer renderer), f9ae01r (Implement passage expansion and openAtSource), f9ae01t (Implement the narrowing renderer), f9ae01v (Implement the ranked-causes renderer), f9ae01x (Implement the coverage-failure renderer), f9ae01z (Implement the waiting states and perf.svelte.ts), f9ae021 (Implement the error renderers and diagnostics disclosure), f9ae023 (Implement the source picker), f9ae025 (Implement provider.svelte.ts and the configuration surface), f9ae027 (Implement the history panel)
  - Stream: 1
  - Requirements: [1.13](requirements.md#1.13), [10.2](requirements.md#10.2), [10.11](requirements.md#10.11)

- [ ] 46. Assemble the page and wire the regions <!-- id:f9ae029 -->
  - +page.svelte as the one surface: scope bar, thread, ask input; picker, history, provider configuration and expanded passages as regions, not routes — navigation would discard the typed question and scope, which 10.2 and 10.11 forbid.
  - The picker expands in place under the scope bar pushing the thread down — legal because 4.2 constrains movement while streaming and expansion is a deliberate activation; collapsed at rest once a scope is chosen (2.11).
  - Overlay regions never trap focus, each dismissed with Escape returning focus to its opener; history one activation each way (12.8); chrome laid out toward 11.8's ≥ 70% content at 1280×800 collapsed.
  - Wiring of already-tested components — no new behaviour, so the integration suite of the previous task is its red state.
  - Blocked-by: f9ae028 (Write integration tests over a stubbed engine)
  - Stream: 1
  - Requirements: [2.11](requirements.md#2.11), [11.8](requirements.md#11.8), [12.8](requirements.md#12.8)

- [ ] 47. Add the Playwright browser and accessibility suite <!-- id:f9ae02a -->
  - No-reflow: over a scripted stream, the `top` of every already-painted line is unchanged at every subsequent frame (4.2) — the browser-level proof of Decision 2.
  - Keyboard-only loop with zero pointer use: ask, narrow, cancel, widen scope, expand a citation and open it (1.13, 13.1); each region dismissed with Escape returns focus to its opener (13.3); expanding and collapsing a citation mid-stream leaves it at the same viewport offset (5.8).
  - Open at source: a vendor-manual citation activates a link whose fragment is exactly `#page=N` with nothing appended; an authored citation reveals the entry in place with `entry_location` copyable and no navigation leaving the tab (5.5).
  - A greyscale screenshot preserves every 11.6 distinction; no horizontal scrolling or clipped control at 200% browser text size (13.7); under reduced motion the counter and static shape keep working/finished/broken distinguishable (13.6); a full turn announces each state transition once and never a streamed fragment (13.5); question plus answer occupy ≥ 70% of viewport height at rest on 1280×800 with the picker collapsed (11.8).
  - axe-core floor over every rendered state: accessible names and toggle states (13.4), visible focus indicator at its contrast in every interactive state (13.2, 13.8).
  - Blocked-by: f9ae029 (Assemble the page and wire the regions)
  - Stream: 1
  - Requirements: [1.13](requirements.md#1.13), [4.2](requirements.md#4.2), [5.5](requirements.md#5.5), [5.8](requirements.md#5.8), [11.6](requirements.md#11.6), [11.8](requirements.md#11.8), [13.1](requirements.md#13.1), [13.2](requirements.md#13.2), [13.3](requirements.md#13.3), [13.4](requirements.md#13.4), [13.5](requirements.md#13.5), [13.6](requirements.md#13.6), [13.7](requirements.md#13.7), [13.8](requirements.md#13.8)
