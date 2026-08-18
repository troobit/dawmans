# Web surface (`web/`)

SvelteKit SPA for `ui/ask-and-source-picker`, built to static assets in `web/build` and mounted at
`/` by the answer-engine process so the page shares the engine's origin. The mount is live:
`dawmans serve` defaults `--static-dir` to `<root>/web/build` when that directory exists.

## Setup facts

- Scaffolded with `sv create` (minimal, TypeScript). The new CLI puts the **kit config inline in
  `vite.config.ts`** via the `sveltekit({...})` plugin options — there is no `svelte.config.js`.
  Runes mode is forced project-wide through `compilerOptions.runes`.
- `@sveltejs/adapter-static` with `ssr = false` / `prerender = true` in `src/routes/+layout.ts`.
  Output directory is the adapter default, `build/`.
- Dev proxy (`/turn`, `/passages`, `/sources`, `/provider` → `$ENGINE_ORIGIN`, default
  `http://127.0.0.1:8722` — `cli.DEFAULT_PORT`, and the guard checks Origin against the port it
  bound, so a proxy pointed elsewhere is 403 rather than merely unrouted) **must rewrite `Origin`
  in a `proxyReq` hook** — `changeOrigin: true` only rewrites `Host`, and the engine's rebinding
  guard 403s any Origin outside its own loopback set. Verified working by curling through
  `vite dev` to a stub server. Don't "simplify" this away.
- Makefile: `make web-install / web-build / web-test / web-e2e / web-lint`, and `make dev` runs
  `dev-web` + `dev-engine` with `-j2`. `dev-engine` is `uv run dawmans serve` — the placeholder
  echo is gone.

## Contract types

`src/lib/engine/records.ts` is CONTRACTS §1–§4e, §6 and §6a as types — the only place they are
written down in this surface. `SourceRecord` and `Citation` are discriminated unions on `kind`, so
per-kind "not applicable" fields are structurally absent rather than optional-everywhere.
`TURN_STREAM_VERSION` lives here too. Types only, no behaviour.

## Design tokens and their test

- `src/lib/tokens.css` holds every colour and size as custom properties; imported once in
  `+layout.svelte`. Components must not declare colours of their own (Decision 6 — the contrast
  floors are only checkable because the token set is enumerable). It also sets the CSS
  `color-scheme` to dark on `:root` <!-- spelling-ignore -->
  — without it the browser paints native checkbox fills and input interiors light.
