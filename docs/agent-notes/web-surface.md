# Web surface (`web/`)

SvelteKit SPA for `ui/ask-and-source-picker`, built to static assets in `web/build` and
(eventually) mounted at `/` by the answer-engine process so the page shares the engine's origin.

## Setup facts

- Scaffolded with `sv create` (minimal, TypeScript). The new CLI puts the **kit config inline in
  `vite.config.ts`** via the `sveltekit({...})` plugin options — there is no `svelte.config.js`.
  Runes mode is forced project-wide through `compilerOptions.runes`.
- `@sveltejs/adapter-static` with `ssr = false` / `prerender = true` in `src/routes/+layout.ts`.
  Output directory is the adapter default, `build/`.
- Dev proxy (`/turn`, `/passages`, `/sources`, `/provider` → `$ENGINE_ORIGIN`, default
  `http://127.0.0.1:8000`) **must rewrite `Origin` in a `proxyReq` hook** — `changeOrigin: true`
  only rewrites `Host`, and the engine's rebinding guard 403s any Origin outside its own loopback
  set. Verified working by curling through `vite dev` to a stub server. Don't "simplify" this away.
- Makefile: `make web-install / web-build / web-test`, and `make dev` runs `dev-web` + `dev-engine`
  with `-j2` (`dev-engine` is a placeholder echo until the engine exists).

## Contract types

`src/lib/engine/records.ts` is CONTRACTS §1–§4e, §6 and §6a as types — the only place they are
written down in this surface. `SourceRecord` and `Citation` are discriminated unions on `kind`, so
per-kind "not applicable" fields are structurally absent rather than optional-everywhere.
`TURN_STREAM_VERSION` lives here too. Types only, no behaviour.

## Design tokens and their test

- `src/lib/tokens.css` holds every colour and size as custom properties; imported once in
  `+layout.svelte`. Components must not declare colours of their own (Decision 6 — the contrast
  floors are only checkable because the token set is enumerable).
- `src/lib/tokens.test.ts` computes WCAG contrast/luminance from the declared values: body ≥7:1,
  other text ≥4.5:1 (incl. hover/active/disabled variants, 13.8), indicators/focus ring ≥3:1,
  background luminance in [0.03, 0.08] and body text ≤0.9 luminance (the recorded 11.3-vs-11.5
  resolution as two enforced bounds).
- Gotcha: **vitest stubs CSS imports even with `?raw`** (empty string), and `import.meta.url` in
  the jsdom environment is not a `file:` URL — the test therefore reads `tokens.css` from disk via
  `process.cwd()`, which vitest sets to `web/`.
- Background is a mid-dark grey (`#3c3c40`, L≈0.046) rather than near-black — deliberate: it sits
  at the lighter end of 11.5's band so body text (`#e4e4e4`) clears 8:1 without going maximal white.

## Engine layer (`src/lib/engine/`)

- `client.ts` — the nine api/answer-engine operations as stateless typed wrappers, all relative
  routes, **no retries**. Non-envelope failures (422 question-too-long, 403 origin) throw
  `EngineRejection` carrying the engine's `rejected` name — an Error, deliberately not an outcome.
  `submitQuestion` returns the `Response` **unread**; `serveDocumentHref` builds
  `/sources/<id>/document#page=N` with slashes in ids kept verbatim (they are path structure).
