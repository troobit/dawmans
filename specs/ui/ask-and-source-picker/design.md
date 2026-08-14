# Design: Ask and Source Picker

**Domain:** `ui` · **Capability:** ask and source picker · **Status:** draft

Implements [`requirements.md`](requirements.md). Shared records, the outcome taxonomy and the latency
budget are governed by [`CONTRACTS.md`](../../CONTRACTS.md); where this design and that file disagree,
that file wins and this design is the defect.

This document records the **how**. It does not restate a requirement, and where it takes a position
against one, the position is named in [Requirements defects to reconcile](#requirements-defects-to-reconcile)
rather than applied silently.

---

## Overview

One page, one process to talk to, no router. The surface is a **SvelteKit SPA built to static assets
and served by the `api/answer-engine` process itself**, so the browser's origin is the engine's
origin. Everything it knows arrives over the engine's loopback HTTP surface; it never reads the
corpus, the index, or the filesystem.

Three properties drive every structural choice below, in this order:

1. **Nothing already painted may move** (4.2). This forces an append-only renderer, block types
   decided by a block's first line, and citation markers of fixed width.
2. **Hands-full operation** (1.2, 1.10, 1.11, 6.3, 13.1). This forces one keyboard router owning the
   whole surface rather than per-component handlers, and an explicit registry of which keys are armed.
3. **Costing nothing to leave** (1.12). This forbids hover-dependent affordances anywhere, and keeps
   the turn alive in a `fetch` stream that has no relationship to window focus.

## Architecture

### Delivery model

```
web/                          SvelteKit, pnpm
  src/routes/+layout.ts       ssr = false, prerender = true
  src/routes/+page.svelte     the one surface
  build/                      static output, mounted by the engine at /
```

`ssr = false` because there is no server to render on: the counterpart is a Python process, and
every value on the page comes from a runtime call to it. `prerender = true` emits a static shell so
first paint costs no round trip, which is what leaves room in 8.7's 150 ms acknowledgement budget.

**Same origin is load-bearing, not convenience.** `api/answer-engine` 9.3 rejects any request whose
`Origin` is outside `{127.0.0.1:<port>, localhost:<port>, [::1]:<port>}` — the check that closes DNS
rebinding. A separately-served front end on `:5173` is *outside* that set and would be rejected, so
either the engine's guard would have to be widened (weakening the one control that closes rebinding)
or the page must share the engine's origin. It shares the origin:

- **Production** — the engine mounts `web/build` at `/`. Requests to `/turn`, `/sources`, `/provider`
  are same-origin and relative; the client hard-codes no host and no port.
- **Development** — `make dev` runs both processes (Decision 10). `vite dev` proxies `/turn`,
  `/passages`, `/sources`, `/provider` to the engine. `changeOrigin: true` rewrites `Host`, but
  **Vite forwards the browser's `Origin` unchanged**, so a proxied request still arrives carrying
  `Origin: http://localhost:5173` and is rejected by the engine's guard. The proxy therefore also
  rewrites `Origin` to the engine's own origin in a `proxyReq` hook. The proxy is local dev tooling
  on the trust boundary's inside; the browser never reaches the engine directly in dev.

Rewriting in the proxy is preferred over relaxing the engine's guard to *any* loopback port, because
it keeps one strict rule in both dev and production rather than a weaker rule everywhere to serve a
dev-only case.

The static mount is an addition to the engine's HTTP surface table; see defect 5.

### Surfaces

One page. The picker, history, provider configuration and expanded passages are **regions of it**,
not routes — navigating away would discard the typed question and the scope, which 10.2 and 10.11
forbid, and a router would buy nothing a single operator can use.

```
┌────────────────────────────────────────────────┐
│ scope bar — indicator (2.5) · picker toggle    │  chrome
│             (2.11) · history · provider (10.2) │
├────────────────────────────────────────────────┤
│ thread — turns, oldest first                   │
│   question · state · answer · citations        │  content (11.8: ≥70%)
│   narrowing · coverage failure · error         │
├────────────────────────────────────────────────┤
│ ask input (1.1) · shortcuts while empty (1.10) │  content
└────────────────────────────────────────────────┘
```

The picker expands **in place under the scope bar**, pushing the thread down. That violates nothing:
4.2 constrains movement *while streaming*, and the picker cannot be expanded from the keyboard
without a deliberate activation. It is collapsed at rest once a scope is chosen (2.11), which is the
state 11.8 is measured in.

Overlay regions (picker, history, provider) are `inert`-free and never trap focus: each is dismissed
with `Escape`, returning focus to the control that opened it (13.3).

### Module placement

```
web/src/lib/
  engine/
    records.ts        CONTRACTS §1–§4 and §6 as types — the only place they are written down
    client.ts         the operations, typed; no state
    sse.ts            SSE frame parser over a ReadableStream
    turn.svelte.ts    the event → Turn reducer (append-only)
  state/
    sources.svelte.ts available sources + both gap reports (2.1, 2.9, 2.10)
    scope.svelte.ts   selection, persistence, decay (§3)
    thread.svelte.ts  the conversation on screen (1.7, 1.8, §6)
    history.svelte.ts persisted exchanges (§12)
    provider.svelte.ts provider status and configuration (§10)
    perf.svelte.ts    per-turn marks for 8.7, 8.8, 8.9 and the 9.3 disclosure
  keys.ts             the keyboard router and the arming registry (1.2, 1.11, 6.3)
  components/         presentation only; no fetching, no persistence
```

Every module under `state/` exports a **class instance**, not a bare `$state` variable: a reassigned
`export let` declared with `$state` is not reactive across a module boundary, because the compiler
rewrites references per file. Class fields declared `$state` survive the boundary intact.

`components/` never calls `client.ts`. A component that fetched its own data would make 5.18's
prefetch and 8.9's paint measurement unobservable, and would put a network call behind a render.

### The turn, client-side

```
  idle ──submit(1.3)──▶ acknowledged ──first event──▶ streaming ──done──▶ settled
   ▲                        │                            │                 │
   │                        └──────── error/cancel ──────┴─────────────────┘
   └──────────────────────────── new question / clear thread (1.7) ─────────┘
```

`acknowledged` exists as a distinct state solely to satisfy 8.7: it is entered **synchronously in the
submit handler**, before `fetch` is called, so the acknowledgement paint never waits on the network.
`streaming` is entered on the first SSE event of any kind, which is what makes 8.2's working
indicator replaceable the moment content exists.

## Components and Interfaces

### The engine client

The nine operations `api/answer-engine` 9.4 names, mapped to the routes its design fixes:

| Operation | Call | Consumed by |
|---|---|---|
| submit-question | `POST /turn` → SSE | §4, §6, §7, §8, §9 |
| fetch-passage | `GET /passages/{passage_id}` | 5.6, 5.11, and 5.5's authored branch |
| list-sources | `GET /sources` | §2, 2.9, 2.10, 9.13 |
| get-provider-status | `GET /provider` | 10.7 |
| set-provider | `PUT /provider` | 10.1, 10.3 |
| set-credential | `PUT /provider/credential` | 10.5 |
| clear-credential | `DELETE /provider/credential` | 10.8 |
| test-provider | `POST /provider/test` | 10.10 |
| serve-document | `GET /sources/{source_id}/document` | 5.5's vendor-manual branch |

`openAtSource()` is two branches and no third. For a `vendor-manual` it is a plain link activation —
`target="_blank"`, `rel="noopener"`, `href` the serve-document route with the fragment `#page=N` and
**nothing appended**; a link activation is not a popup, so "one activation" holds without fighting a
popup blocker, and appending `&zoom=` or a text directive would silently disable the jump in Safari's
viewer. For an `authored-triage` citation it is the ordinary passage expansion of 5.6 plus the
copyable `entry_location`. A 404 from serve-document degrades the citation to its string form
(5.11), never to a broken action.

`client.ts` is stateless and returns parsed records. It performs **no retries**: a retry that the
user did not ask for would either duplicate a turn or mask the `provider-unreachable` state that 9.6
requires the user to see.

### SSE framing and the turn reducer

Streaming is `fetch` + `ReadableStream`, not `EventSource`, because the request carries a question
and a source list in its body and `EventSource` cannot POST. `sse.ts` decodes UTF-8 incrementally
(`TextDecoder` with `{stream: true}` — a multi-byte character split across two network chunks would
otherwise paint as `U+FFFD` and be indistinguishable from a `degraded` passage), splits on `\n\n`,
and yields `{event, data}`.

The reducer fills the envelope from **CONTRACTS §4b's sixteen events**, and **only ever appends**.
The table is that one, per client effect; the rendering obligation itself lives on the field in §4.

| Event | Effect |
|---|---|
| `scope_dropped` | Fills `scope_dropped[]`; reported with the turn (3.11) |
| `outcome` | Fixes which renderer the turn uses (§4 / §6 / §7 / §9), and carries `reason`, `retry_after` and `detail` with it, so an error state paints once rather than being amended |
| `direct_answer` | The first painted content; the 8.8 measurement lands here |
| `body_delta` | Appended to the block parser below |
| `citation` | Added to the turn's citation map, keyed by `passage_id` |
| `cause` | Appended to `causes[]` in rank order; `rank` is asserted equal to position (6.6) |
| `contributing_sources` | 4.7 |
| `uncovered_parts` | 4.8, 4.9 |
| `suggested_sources` | 7.4 — addressable `{source_id, display_name}`, not a substring of the body |
| `narrowing` | §6 |
| `required_device` | 7.7 |
| `required_manual` | 7.7 — the copyable filename and its `placeholders[]` |
| `ungrounded` | 5.13 — marks text already on screen; never blanks it |
| `framing` | 9.3's disclosure, which for `unparsed` opens on a successful turn too |
| `timings` | 8.8 attribution, and the 9.3 disclosure |
| `done` | `settled`; focus returns to an empty input (1.6) |

**Three unknown-member rules, and they differ deliberately** (CONTRACTS §4b). An event **name** not
in this table is ignored and never fails the turn, so an added event does not break a running client.
An **`outcome` value** not in CONTRACTS §6 renders as a broken state carrying `detail` (9.4), because
an outcome selects the renderer and a turn whose renderer is unknown cannot be trusted to any of
them. A **`body` block type** the parser does not know keeps its text and loses only its wrapper
(4.4) — dropping it would make a `!caveat` vanish rather than degrade.

**Absence of `done` is a failure, not a completion.** The reader treats end-of-stream without `done`
as `incomplete` and marks what arrived (9.14); it does not infer completion from the stream closing,
because a stream truncated mid-event discards the pending event silently. There is no reconnection:
`fetch` + `ReadableStream` inherits none of `EventSource`'s retry machinery. The response's
`dawmans/turn-stream/*` header is checked before the body is read, and an unknown version refuses the
turn by name (9.19).

### Streaming without reflow

4.2 is the hardest constraint on this surface, and it is met structurally rather than by care.

**Block type is decided by a block's first line and never revised.** CONTRACTS §4d fixes the closed
set, all identifiable at column 0 — `## `, `N. `, `- `, paragraph, `!caveat` and `!conflict`. The
parser holds the current line only until its prefix is decidable (at most 10 characters — the longest
prefix is `!conflict `), fixes the block type, and streams the remainder into that block. A block
already on screen is therefore never re-typed and never re-flowed. That rule outranks a producer
obligation: `!conflict` is specified to carry exactly two readings, and a block arriving with some
other count is rendered as the conflict block it declared itself to be, with the readings it
supplied — **never re-typed to a paragraph**, which would move painted text. `!suggest` is no longer
in this set; it arrives as an envelope field.

This buffering costs nothing against 8.8: `direct_answer` arrives as its own event, ahead of any
`body_delta`, so the *first painted token* never waits on prefix disambiguation.

**Citation markers are fixed-width numeric superscripts.** Inline markers arrive in the body text as
`[[p:<passage_id>]]`. Painting the raw marker and replacing it later would reflow the line, so the
parser buffers from `[` until the marker either completes or is disproved. Each distinct
`passage_id` is assigned the next integer **in order of first appearance** and painted as that
integer immediately — the number is stable and its width does not change when the matching
`citation` event arrives (which may be later). Everything the citation *says* renders in the citation
list below the answer, never in the prose.

That placement is what keeps §5's five inline obligations — `kind` (5.14), `doc_version` (5.2),
`hardware_applicability` (5.3), `unbacked` (5.16), `has_figures` (5.4) — compatible with 11.7's
25-word reading budget. "Inline" in CONTRACTS §3 means *on the citation, not behind a disclosure*;
it does not mean *in the sentence*. Five caveats rendered mid-prose would breach 11.7 on the first
citation.

**The working indicator sits below the thread**, never above it, so its removal cannot shift text.

### Citations

| Concern | Approach |
|---|---|
| Rendering (5.1, 5.15) | Location slot is `section_number` + `section_title` + page where present; for a pageless source the entry's symptom title occupies the slot and page and section render as absent. Nothing is synthesised. |
| Expansion (5.6, 5.7) | `GET /passages/{id}` on activation; revealed in place under the citation entry. Cached in a `Map` for the session — a passage's text cannot change without a re-ingestion, which changes the `passage_id`. |
| Speed (5.18) | Prefetched **on focus**, not on hover (1.12). Focus precedes activation by at least one keystroke, so the ≤150 ms target is met by cache hit in the ordinary case; a miss shows the working indicator past 300 ms rather than an empty area. |
| Reading position (5.8) | Before expanding, record the citation element's `getBoundingClientRect().top`. After collapsing, scroll so it is at the same viewport offset. Restoring `scrollY` alone is wrong: content above may have grown while streaming continued. |
| Degraded text (5.10) | Marked on the expanded passage, distinct from the "unavailable" state of 5.11. |
| Failure (5.11) | The citation keeps its location, its marks and its open-at-source action; only the passage body reports unavailable. |
| Uncited answers (5.12, 5.13) | `5.12` is a property of the settled turn (`citations.size === 0`); `ungrounded` is an engine assertion arriving after `done` and marks the rendered text without touching it. |

### Keyboard routing and arming

One `keydown` listener on `window`, in `keys.ts`. Per-component handlers would make 1.11's arming
rule unenforceable, because no component can know what another has armed.

```
keydown ─▶ modifier held (ctrl/meta/alt)?        ─ yes ▶ pass through
        ─▶ target is input/textarea/editable?    ─ yes ▶ pass through
        ─▶ Escape?                               ─ yes ▶ dismiss topmost region (13.3)
        ─▶ digit 1–4 and arming registry non-empty? ─ yes ▶ activate that entry (1.11, 6.3)
        ─▶ single printable character?           ─ yes ▶ focus input, insert it (1.2)
        ─▶ otherwise                                    ▶ pass through
```

The registry holds at most one armed set at a time — narrowing candidates (6.3) or symptom shortcuts
(1.10), never both, since shortcuts show only on an empty input and a narrowing turn has a question
in flight. Whatever is armed renders its digit next to each entry, which is 1.11's on-screen
indication and 11.6's greyscale-safe channel for it.

The character in 1.2 must be **inserted manually** after focusing: the `keydown` already happened on
another element, so focusing the input does not deliver it. `preventDefault` then append.

`svelte:window onfocus` restores focus to the input (1.1) **unless** an overlay region holds focus —
stealing it would break the return-focus contract of 13.3.

### The source picker

`GET /sources` returns `SourceRecord[]` plus both gap reports. The picker renders three groups:

1. **Selectable sources** — every record, of both kinds. An `authored-triage` record sits among the
   manuals with its kind stated on its entry, selectable by the same controls (2.12). Nothing about
   it is special-cased: treating it as always-in-scope or as a gap is explicitly forbidden.
2. **Marked selectable sources** — a record whose `hardware_applicability` is *assumed* carries the
   revision it is taken to describe (2.10), and `low_text` marks a sparse source.
3. **Known gaps** — the owned-but-undocumented report, listed apart and never selectable (2.9).

Newness (2.4) is `source_id ∉ seen[]`, where `seen[]` is persisted and updated on the next submit —
not on render, so a source seen in a glance the user did not act on is still new.

Scope indicator states (2.5–2.7, 3.3, 3.10): *all sources* · *n named sources* (≤3) · *n of m*, with
the narrowed state visually distinct from the all-sources state through shape and label, not colour
(11.6). The count comes from the engine's list, never a constant (2.1).

The filter promised at 12+ sources (2.13) is a plain substring match over `display_name`, rendered
only past that count so it costs no chrome in the three-source case that exists today.

### Scope state, persistence and decay

```ts
// localStorage: dawmans.scope
{ selected: string[], seen: string[], lastQuestionAt: number, released?: string[] }
// sessionStorage: dawmans.session — presence alone is the signal
```

**The session boundary is `sessionStorage`, not a timestamp.** 3.6 fires on "the first load after a
browser restart, or a load more than 8 hours after the last submitted question". `sessionStorage` is
cleared by a browser restart and survives a reload — which is exactly the first clause, with no
clock involved. The 8-hour rule is the second clause, checked against `lastQuestionAt`. Either
triggers release.

On load:

1. No stored scope → all available sources (3.7).
2. Stored scope, same session, within 8 h → restore, dropping ids the engine no longer reports,
   silently (3.8).
3. Stored scope narrower than all available, **and** a new session → restore to all available, keep
   the narrowing in `released`, and state that it was released with a one-activation reinstate (3.6).

A narrowed scope that already equals all available sources releases nothing, so the notice never
appears spuriously.

Zero sources in scope **blocks** submission (3.1, 3.2) — the client does not send an empty scope, and
`no-sources-selected` from the engine renders as the same blocked state rather than as a failure
(9.12). Scope changes mid-answer touch only the next turn (3.9).

### Narrowing and ranked causes

`needs-narrowing` renders the question and its 2–4 candidates in the engine's order, each numbered
and armed (6.2, 6.3), each activating a **follow-up turn in the same thread** against the unchanged
scope (6.4). The question and the chosen candidate stay visible in the thread, and the exchange is
retained as part of that thread rather than as a standalone unanswered question (6.7).

Typing any printable character other than an armed digit begins a free-text reply without dismissing
the list (6.5) — which falls out of the keyboard router above at no extra cost.

A **ranked cause list** is the `ranked-causes` outcome carrying `causes[]` (CONTRACTS §4c). It
renders in array order with each `rank` shown, each cause with its `check` and with the citations its
`cites[]` and `fix_cites[]` name — **resolved through the turn's own citation map by `passage_id`**,
which is why a `Cause` carries ids and not citation records: the map is already keyed that way, and a
second citation channel would make §5's inline obligations something to satisfy twice. A cause whose
`fix_cites[]` is empty carries the `unbacked` mark of 5.16. The first cause is not promoted to an
answer, and the causes are **not** armed digit controls — that affordance belongs to narrowing
candidates alone (6.2, 6.3), and it is the only thing keeping two similar-looking shapes apart. The
rank-1 cause's check arrives as `direct_answer`, so 4.10 and 11.7 stay reachable on a turn whose body
is four things to check.

### Coverage failure, errors, and the outcome table

Every outcome in CONTRACTS §6 maps to exactly one renderer. The table is exhaustive by construction:
`records.ts` types `outcome` as a union of the taxonomy, and the renderer is a total function over
it, so adding a member to the union without a renderer fails the type check rather than at runtime.

| Outcome | Renderer | Actions offered |
|---|---|---|
| `answered`, `partially-answered` | Answer (§4) | Partial: re-ask each uncovered part alone (4.9) |
| `needs-narrowing` | Narrowing (§6) | Candidates 1–4; free-text reply |
| `ranked-causes` | Ranked causes (§6, 6.6) | No per-cause control — findings to read, not candidates that re-ask; the causes' citations expand and open like any other, and the ordinary follow-up input remains the way forward |
| `refused-not-covered` | Coverage failure (§7) | Add named sources and re-ask (7.4); else widen-all and re-ask (7.5) |
| `out-of-domain` | Coverage failure, technique wording (7.6) | Re-edit only; suggestions and widen suppressed |
| `no-manual-for-device` | Coverage failure (7.7) | Copy the exact filename; suggestions and widen suppressed |
| `no-sources-selected` | Empty-scope state (9.12 → 3.2) | Select all |
| `unknown-source-id` | Error (9.11) | Drop id, re-ask against the remainder |
| `corpus-empty` | Error (9.13) | Names `manuals/` and the ingestion step; submission disabled |
| `provider-unconfigured` | Error (9.5) | Open provider configuration, question preserved |
| `provider-unreachable` | Error (9.6) | Retry |
| `provider-rate-limited` | Error (9.8) | Countdown; retry enabled when it elapses |
| `provider-error` | Error (9.9) | Retry — **or** open configuration where the cause is a credential (9.10) |
| `timeout` | Error (9.7), distinct from unreachable | Retry |
| `incomplete` | Answer, marked incomplete (9.14) | Retry; partial text retained |
| `cancelled` | Abandoned turn (9.16) or ready state (8.6) | Depends on who cancelled |

`cancelled` is the one outcome whose rendering depends on client knowledge the engine does not have:
a turn the user stopped (1.9, 8.6) returns to a ready state with the question preserved, while a turn
the engine cancelled because a new question arrived is marked abandoned and left undisturbed (9.16).
The client already knows which, because it issued the cancellation.

Widen-and-retry persists the widened scope (7.9) rather than reverting it, and that widened scope
decays at the next session like any other. When all sources were already in scope, the widen control
is not offered and the state falls through to the filename action or to re-editing (7.8) — no state
dead-ends (9.2).

### Provider configuration

Kind first, credential only where the kind needs one (10.1, 10.3). The surface renders from
`GET /provider` — the engine's reported status, not the browser's stored settings (10.7) — so a key
the engine cannot use is never reported as configured.

- The key input is **always empty** on open and is never pre-populated (10.6). The stored key is
  represented only by the engine's masked tail.
- Masked by default with a momentary reveal of the value being typed (10.5).
- The shared-backend disclosure (10.4) blocks the first turn until acknowledged, and remains readable
  on the surface afterwards. The acknowledgement is stored locally against the backend's identity, so
  changing backend re-arms it.
- The key travels only in a `PUT /provider/credential` body — never a query string, never the title,
  never history (10.9). Saving returns to the ask surface with question and scope intact (10.11).

### History

Reverse-chronological, off the ask surface, one activation each way (12.8, 12.2). An entry stores the
question, the envelope, the citation records, the scope at the time, and a timestamp — **not passage
text**, which is refetched on demand and would otherwise dominate the quota.

Persistence is `localStorage`, read **lazily when the panel first opens**. Parsing 50 exchanges on
boot would come out of 8.7's acknowledgement budget for no benefit, since history is not on screen at
rest. Writing happens on `settled`, trimming to the most recent 50 (12.9); a `QuotaExceededError`
drops oldest entries until the write succeeds rather than failing the turn.

Re-asking a retained question (12.5) starts a **new conversation** — `conversation_id: null` — and
produces a new exchange. Continuing a thread remains available by typing a follow-up. Cancelled and
failed exchanges are not retained as answers; a partial retained under 9.14 is marked incomplete
(12.7).

## Data Models

`records.ts` mirrors CONTRACTS §1–§4e exactly: no field added, none dropped, `outcome` typed as the
union of §6 and `reason` as the union of §6a. Optionality follows the contract's own rules —
`section_number`, `page_start`, `page_end` and `doc_version` are optional because a pageless or
unnumbered source has none; `entry_location` because only an authored citation has one;
`suggested_sources[]`, `causes[]`, `required_manual`, `scope_dropped[]`, `retry_after` and `detail`
because each is scoped to particular outcomes. The renderer treats absent as *absent*, never as empty
string, zero, or an empty array — an empty `suggested_sources[]` would assert that the engine looked
and found nothing, which is a different claim from its having made no suggestion.

Client-only types, which cross no spec boundary:

```ts
type TurnState = 'acknowledged' | 'streaming' | 'settled' | 'failed'
type Turn = {
  question: string
  state: TurnState
  envelope: Partial<AnswerEnvelope>       // filled by the reducer as events arrive
  blocks: Block[]                          // append-only
  citations: Map<string, Citation>         // by passage_id
  markers: string[]                        // passage_id by first appearance → the printed integer
  scopeAtAsk: string[]
  marks: { submit: number, firstByte?: number, firstPaint?: number }
}
```

`blocks` is `$state.raw` and replaced by append rather than mutated: the array is long, deeply
reactive proxying of every streamed block would cost more than it buys, and nothing mutates a block
after its text is final.

## Legibility, colour and motion

§11 and §13 are targets, converged on by observing real output (`PROCESS.md` §5). Two of them are
nonetheless **computable**, and are asserted rather than eyeballed.

Design tokens live in one CSS file as custom properties: background, surface, body text, secondary
text, accent, and the four state colours. Contrast (11.3, 11.4) and background luminance (11.5) are
computed from those token values **in a unit test** — WCAG relative luminance is arithmetic over the
declared colours, so the floors hold as a hard check even though the criterion is a target. A token
change that breaches a floor fails the build; a stand-back test is not needed to catch it.

The 11.3-versus-11.5 tension the requirements record resolves as they direct: the background sits at
the lighter end of 11.5's band so body text reaches its contrast target without going to pure white.

**Colour independence (11.6).** Every state distinction carries a second channel: in/out of scope by
a filled versus hollow marker and the word; working/finished/broken by shape and label; cited/uncited
by the presence of the numeric marker; authored/manufacturer by a stated kind word on the citation;
backed/unbacked by an explicit mark; armed digits by the printed digit itself. A greyscale screenshot
test in Playwright covers the set.

**Motion and reduced motion (11.9, 13.6, 8.2).** The only animation is the working indicator and the
arrival of text. Under `prefers-reduced-motion`, 8.2 still demands something "unmistakably live" —
resolved by an **elapsed-seconds counter**, which is live and textual without being motion, paired
with the static shape 8.4 requires. This also serves 8.5: the counter is already the thing that
crosses the per-provider threshold (8.10).

**Announcements (13.5).** One `aria-live="polite"` region carries state transitions only — streaming
started, finished, failed, coverage failure, partial answer, narrowing. The streamed body is
`aria-live="off"` with `aria-busy` while streaming, so fragments are never announced individually. A
narrowing announcement names the candidates and that number keys select them.

**Measurement (8.7, 8.8, 8.9).** `perf.svelte.ts` marks `submit` in the submit handler, `firstByte`
when the first content event leaves the SSE reader, and `firstPaint` in a `requestAnimationFrame`
callback after that content is in the DOM. 8.9 is `firstPaint − firstByte` and is wholly
client-side; 8.8 is `firstPaint − submit`; a breach is attributed with the engine's `timings` before
any work is done here. The marks are what the 9.3 diagnostic disclosure shows.

## Error Handling

| Failure | Rendering |
|---|---|
| Non-envelope HTTP failure — 422 `question-too-long`, 403 host/origin rejection | Broken state naming what was rejected; never a refusal (9.15). The 1000-character limit is enforced client-side first, with the limit and the typed length shown while the question stays editable |
| Stream drops mid-answer with no `outcome` | Partial text retained and marked incomplete, retry offered (9.14) |
| `GET /sources` fails | Picker reports the engine unreachable and submission is blocked; distinct from `corpus-empty`, which is the engine answering that nothing is ingested (9.13) |
| Passage fetch fails | 5.11 — citation intact, body unavailable |
| serve-document 404 | Citation degrades to its string form with its location and marks intact; never a broken action (5.11) |
| Unrecognised `outcome` | Broken state carrying `detail` (9.4) |
| Unknown turn-stream version | Turn refused before the body is read; broken state naming both versions (9.19). Carries no outcome |

Diagnostics (9.3) sit behind an explicit disclosure on every error state — and on any turn carrying
`framing: unparsed`, which is a degraded rendering whether or not it failed — and render **only** the
engine's `detail`, `framing` and `timings` plus the client's per-turn marks. Nothing here parses
`detail`: CONTRACTS §4 declares it unparsed, and every fact this surface acts on (`reason`,
`retry_after`, `required_manual`) is its own field. No request body is ever echoed, which is what
keeps 9.17 structural rather than a filtering rule — the credential is never in a value the error
renderer can reach.

Raw exception text and payloads never appear as the primary message (9.1); every error state offers
at least one action (9.2).

## Requirements defects to reconcile

Five of the six are **closed** by `DECISIONS.md` Decision 11, which amended CONTRACTS and then
reconciled this spec against it. They are kept with what closed them rather than deleted: items 1, 2
and 3 were each found independently from the `api/answer-engine` side as well, and that is the
evidence the amendment was owed.

1. **CLOSED — open-at-source could not be done with the eight operations.** The old assumption that
   "the operating system can open a local PDF at a given page" was false, and it — not 5.5 — was the
   defect. Closed by CONTRACTS §3a and **one** new engine operation, serve-document: the
   vendor-manual branch opens the engine-served PDF in a new tab at `#page=N` and nothing else. The
   authored branch needed **no** operation at all — `GET /passages/{passage_id}` already returns the
   entry's text and 5.6 already reveals it in place — so the proposed
   `POST /sources/{source_id}/open` is dropped, along with its process launcher on a loopback
   endpoint. The entry's file and line arrive as `entry_location` (5.19). The Assumptions section now
   names the engine's operation **list** rather than a count, so the next route is an amendment
   rather than a defect.
2. **CLOSED — a ranked cause list had no representation.** Closed by CONTRACTS §4c `Cause` and the
   `ranked-causes` outcome, rendered by an amended 6.6: array order, explicit `rank`, per-cause
   `check`, and `cites[]`/`fix_cites[]` resolved through the turn's citation map. The interim
   position — rendering it from `narrowing` candidates, which could not carry the rank — is
   withdrawn, and the two shapes are now held apart by affordance as well as by outcome.
3. **CLOSED — provider error detail had no envelope home.** Closed by `reason` (from the closed §6a
   vocabulary), `retry_after`, `detail` and `framing` as CONTRACTS §4 fields, and by amendments to
   9.3, 9.5, 9.8, 9.9 and 9.10 keying on them. The `reason` this design had assumed is now governed,
   and it is a machine sub-code rather than the human wording it was being used as: the wording is
   `detail`, which no criterion may parse.
4. **CLOSED — 8.8's closing sentence was stale.** CONTRACTS §7 already records the band. Nothing in
   CONTRACTS needed changing; the sentence is the thing to remove from 8.8, and it is the one item
   here that was never a contract defect.
5. **OPEN — the static mount is missing from the engine's HTTP surface.** Serving `web/build` at `/`
   is what makes the page same-origin, which is what lets the engine keep its strict `Origin` guard.
   *(Now listed in that design's route table, but no engine criterion requires it; 9.4 names
   operations and the mount is not one. It is the smallest remaining item on this seam.)*
6. **CLOSED — `scope_dropped` was produced with no criterion requiring it to be rendered.** Closed by
   CONTRACTS §4b, which governs the event set and requires every event to discharge into a named
   criterion, and by the new 3.11. §4b also states in one sentence why 3.8 was never in conflict with
   it: 3.8 prunes this surface's **own store at load time**, before any turn exists, while
   `scope_dropped` reports a prune the **engine** performed on the turn just asked.

A seventh item remains a consequence rather than a defect, and the amendment has made it *fixable*
without fixing it: 4.9 re-asks an uncovered part "widening scope to any sources the engine names for
it", but `uncovered_parts[]` entries are strings and `suggested_sources[]` is an envelope-level array
with no association to the part that motivated a suggestion. The re-ask therefore still widens to
every suggested source. Closing it means an association on the record — an optional `for_part` member,
or a nested shape — and no criterion asks for one, so it was left out rather than designed on
speculation.

## Testing Strategy

`vitest` + `@testing-library/svelte` for behaviour, Playwright for anything needing a real browser,
`axe-core` for the accessibility floor. The engine is stubbed by a fake SSE server so no test needs a
provider, a corpus, or a key.

### Unit and component

| Test | Asserts |
|---|---|
| SSE parser | Frames split across chunk boundaries reassemble; a multi-byte character split across chunks does not become `U+FFFD`; an unknown event name is ignored; end-of-stream without `done` yields `incomplete` rather than a settled turn; an unknown `dawmans/turn-stream/*` header refuses the turn before the body is read (9.19) |
| Event coverage | **One rendering path per event in CONTRACTS §4b** — the test that enforces §4b's "render everything you do know" clause, which the wire cannot. A governed event with no path fails here, not in review |
| Reducer totality | Every member of the CONTRACTS §6 union — all 17 — maps to a renderer; an outcome outside it renders broken with `detail` (9.4) |
| Block typing | A block's type is fixed by its first line and never revised across any chunk split; the `!conflict ` prefix is disambiguated within 10 characters; an unknown first line renders its text as a paragraph rather than nothing (4.4); a `!conflict` with other than two readings is not re-typed |
| Ranked causes | Causes render in array order with `rank` shown, never as armed digit controls; each cause's `cites[]` and `fix_cites[]` resolve through the turn's citation map; an empty `fix_cites[]` renders the `unbacked` mark (6.6) |
| Dropped scope | A turn carrying `scope_dropped[]` names the dropped sources with that turn (3.11), while a stale stored id at load time drops silently (3.8) — the two paths asserted together, since the pair is what the criteria disagree about on a careless reading |
| Marker stability | A citation's printed integer is assigned at first appearance and does not change when its `citation` event arrives late |
| Absent fields | A pageless citation renders the symptom title in the location slot with page and section absent — never `0`, never empty (5.15) |
| Inline obligations | `kind`, `doc_version`, `hardware_applicability`, `unbacked`, `has_figures` each render on the citation with no disclosure in the path (5.2, 5.3, 5.4, 5.14, 5.16) |
| Scope decay | Present `sessionStorage` marker ⇒ no release; absent marker with a narrowed scope ⇒ release with reinstate; narrowed-but-equal-to-all ⇒ no notice (3.6) |
| Scope pruning | A stored id the engine no longer reports is dropped silently on load (3.8) and named on `unknown-source-id` (9.11) |
| Arming | Digits 1–4 activate candidates while armed and type normally when not; every other printable character always types (1.11) |
| Cancellation split | User-cancelled renders ready-with-question-preserved (8.6); engine-`cancelled` renders abandoned and does not disturb the replacing turn (9.16) |
| Credential containment | After a `set-credential` round trip, the key value appears nowhere in the DOM, the title, the URL, or the history store (10.6, 10.9, 10.17) |
| Contrast floors | Every token pair meets 11.3 and 11.4; background luminance is inside 11.5's band — computed from the tokens, not observed |

### Browser

| Test | Asserts |
|---|---|
| No reflow | Over a scripted stream, the `top` of every already-painted line is unchanged at every subsequent frame (4.2) |
| Keyboard-only loop | Ask, narrow, cancel, widen scope, expand a citation and open it, using no pointer at all (1.13, 13.1) |
| Open at source | A `vendor-manual` citation activates a link to the serve-document route whose fragment is exactly `#page=N`, with nothing appended; an `authored-triage` citation reveals the entry in place with `entry_location` copyable, and no navigation leaves the tab (5.5, 5.19) |
| Focus return | Each region dismissed with `Escape` returns focus to its opener; no region traps focus (13.3) |
| Reading position | Expanding and collapsing a citation mid-stream leaves it at the same viewport offset (5.8) |
| Greyscale | A greyscale screenshot preserves every distinction 11.6 lists |
| 200% text | No horizontal scrolling and no clipped control at 200% browser text size (13.7) |
| Reduced motion | With `prefers-reduced-motion`, the working indicator is a counter and a static shape, and working/finished/broken remain distinguishable (13.6, 8.4) |
| Announcements | A full turn announces its state transitions once each and never a streamed fragment (13.5) |
| Chrome ratio | At rest on 1280×800 with the picker collapsed, question plus answer occupy ≥70% of viewport height (11.8) |

### Observed, not asserted

2.14, 4.10, 4.11, 4.12, 5.17, 8.11, 11.1, 11.2 and 11.7 are stand-back and measure tests run against
real output, per `PROCESS.md` §5. Each is recorded in `decision_log.md` when its band is hit,
together with any conscious near-enough trade-off. 8.8 and 8.10 need a real provider and are
measured against both provider classes, not stubs.