- **There is no headroom for a lighter surface token.** `--colour-surface` (#46464b) clears 11.3's
  7:1 body floor by 0.37; anything lighter fails it. A "raised/selected" surface must therefore be
  carried by border, shadow and a *darker* recessed variant (`--colour-bg`), not by a new lighter
  colour — which is what the picker tiles do.
- Spacing (`--space-*`), tile sizes (`--tile-*`), radii and the two shadow tokens live here too.
  The token test's regex only captures `#hex` values, so non-colour tokens are invisible to it; a
  new **hex** token is captured but asserted only if it is added to `textFloors` / `backgrounds`.
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
  the header — this constant was the surface's choice, and the engine now matches it
  (`answer/http/app.py` sets `dawmans-turn-stream: TURN_STREAM_VERSION` on the turn response). The
  name is written down twice with no shared source; changing either side alone breaks every turn
  with a version-mismatch broken state.
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
`dawmans.scope`, `dawmans.session` (marker only), `dawmans.history`, `dawmans.disclosure-ack`.

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
  The two gap-report fields are `owned_but_undocumented` and `documented_but_unconfirmed` — the
  engine's names, relayed verbatim from the corpus's `gaps.json`. This side shipped the abbreviated
  forms for a while, so both reports arrived `undefined` in the real app while every test passed:
  every fixture here (`fake-server.ts`, `e2e/stub-engine.mjs`, the per-test `payload()` helpers) was
  written from this side's own type. See `specs/bugfixes/gap-reports-field-names/report.md`. **Any
  field name in `client.ts` that no test compares against a payload written in the engine's own
  terms is unverified** — `answer/http/app.py` is the producer and
  `tests/answer/test_http_sources.py` pins it.
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

- `provider.svelte.ts` — provider status over the five provider operations (§10). Renders **only**
  `GET /provider` (10.7); the one legitimately local piece of state is the shared-backend
  disclosure acknowledgement, stored under `dawmans.disclosure-ack` as the backend identity string
  `` `${kind}:${model ?? ''}` `` — equality against the *engine-reported* identity is what makes
  changing backend re-arm the disclosure (10.4). `blocksFirstTurn` is
  `kind === 'shared-backend' && !acknowledged`; the page wires it (with `sources.blocksSubmission`)
  into `ThreadStore.submitGate`. How the ack reaches the *engine* is an open seam: the api design says
  `PUT /provider` to shared-backend "returns `requires_disclosure_ack: true` and records nothing",
  and no ack operation exists among the five, so the engine side will need an amendment when built.

- `perf.svelte.ts` — per-turn marks (8.7–8.9) and the per-provider-class "taking longer" thresholds
  (`SLOW_THRESHOLD_MS`: hosted 3 s, local 5 s, 8.10). `markFirstByte` is called by the reducer's
  `direct_answer`/`body_delta` handlers (first content event only — `outcome` is not content);
  `scheduleFirstPaint` stamps in a rAF and guards double-scheduling with a `WeakSet`;
  `measures()` returns `{}` unless **both** firstByte and firstPaint exist (absent is absent).
  `Turn.marks` is a deep `$state` object *(the one non-raw state on Turn)* so the working
  indicator can leave the moment `firstByte` lands and the disclosure never shows stale marks.

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

- `pictograms.ts` / `Pictogram.svelte` — the pictogram set (Decision 10). Path data in a 24-unit
  box keyed by name, plus `pictogramFor(record)` (a keyword table over vendor/product words, book
  as fallback) and `SHORTCUT_PICTOGRAMS` (keyed on the shortcut text). Every pictogram renders
  `aria-hidden` with `stroke: currentColor` — it is never an accessible name, never a colour of its
  own, and never the only channel for a state.
- `AskSurface.svelte` — textarea bound to `thread.draft`; Enter submits, Shift+Enter passes
  through; shortcut row (`SYMPTOM_SHORTCUTS`, module export) renders and arms only while
  `draft === '' && !busy && !awaitingNarrowing` — the gating that keeps the one-armed-set
  invariant when Phase 6's narrowing candidates arm. Zero-scope and over-limit notices render from
  store state (not submit attempts). Stop restores the question into the draft. Each shortcut is a
  tile: `<kbd>` digit, pictogram, label. **DOM order is digit → pictogram → label** because
  `ask.test.ts` matches the accessible name against `/${index + 1}.*${label}/`, and the tile is a
  *single row* because the shortcuts share the viewport with the answer that 11.8 measures — a
  column layout cost 50 px and put 11.8 under its band.
- `ThreadView.svelte` — the thread shell. The question is a button that re-edits (sets
  `thread.draft`); the state line is text **plus a static glyph** (`.state-shape`: ● working,
  ✓ finished, ✕ broken, ◗ incomplete, ■ stopped, □ abandoned) — 8.4's two channels; the glyph is
  deliberately unanimated (11.9 allows motion only on the working indicator). Routing: the error
  family first (`error`/`broken`/`empty-scope`, **plus `state === 'failed' && renderer === null`**
  — a rejection/version-mismatch turn, whose `failureOf(turn)` is passed to ErrorView), then
  `'answer'`/`null`/`'cancelled'` → AnswerView (cancelled retains what arrived), then the Phase 6
  renderers. Per-turn footer: `.incomplete-note` + Retry gated on `turn.incomplete &&
  !isErrorFamily(turn)` (the getter is true for *any* failed turn, including rejections — don't
  widen the gate), `.abandoned-note` on engine-cancelled-not-user (9.16), and
  `DiagnosticsDisclosure` when failed / error / broken / `framing === 'unparsed'` (9.3).
  Below the turns: `WorkingIndicator` then the one `aria-live="polite"` `.announcer` (13.5) —
  announced-once bookkeeping is a `WeakMap<Turn, {streaming, terminal}>` written from an
  `$effect`; a narrowing announcement includes the candidates and that digits select them.
  New props: `providerClass`, `reducedMotion`, `providerName`, `onconfigure` (wired by the Phase 9
  page; provider knowledge itself is the Phase 8 store).
- `WorkingIndicator.svelte` — shown only while the active turn has no `firstByte` (8.2 is about
  the wait for *first content*; once text arrives, the text is the liveness). Elapsed time is a
  1 s `setInterval` incrementing plain `$state` — deliberately not `performance.now()`, so fake
  timers drive it deterministically. Default: pulsing shape (`[data-animated="true"]`, the only
  animated element on the surface); `reducedMotion` (default from `matchMedia`, prop-injectable):
  static shape + `.elapsed` seconds counter, which sits **outside** the announcer region
  (Decision 7). Past `SLOW_THRESHOLD_MS[providerClass]`: "Taking longer than usual." + Cancel
  (stop + restore question to an empty draft, 8.6).
- `ErrorView.svelte` — the §9 outcome table. Branch order: `no-sources-selected` → `.empty-scope`
  (3.2 wording + select-all, **no `.error` class** — 9.12 forbids reading as a failure); then
  `failure !== undefined || renderer === 'broken'` → `.error.broken` (version mismatch names both
  versions from the error's fields, `EngineRejection` names `rejected`, unknown outcome names
  neither and leaves `detail` to the disclosure); else per-outcome `.error` states. Wording keys
  on `outcome` + `reason` sub-code only, never `detail` (9.5, 9.10: authentication-failed gets
  configuration **instead of** retry). The 9.8 countdown mirrors the indicator's interval pattern
  (`Math.ceil(retry_after) − waited`, retry disabled while > 0; absent `retry_after` → honest "did
  not say how long", retry enabled). 9.11 drops rejected ids (from `envelope.scope_dropped` — the
  only addressable channel that names them) via an idempotent `$effect` toggling the scope store,
  then re-ask = `thread.submit(turn.question)` against the pruned snapshot. `corpus-empty` offers
  no control (no in-app action exists; names `manuals/` + ingestion).
- `DiagnosticsDisclosure.svelte` — a `<details class="diagnostics">` rendering exactly `detail`,
  `framing`, `timings` (entries verbatim) and the client marks/measures — nothing else, nothing
  parsed from `detail`, no request echo (that structure is what makes 9.17 hold).
- `NarrowingView.svelte` — the §6 narrowing renderer. Candidates are numbered buttons in engine
  order; the digits arm through `router.arm()` **only while the turn is the thread's last settled
  turn** (`thread.awaitingNarrowing && turns.at(-1) === turn`) — the counterpart to AskSurface's
  `!awaitingNarrowing` gate, which is what keeps the router's one-armed-set invariant from
  throwing. A candidate is a `{label, value}` record, **not a string**: the control reads
  `candidate.label` (the cause's `check`, an observable to look at) and selection is
  `thread.submit(candidate.value)` (the cause `statement`) — a follow-up in the same conversation
  against the unchanged scope. The two are assigned by `api/answer-engine` design §Narrowing step 3;
  this side typed them `string[]` for a while, so every control read `[object Object]` and selection
  threw inside `ThreadStore.submit`, with all six fixtures agreeing because each was written from
  this side's own type (`specs/bugfixes/narrowing-candidate-shape/report.md`). The free-text-reply
  path (6.5) is the router's printable capture, nothing here. The question paints from the
  `narrowing` event, never gated on `done` (6.8).
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

- `SourcePicker.svelte` (Decision 10 reshaped its presentation; every rule below still holds) — the
  one expand/collapse control is the indicator line itself
  (`button[aria-expanded]`, `data-scope="all|narrowed|none"`): "All N sources in scope" (2.7),
  names at ≤3 in scope (2.6/3.3), else "n of m sources" (2.5), with a `.scope-glyph` (● / ◐ / ○)
  as the non-colour channel beside the wording (3.10/11.6). Expanded: per-source checkbox rows
  with a filled/hollow `.scope-marker` **plus the word** in/out of scope (2.14), the kind stated
  on every entry ("your own notes (authored)" vs "manual", 2.12), the 2.10 assumed-revision mark
  (only when `hardware_applicability.device` exists — the authored store is assumed-with-no-device
  and gets no mark), and the `low_text` "sparse text layer" mark. All/none buttons (2.8); the
  substring filter renders only at ≥12 sources (2.13); `.gaps` (owned-but-undocumented) renders
  apart with no inputs and is omitted entirely — heading included — when the report is empty
  (2.9). While expanded it registers on the router's Escape stack with the indicator as opener.
  The 2.4 "new" mark is **not** rendered yet — the store side (`seen`/`known`) exists; marking is
  open for a later pass.
  Presentation gotchas, all of them load-bearing for a suite:
  - **Collapsed renders no checkbox at all** (`picker.test.ts` asserts `queryAllByRole('checkbox')`
    is empty at rest), so the collapsed bar cannot become the toggle surface.
  - **The indicator must be the first `button[aria-expanded]` in the document** — both the unit
    helper and the e2e locators take the first one, and the page's History/Provider buttons carry
    the attribute too. The header is a *grid* whose areas place the picker on the title's row at
    ≥ 60rem and on its own row below that, precisely so DOM order can stay picker-before-nav.
  - **The bar is `flex-wrap: nowrap` with an ellipsised `.indicator-text`.** A second flex line
    costs 26 px and puts 11.8 under target; the trade-off is Decision 10's recorded negative.
  - **`.body` is `position: absolute`** under the bar. That is what keeps 11.8 a collapsed-state
    measurement while the tiles are large. It needs `.picker { position: relative }` — do not move
    the positioning context to the page.
  - `.scope-marker` must exist once per source, in source order, with no earlier element of that
    class anywhere (the greyscale e2e test reads `.first()` / `.nth(1)`).
  - The checkbox stays a **visible** native control: Playwright's `uncheck()` in the greyscale test
    needs a real, hittable box. It is absolutely positioned in the tile's corner, not hidden.
- `ProviderConfig.svelte` — kind-first (10.1): three radios; the credential input exists only in
  the keyed-hosted branch (masked `type="password"` by default with a hold-to-reveal button,
  10.5); local is an "Endpoint or model" text input and Save is gated on it being non-empty
  (10.3). Save = `provider.choose(kind, model?)` then `onclose?.()` — **except** shared-backend
  with the disclosure unacknowledged, which keeps the surface open showing the disclosure text and
  its Acknowledge button; the text stays rendered after acknowledgement too (10.4). The key state
  is cleared after `saveCredential` so the engine's masked tail is the only representation left
  anywhere (10.6); the component never touches thread or scope, which is what keeps 10.2/10.11
  free. `.status` renders kind/model/masked from the store only (10.7).
- `HistoryPanel.svelte` — mounted only while open; registers on the Escape stack (12.8/13.3) with
  an injectable `opener`. Entries newest-first with a `<time datetime>` element; selecting one
  re-displays scope-at-ask (12.4, names via a `SourcesLike`), `direct_answer`, the stored body
  with `[[p:…]]` markers stripped, and the stored citation records through `CitationEntry` —
  no fetch happens on re-display (12.3); passage text still refetches on explicit expansion.
  Re-ask = `thread.clear()` + `thread.submit(entry.question)` — exactly "new conversation,
  current scope" (12.5). Clear-all is a two-step confirm in the header calling the store's
  `clear()` (12.6). **Gotcha:** the selected entry is `$state.raw` — a plain `$state` proxies the
  assigned object and `selected === entry` against the store's own reference never matches.

## The assembled page (`src/routes/+page.svelte`, Phase 9)

- Every store and the router are optional props defaulting to the singletons — that is what lets
  `src/routes/page.test.ts` mount the whole page over fresh instances. On mount: `sources.load()`
  then `scope.load(sources.ids)` on success, and `provider.load()`.
- The page's own (small) behaviour, beyond wiring: `ThreadStore.submitGate` (blocks submission on
  `sources.blocksSubmission` or `provider.blocksFirstTurn`, 9.13/10.4), the 3.6 release notice with
  its reinstate button (nothing else renders `scope.released`), the engine-unreachable /
  corpus-empty notices (AskSurface is unmounted in those states — the draft survives in the
  thread store), and the provider region's Escape-stack registration (ProviderConfig has no
  router; HistoryPanel and SourcePicker register themselves).