- `sse.ts` — `readFrames` (incremental TextDecoder, dispatch on blank line, data-less events never
  dispatched) and `turnEvents` (version check first, yields frames, **returns** `{complete}` — the
  generator's return value, read by iterating manually, is how end-without-`done` is signalled).
  **`TURN_STREAM_HEADER = 'dawmans-turn-stream'`**: CONTRACTS §4b fixes the token but no spec names
  the header — this constant is the surface's choice and the engine implementation must match it.
- `blocks.ts` — the append-only block parser. `PREFIX_LIMIT` is coupled to the longest sigil
  (`!conflict `, 10 chars); a longer sigil must move it. Unknown sigils drop their wrapper only when
  the token ends within the limit, else the text stays verbatim. Marker/key candidates are buffered
  (never painted raw); a disproved candidate re-scans from its second character so `[[[p:…` keeps
  its marker. Marker numbering is injected (`MarkerAssign`) — the Turn owns first-appearance order.
- `turn.svelte.ts` — the reducer. Two compile-time totality guards: `RENDERER_FOR_OUTCOME` is
  `Record<Outcome, TurnRenderer>` (new outcome fails typecheck) and the handler map is a mapped type
  over `TurnEvent` (new event without a handler fails typecheck); turn.test.ts additionally asserts
  one observable effect per event. Handlers live in a `static readonly handlers` so they can reach
  `#`-private members. State is `$state.raw` replaced-by-append everywhere (Map included — the
  svelte-autofixer suggests SvelteMap; not taken, reassignment is the design's reactivity model).

## State stores (`src/lib/state/`)

Every store is a **class instance with `$state` fields** exporting a singleton (a reassigned
module-level `$state` is not reactive across the module boundary). Persistence keys:
`dawmans.scope`, `dawmans.session` (marker only), `dawmans.history`.

- `scope.svelte.ts` — selection, persistence, decay (§3, Decision 4). The stored record carries a
  `known[]` field (the available-source list at last persist) **in addition to** `seen[]`: the 2.4
  admission rule ("a new source joins only where the stored scope was all available") cannot read
  `seen[]`, because `seen` updates only on submit — a narrowing made before any question would read
  as "everything new" and be silently widened on reload, breaching 3.5. Session boundary is
  `sessionStorage` **presence**, not a clock; the 8-hour clause reads `lastQuestionAt`.
- `sources.svelte.ts` — `GET /sources` plus both gap reports. Four states: `loading` / `ready` /
  `engine-unreachable` (fetch failed or non-OK — never rendered as an empty picker) /
  `corpus-empty` (the engine answering that nothing is ingested, 9.13). `blocksSubmission` is
  `state !== 'ready'`. The store does **not** call `scope.load()` — the page wires
  `scope.load(sources.ids)` after a successful load (kept separate so each store tests alone).
- `history.svelte.ts` — persisted exchanges, newest first, trimmed to 50 on `record()`. Lazy-read
  gotcha: the `entries` getter must not assign a `$state` field (a first read from a template would
  throw `state_unsafe_mutation`), so the cache is a **plain field** and a `$state` version counter —
  bumped only in `record()`, which runs in stream handlers — provides the reactivity. Quota
  fallback drops the oldest entry and retries until the write succeeds or the list is empty; it
  never throws. Retention: user-cancelled, engine-`cancelled` and error/broken/empty-scope turns
  are skipped; a `failed`/`incomplete` turn is retained with `incomplete: true` (9.14, 12.7).
  `record(turn, thread?)` also stores the client-minted conversation id as `entry.thread` (6.7) —
  the Phase 8 history panel groups on it so a narrowing exchange is never a standalone unanswered
  question.

- `thread.svelte.ts` — the conversation on screen. `draft` (the composed question) lives here, not
  in the input component, so the router's manual insert, ThreadView's re-edit and stop's
  question-restore all reach one text. Guards in `submit()`: whitespace no-op, `scope.canSubmit`,
  1000-char limit; the `Turn` is constructed synchronously (8.7) before the fetch. **Conversation
  ids are minted client-side** (Decision 8): first turn of a thread sends `conversation_id: null`,
  then one `crypto.randomUUID()` for every follow-up; `clear()` resets to null. The engine will
  need to treat any non-null id as "continue the current conversation". Error paths in `#run`:
  user-cancel synthesizes `outcome: cancelled` + `done` through `applyEvent` (the client knows who
  cancelled, 8.6 vs 9.16); `EngineRejection`/`UnknownStreamVersionError` are kept in a WeakMap
  (`failureOf(turn)`) with no outcome for Phase 7's broken renderer; any other mid-stream throw
  becomes `incomplete`. `onSettled` is a settable callback AskSurface uses for 1.6's focus return.

## Keyboard router (`src/lib/keys.ts`)

Plain TS (no runes) — a `KeyRouter` class with three registries: the question-input adapter
(`{element, focus, insert}`), at most one armed digit set (`arm()` **throws** on a second
registration; Decision 5's invariant is enforced, not assumed), and an Escape stack of overlay
regions. Decision-table order as designed, with **one recorded deviation**: an armed digit fires
even when the target is the question input, because 1.1 keeps focus resting there and arming only
exists while the input is empty — a literal text-entry pass-through would defeat 1.10/6.3's
one-keypress rule. All other text-entry targets pass through entirely (including Escape).
Components arm/disarm via `$effect` cleanup; AskSurface wires `<svelte:window onkeydown onfocus>`.

## Components (`src/lib/components/`)

- `AskSurface.svelte` — textarea bound to `thread.draft`; Enter submits, Shift+Enter passes
  through; shortcut row (`SYMPTOM_SHORTCUTS`, module export) renders and arms only while
  `draft === '' && !busy && !awaitingNarrowing` — the gating that keeps the one-armed-set
  invariant when Phase 6's narrowing candidates arm. Zero-scope and over-limit notices render from
  store state (not submit attempts). Stop restores the question into the draft.
- `ThreadView.svelte` — the thread shell. The question is a button that re-edits (sets
  `thread.draft`); state line is text (`working…`/`stopped`/`abandoned`/`incomplete`/`broken`/
  `finished`). Renderer `'answer'` (and `null`, pre-outcome) goes to `AnswerView`; `'narrowing'`,
  `'ranked-causes'` and `'coverage-failure'` go to their Phase 6 components below (ThreadView
  passes optional `router` and `sources` props down for them); error/broken/empty-scope/cancelled
  keep the plain-text placeholder until Phase 7.
- `NarrowingView.svelte` — the §6 narrowing renderer. Candidates are numbered buttons in engine
  order; the digits arm through `router.arm()` **only while the turn is the thread's last settled
  turn** (`thread.awaitingNarrowing && turns.at(-1) === turn`) — the counterpart to AskSurface's
  `!awaitingNarrowing` gate, which is what keeps the router's one-armed-set invariant from
  throwing. Selection is just `thread.submit(candidate)` — a follow-up in the same conversation
  against the unchanged scope; the free-text-reply path (6.5) is the router's printable capture,
  nothing here. The question paints from the `narrowing` event, never gated on `done` (6.8).
- `RankedCausesView.svelte` — the `ranked-causes` renderer. Causes are plain list items (no
  buttons, no `<kbd>` — the affordance split from narrowing is deliberate and tested); each shows
  rank, statement, `Check:` line, and marker superscripts for `cites[]`/`fix_cites[]`; empty
  `fix_cites[]` renders the "no manual behind this" mark (5.16). `direct_answer` (the rank-1
  check) paints first; the shared CitationList renders below.
- `citation-order.ts` — `numberedCitations(turn)`: markers in first-appearance order, then
  citations never referenced by a prose marker numbered on. Extracted from CitationList so
  RankedCausesView's per-cause markers and the list entries can never disagree on a number.
- `CoverageFailureView.svelte` — one renderer for `refused-not-covered` / `out-of-domain` /
  `no-manual-for-device` with the §7 action table: add-suggested-and-re-ask (7.4, via
  `scope.toggle` + `thread.submit(turn.question)`), widen-all-and-re-ask only on
  `refused-not-covered` with no suggestion and out-of-scope sources (7.5; `scope.selectAll()`, so
  it persists and decays like any scope change, 7.9), the copyable `required_manual` filename with
  `placeholders[]` named from the array (7.7 — never split from the filename; absent ⇒ the
  `manuals/` naming convention and the device, nothing synthesised), and an always-present "Edit
  the question" fall-through so no state dead-ends (7.8, 9.2). Takes a `SourcesLike`
  (`Pick<SourcesStore, 'ids' | 'displayName'>`) so tests inject a plain object; `allInScope` and
  7.3's names are measured against `turn.scopeAtAsk`, not the scope now.
- `AnswerView.svelte` — the §4 answer renderer: `scope_dropped` notice, `direct_answer` first,
  blocks in arrival order (`.heading/.step/.bullet/.paragraph/.caveat/.conflict>.reading`,
  backtick spans as `<kbd>`, markers as `<sup class="marker">`), then `.uncovered` with a
  per-part re-ask button (widens scope to `suggested_sources` via `scope.toggle`, then
  `thread.submit(part)`), `.contributing` (names via the turn's citation map), and the
  CitationList. Props `thread`/`scope`/`passages` are injectable, defaulting to the singletons.
- `CitationList.svelte` / `CitationEntry.svelte` — one entry per marker integer in
  first-appearance order; a citation resolved only by `causes[]` (no prose marker) appends after,
  numbered on. All five §3 inline obligations are elements on the entry (`.doc-version`, `.kind`
  "your own note", `.applicability`, `.figures`, `.unbacked`), the location slot renders only what
  exists (symptom title for authored, 5.15), `entry_location` + copy button sit outside the slot
  (5.19). `uncited` (settled ∧ empty map) and `ungrounded` notices live on the list.
- Expansion (CitationEntry): prefetch **on the expand button's focus**, never hover; expanded
  passage is a `.passage` blockquote with `.degraded-mark` distinct from `.passage-unavailable`;
  the working indicator appears only after a 300 ms timeout while status is `loading` (timer set
  in an `$effect`, the flag written only in the untracked timer callback). Collapse restores the
  **entry's own rect top** via `window.scrollBy(0, delta)` after `tick()` — never `scrollY`.
  openAtSource: vendor = plain `<a target="_blank" rel="noopener">` to `serveDocumentHref`
  (`#page=N` exactly); authored = the expansion + copyable `entry_location`
  (`navigator.clipboard.writeText`). No third branch, no `file://`.

## Passage cache (`src/lib/state/passages.svelte.ts`)

`PassageStore` — session `Map` of `loading/ready/failed` per `passage_id`, injectable fetcher
(defaults to `client.fetchPassage`). `prefetch()` no-ops on loading/ready and **retries on
failed**, so a citation activated after an outage recovers; `ready` is never refetched (a passage
cannot change without re-ingestion, which changes its id).

## Gotcha: the reducer must clone the open block on snapshot

`BlockParser` streams into its **last** block by mutating it in place; `Turn.#snapshotBlocks`
copies the outer array only. Under `$state.raw` a keyed `{#each}` compares items referentially, so
a delta extending an already-painted paragraph never repainted. Fix (in `turn.svelte.ts`): the
snapshot `structuredClone`s the last block (the only one still open); earlier blocks are closed
and keep their references. Don't "simplify" this back to `[...parser.blocks]`.

## Testing stack

vitest (jsdom) + @testing-library/svelte for units/components; @playwright/test + axe-core
installed but not yet configured (no browser tests exist yet — config comes with the first one).

- **Node ≥ 22 shadows Web Storage in vitest**: Node's experimental `localStorage`/`sessionStorage`
  globals (lazy getters, undefined without `--localstorage-file`) win over jsdom's because vitest
  skips keys the Node global already owns — and vitest's `window` IS `globalThis`, so no jsdom
  Storage object is reachable at all, whatever the jsdom URL. `web/vitest-setup.ts` installs an
  in-memory `Storage` over both globals; don't remove it on the theory that jsdom provides one.
- The SSE tests assert "header checked before body read" via `response.bodyUsed`; a `pull()`-spy
  stream cannot work because the stream machinery calls `pull` eagerly to fill its queue.
- **Component tests need `resolve.conditions: ['browser']` under vitest** (gated on
  `process.env.VITEST` in vite.config.ts) — without it vitest resolves Svelte's *server* entry and
  `render()` dies with `lifecycle_function_unavailable: mount(...) is not available on the server`.
- `src/lib/testing/turn-channel.ts` is the shared stub engine: `sseChannel()` (a controllable
  SSE `Response` carrying the version header, with an `abort()` that errors the stream the way a
  real aborted fetch does) and `fakeEngine()` (records `TurnRequest`s, one channel per turn,
  wires the abort signal). Thread and component tests both inject `fakeEngine().submit` into
  `new ThreadStore({...})`.
