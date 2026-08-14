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