- **AskSurface owns the router's `<svelte:window>` wiring.** The page adds a window keydown that
  delegates only while `sources.state !== 'ready'` (when AskSurface is unmounted) — two active
  handlers would double-dismiss on Escape.
- The scroll container is `.content` (flex:1, overflow-y auto), not the window; `main` is 100vh.
  CitationEntry's 5.8 restore therefore scrolls the nearest ancestor whose computed overflow-y is
  auto/scroll, falling back to `window` (jsdom reports `visible` everywhere, so unit tests still
  see `window.scrollBy`). Don't "simplify" back to window-only — it is a silent no-op on the page.
- Token gotcha: the background token is `--colour-bg`, **not** `--colour-background`; the body
  styles (background, margin 0, base font) live in `+layout.svelte` as `:global(body)` because
  tokens.css only declares values. `app.html` carries the static `<title>` (10.9: never dynamic).

## Integration suite (`src/routes/page.test.ts` + `src/lib/testing/fake-server.ts`)

- `installFakeEngine()` stubs global fetch for every client.ts route; turn streams are
  turn-channel's controllable channels, one per POST /turn. Pair with `vi.unstubAllGlobals()`.
- **Flush depth**: the real client → sse → reducer path spends several microtasks per frame; a
  20-turn flush leaves a many-event turn still `streaming`. page.test.ts flushes 200 microtask
  turns + `tick()`. Symptom of too-shallow: late events (citations, second cause) miss assertions.
- The §4b completeness test types its assertion map as `Record<TurnEvent['event'], () => void>` —
  a seventeenth event fails the type check there.
- ErrorView wording keys on `reason`: `provider-unconfigured` without a reason renders the
  generic sentence, so tests wanting 9.5's wording must send `reason`. `corpus-empty` is the one
  error state with **no** button (the design records no in-app action exists).

## Browser suite (`e2e/`, Playwright)

- `playwright.config.ts` runs two webServers: `e2e/stub-engine.mjs` (Node http, port 8788) and
  `vite dev --port 4173` with `ENGINE_ORIGIN` pointed at the stub — the real dev-proxy shape, so
  the Origin rewrite is exercised. `make web-e2e` / `pnpm test:e2e`.
- The stub picks a turn script by question substring: `narrow`, `slow` (8 s of silence — the
  waiting/cancel window), `steps` (long streamed answer with a 2.5 s quiet stretch before the
  final line — the reading-position test collapses in that window), `break` (unknown outcome and
  **no `done`**, so the turn fails → the ✕ state; with `done` it settles and the state line reads
  finished, which is what 9.4's broken *renderer* plus a settled turn produces).
- **`reuseExistingServer: true` keeps a stale stub across edits** — `pkill -f stub-engine.mjs`
  after changing it, or the old scripts keep serving.
- Headless chromium has no PDF viewer: a `#page=N` popup never "navigates", so open-at-source
  asserts the focused link's href + that a new tab opened and the opener stayed put.
- 5.8's restore is geometrically impossible until the thread overflows `.content` — the test
  waits for `scrollHeight > clientHeight + 40` before expanding.
- axe runs at the WCAG A/AA tag floor (`wcag2a`, `wcag2aa`, `wcag21aa`); best-practice rules like
  heading-order would flag the h1 → h3 jump inside answers and are deliberately out of the floor.
- 200% text is tested as the WCAG reflow equivalence: viewport 640×400 at 100%.

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

vitest (jsdom) + @testing-library/svelte for units/components; @playwright/test + axe-core drive
the browser suite in `e2e/` (see "Browser suite" below). `pnpm test` runs only `src/**/*.test.ts`,
so the e2e specs never leak into the unit run.

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
- Fake-timer tests (thresholds, countdowns) must not settle turns through `vi.waitFor` where the
  assertion cares about elapsed time — `waitFor` under fake timers auto-advances them. The
  errors suite settles with a `flush()` of ~20 microtask turns + `tick()` instead (SSE frames
  travel entirely on microtasks with the stub channel), then advances timers explicitly.
- `screen.getByText` regexes over ThreadView now collide with the announcer region and the 9.14/
  9.16 notes (e.g. /finished/, /abandoned/ match twice); scope such queries to `.state` or use
  `getAllByText`.
- `src/lib/testing/turn-channel.ts` is the shared stub engine: `sseChannel()` (a controllable
  SSE `Response` carrying the version header, with an `abort()` that errors the stream the way a
  real aborted fetch does) and `fakeEngine()` (records `TurnRequest`s, one channel per turn,
  wires the abort signal). Thread and component tests both inject `fakeEngine().submit` into
  `new ThreadStore({...})`.

## Review-pass fixes (post-Phase 9)

A requirements review over the finished surface found and fixed these; the regression tests sit in
the named suites.

- **Effects that mutate a store must untrack their store reads** — `ErrorView`'s 9.11 drop read
  `scope.isSelected` inside `$effect`, so the effect re-ran on every scope change and vetoed the
  user's own re-selection while the turn stayed mounted. The drop is now wrapped in `untrack`
  (`errors.test.ts` "drops once").
- **Timer effects keyed on a boolean don't reset across turns** — `WorkingIndicator` derived
  `waiting` stayed `true` when a follow-up replaced a still-waiting turn, so the 8.10 threshold
  counted from the old turn. The effect now keys on the waiting *turn object* (`waiting.test.ts`
  "measures the threshold from each turn").
- **`scope_dropped` renders in `ThreadView`, above the renderer switch** — it can accompany any
  outcome (CONTRACTS §4 puts it before `outcome`), not only an answer. `unknown-source-id` is
  excluded there because `ErrorView` owns that wording (9.11).
- **Provider disclosure ack given before Save is held pending** in `ProviderConfig` and recorded
  against the identity the engine reports *after* `choose()` — acknowledging while another
  provider is still configured must not write the ack under the old identity (10.4).
- **History guard**: `record()` skips `renderer === null` failures (9.15/9.19 rejections) and
  `incomplete` turns with no content at all — 12.7 retains only the 9.14 partial.
- **Scope indicator** at all-in-scope with ≤3 sources names them ("All in scope: A, B, C") so 2.6/
  2.7/3.3 hold together; `scope.seen` is now `$state.raw` so the picker's 2.4 "new" badge clears
  reactively on submit.
- **Decision 9**: 4.2's no-reflow guarantee is scoped to the streamed prose. Do NOT defer the
  citation list to stream end to satisfy 4.2's letter — it breaks 5.8's mid-stream expansion
  (the e2e suite exercises it) and contradicts the design's recorded 5.8 approach.
