# Decision Log: Ask and Source Picker

## Decision 1: Serve the built surface from the answer-engine process, on one origin

**Date**: 2026-08-14
**Status**: accepted

### Context

DECISIONS Decision 10 puts the browser surface in SvelteKit and the answer engine in Python, with
`make dev` running both. That leaves open how the page reaches the engine, and the answer is
constrained by a security control rather than by taste: `api/answer-engine` 9.3 rejects any request
whose `Origin` is outside `{127.0.0.1:<port>, localhost:<port>, [::1]:<port>}`, and its `Host` check
is what closes DNS rebinding against a loopback service that has no authentication boundary.

A separately-served front end on its own port is *outside* that set. A `fetch` from it carries
`Origin: http://localhost:5173` and is rejected — the product would be unusable while every
same-port test passed.

### Decision

Build the surface to static assets with `adapter-static` (`ssr = false`, `prerender = true`) and
have the engine process mount them at `/`. In development, the Vite proxy rewrites `Origin` as well
as `Host` when forwarding to the engine.

### Rationale

Same-origin removes the question in production rather than answering it: there is no cross-origin
request to permit, so the engine keeps its strict guard unweakened and the client hard-codes no host
and no port.

`ssr = false` because there is no server to render on — the counterpart is a Python process and every
value on the page comes from a runtime call to it. `prerender = true` emits a static shell so first
paint costs no round trip, which is what leaves room in 8.7's 150 ms acknowledgement budget.

In development the two processes genuinely are separate, so something must bridge them. Rewriting in
the proxy is preferred over relaxing the engine's guard to any loopback port, because it keeps one
strict rule in both environments rather than a weaker rule everywhere to serve a dev-only case. The
proxy is local dev tooling on the inside of the trust boundary; the browser never reaches the engine
directly in dev.

Note that `changeOrigin: true` alone is **not** sufficient — it rewrites `Host` and leaves `Origin`
forwarded, so the rewrite must be explicit.

### Alternatives Considered

- **Relax the engine's `Origin` check to any loopback host on any port**: Simplest, and defensible
  since the `Host` check is what actually closes rebinding - Rejected because it weakens the
  production rule to serve a development convenience, and defence in depth on an unauthenticated
  local service is worth keeping intact.
- **Serve the surface from a separate static server in production too**: Matches the dev topology, so
  one configuration everywhere - Rejected: it makes the cross-origin problem permanent rather than
  dev-only, and adds a third process to a single-user local app.
- **SvelteKit SSR with a Node adapter proxying to Python**: Would give one origin - Rejected as a
  whole extra runtime and hop in the latency budget, rendering data it must fetch from Python anyway.

### Consequences

**Positive:**
- The engine's rebinding guard stays strict, and the page needs no CORS handling at all.
- One process to run in production; no host or port configuration in the client.
- The static shell paints before any network call, protecting the 8.7 budget.

**Negative:**
- The engine's HTTP surface gains a static mount, which its route table did not have — a change to
  another spec's design.
- Dev and production differ in how the request reaches the engine, so a proxy misconfiguration
  produces a failure that only appears in dev.
- The UI cannot be run standalone against a mock without replicating the proxy.

---

## Decision 2: Render the answer append-only, with block type fixed by a block's first line

**Date**: 2026-08-14
**Status**: accepted

### Context

4.2 forbids changing the vertical position of already-rendered text while streaming, except in
response to the user scrolling. The usage context is why: the user glances across a room mid-take,
and text that reflows under a glance costs the glance.

The engine streams `body_delta` events carrying a restricted Markdown subset plus typed sigil blocks,
and network chunks split at arbitrary byte boundaries — including mid-line and mid-token.

### Decision

Parse append-only. A block's type is decided by its first line and never revised: the parser holds
the current line only until its prefix is decidable (at most 10 characters, the longest prefix being
`!conflict `), fixes the type, and streams the remainder into that block.

### Rationale

The engine deliberately made every block type identifiable at column 0 without prose heuristics.
That property is what lets the client commit to a type immediately, and committing immediately is
what makes no-reflow structural rather than a thing to be careful about. A parser that re-parsed the
accumulated body on each delta would be simpler to write and would reflow on every ambiguity
resolved late — precisely the failure 4.2 names.

The buffering costs nothing against 8.8, the latency figure the user experiences: `direct_answer`
arrives as its own SSE event ahead of any `body_delta`, so the first painted token never waits on
prefix disambiguation.

The same reasoning forces two smaller rules. Incremental UTF-8 decoding (`TextDecoder` with
`{stream: true}`) is required because a multi-byte character split across two network chunks would
otherwise paint as `U+FFFD` — indistinguishable, to the user, from a `degraded` passage. And the
working indicator sits *below* the thread, never above it, so its removal cannot shift text either.

### Alternatives Considered

- **Re-parse the accumulated body on each delta**: Much simpler, and correct at rest - Rejected: it
  reflows whenever a block's type resolves late, which breaks 4.2 during exactly the window 4.2 is
  written about.
- **Buffer the whole answer and render on `done`**: Trivially satisfies 4.2 - Rejected outright; it
  discards streaming, and 8.8's keypress-to-first-painted-token target becomes keypress-to-complete.
- **Render each block into a fixed-height container**: Would prevent shift without a parser rule -
  Rejected: block heights are not knowable in advance, and reserving worst-case height wastes the
  viewport that 11.8 budgets.

### Consequences

**Positive:**
- 4.2 holds by construction, and is testable by asserting the `top` of every painted line is stable
  across frames.
- Streaming remains genuinely incremental; no content is withheld to make layout easier.
- The parser is a small state machine rather than a re-entrant Markdown renderer.

**Negative:**
- A block whose first line is malformed is typed wrongly for its whole length, with no recovery.
- The 10-character prefix buffer is a constant coupled to the engine's longest sigil; a new longer
  sigil silently breaks it unless the constant moves with it.
- Append-only means a correction the engine might later send cannot be applied to painted text.

---

## Decision 3: Citation markers are numeric superscripts; citation detail renders in a list

**Date**: 2026-08-14
**Status**: accepted

### Context

CONTRACTS §3 requires five things to be shown **inline** on a citation and never behind a disclosure:
the source `kind` (5.14), `doc_version` (5.2), `hardware_applicability` where assumed (5.3),
`unbacked` (5.16), and `has_figures` (5.4). Each exists for a real failure — the mk1/mk2 mismatch,
an authored note mistaken for the manufacturer's manual, a fix resting on no manual at all.

Against that, 11.7 budgets the user 25 words of reading before the actionable instruction, and 4.10
requires that instruction in the first rendered line. The requirements' own Risks section names the
collision: provenance marking "competes directly with 11.7's 25-word reading budget".

Separately, `citation` SSE events may arrive *after* the body text containing their marker, so a
marker's rendering cannot depend on its citation being resolved yet.

### Decision

An inline marker is a small numeric superscript, assigned in order of first appearance and painted
immediately. Everything the citation *says* renders in a citation list below the answer, where each
entry carries all five inline obligations with no disclosure in the path.

### Rationale

"Inline" in CONTRACTS §3 means *on the citation rather than behind a disclosure*; it does not mean
*in the sentence*. Reading it as the latter would put five caveats mid-prose and breach 11.7 on the
first citation of the first answer — satisfying the letter of §3 while destroying the property the
whole surface is built for.

The numeric superscript also solves the late-arrival problem. The integer is stable and its width
does not change when the matching `citation` event arrives, so resolving a citation late cannot
reflow the line it sits in — which Decision 2 would otherwise have to handle as a special case. A
marker whose width changed on resolution would reflow horizontally and push subsequent lines.

It satisfies 5.17 directly: a marker that is a digit contributes no more visual weight than the body
text beside it and is never larger than it.

### Alternatives Considered

- **Full citation text inline in the prose**: The most literal reading of "inline" - Rejected on
  11.7; five marks per citation across an answer is far past 25 words to the instruction.
- **Hover cards carrying the detail**: Compact and conventional - Rejected on 1.12, which forbids
  anything needed to read or act on an answer depending on hover, and on 13.1's keyboard-only
  requirement.
- **A footnote symbol (†, ‡) rather than a number**: Avoids implying an ordering - Rejected: symbols
  run out past two citations, and 6.6's ranked causes need citations that can be referred to by name.

### Consequences

**Positive:**
- Every CONTRACTS §3 obligation is met with no disclosure in the path, while the reading budget holds.
- Late-arriving citations cannot cause reflow, so Decision 2 needs no exception.
- Markers are keyboard-focusable targets with an obvious accessible name ("citation 3").

**Negative:**
- Checking what a claim rests on costs an eye movement to the list rather than being read in place.
- The number is meaningless outside the answer it belongs to, so a citation quoted elsewhere loses
  its referent.
- A long answer with many citations produces a long list below it, competing for the viewport that
  11.8 measures.

---

## Decision 4: `sessionStorage` presence is the session boundary for scope decay

**Date**: 2026-08-14
**Status**: accepted

### Context

3.6 releases a narrowed scope "WHEN a new session begins — the first load after a browser restart,
or a load more than 8 hours after the last submitted question". The rule exists so a narrowing made
deliberately on Monday does not silently refuse a question asked on Thursday mid-take.

The first clause is not a clock condition. Nothing in a timestamp distinguishes a browser restart
from a reload thirty seconds later.

### Decision

Use the presence of a `sessionStorage` marker as the browser-restart signal, and `lastQuestionAt` in
`localStorage` for the 8-hour clause. Either condition releases the narrowing, retaining it in
`released` so 3.6's one-activation reinstate can restore it.

### Rationale

`sessionStorage` is cleared by a browser restart and survives a reload — which is precisely the
first clause of 3.6, expressed in a primitive the browser already maintains. No heuristic, no clock
skew, and nothing to tune.

The two clauses are genuinely independent conditions, so they get two mechanisms rather than one
approximating both. A timestamp-only implementation would miss a restart inside the 8-hour window,
which is the common case: the user quits at the end of a session and comes back the next morning
seven hours later.

Release is deliberately not applied when the stored scope already equals all available sources —
otherwise the "your narrowing was released" notice would appear spuriously on most loads, and a
notice that usually means nothing is a notice the user stops reading.

### Alternatives Considered

- **A timestamp alone, with a short idle threshold standing in for a restart**: One mechanism -
  Rejected: any threshold short enough to catch a restart also fires on an ordinary pause mid-session,
  which releases a narrowing the user is actively using.
- **A session cookie**: Also cleared on browser restart - Rejected as a heavier primitive with
  server-visible semantics for a value that never leaves the page, on an app with no auth boundary.
- **Never decay; require an explicit reset**: Simplest, and never surprises by widening - Rejected
  by 3.6, and by the failure it names: a forgotten narrowing produces a refusal the user reads as
  missing documentation.

### Consequences

**Positive:**
- The restart clause is exact rather than inferred, with no threshold to tune.
- The two clauses of 3.6 map to two independent checks, so neither masks the other.
- Reinstating is one activation because the released scope is kept, not recomputed.

**Negative:**
- A user who never quits their browser only ever gets the 8-hour clause, so the two mechanisms are
  unevenly exercised and the restart path is easy to leave untested.
- `sessionStorage` is per-tab: opening the surface in a second tab reads as a new session and
  releases a narrowing the first tab is still using.
- Privacy modes and storage clearing produce a release the user did not cause and cannot explain.

---

## Decision 5: One window-level keyboard router with an explicit arming registry

**Date**: 2026-08-14
**Status**: accepted

### Context

Four criteria interact on a single keypress. 1.2 captures a printable character typed anywhere and
moves it into the question input. 1.11 reserves 1–4 when a narrowing candidate list (6.3) or the
symptom shortcuts (1.10) are armed, and requires the armed keys be shown on screen. 13.3 forbids
trapping focus and requires `Escape` to dismiss whatever holds it. 13.1 requires everything to be
keyboard-operable.

Whether a `2` types the character or selects a candidate is not knowable to any single component.

### Decision

One `keydown` listener on `window`, in `keys.ts`, holding an explicit registry of what is currently
armed. Components register and unregister; they do not handle these keys themselves.

### Rationale

1.11's rule is global by nature. A component-local handler cannot know what another component has
armed, so per-component handling would either double-handle a digit or drop it, and the bug would
depend on mount order.

The registry holds at most one armed set at a time, which is sound rather than a simplification:
shortcuts appear only on an empty input, and a narrowing turn has a question in flight, so the two
cannot both be armed. Making that an invariant of the registry means the ambiguous case cannot arise.

Rendering the digit beside each armed entry does double duty — it is 1.11's required on-screen
indication and it is 11.6's greyscale-safe channel for armed-versus-not, since a printed digit
survives greyscale where a colour cue would not.

One detail is forced by the platform: the character in 1.2 must be **inserted manually** after
focusing. The `keydown` already happened on another element, so focusing the input does not deliver
it — `preventDefault`, focus, then append.

### Alternatives Considered

- **Per-component handlers with an event-bus veto**: Keeps key handling next to the thing it acts on
  - Rejected: the veto has to run before the component's own handler, which reproduces the global
  router with extra indirection and mount-order sensitivity.
- **Bind digits only while the candidate list has focus**: Avoids the global reservation entirely -
  Rejected by 6.3 and 1.10, whose whole point is one keypress with hands full, without first
  navigating focus to the list.
- **Use a keyboard-shortcut library**: Handles chords and sequences - Rejected: this surface needs no
  chords, and the arming rule is the hard part, which no library models.

### Consequences

**Positive:**
- 1.11 is decided in one place, so the capture rule cannot disagree with itself.
- The armed indicator and the arming state come from the same registry and cannot drift apart.
- `Escape` handling and focus return are centralised alongside it, serving 13.3.

**Negative:**
- A global listener is a single point of failure: a bug in it breaks typing everywhere, not in one
  component.
- Components must register and unregister correctly on mount and unmount; a missed unregister leaves
  a stale armed digit.
- A question the user means to begin with a digit needs the input focused first — the requirements
  accept this and name the visible indicator as the mitigation.

---

## Decision 6: Assert the contrast and luminance targets from design tokens, not from screenshots

**Date**: 2026-08-14
**Status**: accepted

### Context

§11 is a set of target-and-band criteria run as the iterative loop of `PROCESS.md` §5, verified by
observing real output. The requirements say so explicitly, and for most of §11 that is unavoidable:
whether body text reads comfortably at 1.5 m is a stand-back test.

But 11.3 (body contrast ≥ 7:1, everything else ≥ 4.5:1), 11.4 (non-text indicators ≥ 3:1) and 11.5
(background relative luminance ≤ 0.08) are **arithmetic over colour values**. The requirements' own
Risks section names the danger of leaving them observational: the bands "can silently drift as the
interface changes".

### Decision

Define every colour as a design token in one CSS file, and compute WCAG relative luminance and
contrast from those token values in a unit test that fails the build on a breach. The stand-back
tests remain for everything in §11 that is genuinely perceptual.

### Rationale

A target-and-band criterion is not the same as an unverifiable one. Where the band is a number over
values the code already declares, checking it in a test is strictly better than checking it by eye:
it runs on every change, it cannot drift, and it catches the case a screenshot review misses — a
token altered for one component that breaches the floor somewhere else it is used.

This also resolves the 11.3-versus-11.5 tension the requirements record, and resolves it as they
direct. An 8:1 body target against a background at the dark end of 11.5's band drives text toward
maximal white, which 11.5 warns against; the background therefore sits at the lighter end of its
band, and the test enforces both ends rather than letting one be traded away silently.

Colour independence (11.6) stays a greyscale screenshot test, because "does this distinction survive
greyscale" is a property of the rendered composition, not of two colour values.

### Alternatives Considered

- **Screenshot review only, per the literal reading of §11**: Faithful to "verified by observing
  real output" - Rejected: it leaves a computable floor to human vigilance, and the requirements
  themselves flag silent drift as the risk.
- **An automated contrast audit over the rendered page (axe or similar)**: Catches real composed
  pairs including ones the token table does not anticipate - Kept, but as a complement rather than
  the primary check: it needs every state rendered to cover them, and a state no test renders is
  unchecked.
- **Hard-code no tokens; author colours per component**: Rejected — it makes the floors uncheckable
  in principle, since there is no enumerable set of pairs.

### Consequences

**Positive:**
- Three bands that would otherwise drift are enforced on every commit.
- The 11.3/11.5 trade-off is recorded as two enforced bounds rather than as a remembered intention.
- A token change that breaches a floor names the failing pair, rather than being spotted later.

**Negative:**
- The test checks *declared* pairs. A component that composes two tokens the table does not pair —
  or applies opacity — can still breach a floor unnoticed.
- Token values become harder to adjust casually, which is the point but is still friction.
- It may read as satisfying §11, when most of §11 remains genuinely observational.

---

## Decision 7: An elapsed-seconds counter is the reduced-motion working indicator

**Date**: 2026-08-14
**Status**: accepted

### Context

8.2 requires a "continuously animated or otherwise unmistakably live" working indicator while
waiting for first content. 13.6 requires that when the operating system requests reduced motion,
animated indicators are replaced by non-animated equivalents that still satisfy 8.4 — working,
finished and broken distinguishable by at least two independent channels, never colour alone.

Read naively these conflict: 8.2 asks for something live, 13.6 removes the motion that usually
carries liveness. A static "Working…" label satisfies 13.6 and fails 8.2, because a static label is
indistinguishable from a stalled one at a glance from across the room.

### Decision

Under `prefers-reduced-motion`, the working indicator is an **elapsed-seconds counter** paired with
the static shape 8.4 requires. The counter is textual and updates once per second.

### Rationale

8.2's "or otherwise unmistakably live" is the clause that resolves it. A number that increments is
unmistakably live — more so than a spinner, since it distinguishes *waiting three seconds* from
*waiting thirty* — while involving no motion in the sense 13.6 and 11.9 are about: nothing moves,
travels, or animates, so nothing triggers the vestibular response the preference exists to avoid.

It also does double duty. 8.5 requires supplementary text once the wait exceeds the per-provider
threshold in 8.10, and the counter is already the thing measuring that wait, so the "taking longer
than usual" state is a change of wording beside a number the user is already reading rather than a
new element appearing.

Applying it only under reduced motion, rather than always, keeps the default case conventional: a
counter ticking on every three-second wait draws more attention than the wait deserves.

### Alternatives Considered

- **A static label plus a progress bar at indeterminate fill**: No motion, clear affordance -
  Rejected: an indeterminate bar that does not move is indistinguishable from a stalled one, which
  is the exact failure 8.2 guards against.
- **Keep a slow animation under reduced motion, on the grounds that it is small**: Rejected — the
  preference is a user's stated need, not a hint to be weighed against convenience.
- **Use the counter in all cases, animated or not**: Simpler, one code path - Rejected as too
  attention-hungry in the ordinary case, where waits are short and a spinner reads as calmer.

### Consequences

**Positive:**
- 8.2 and 13.6 are both satisfied without either being read down.
- 8.5's threshold state reuses the element already on screen instead of introducing one.
- The counter makes a slow provider visible as slow, which is what 8.10 needs tuning data for.

**Negative:**
- Two working-indicator implementations exist, and the reduced-motion one is the less-exercised path.
- A per-second text update is an `aria-live` hazard: the region must not announce each tick, so the
  counter is excluded from the announcement region of 13.5.
- A visible counter may read as a promise about how long the wait will be, which it is not.

---

## Decision 8: The thread mints its conversation id client-side

**Date**: 2026-08-15
**Status**: accepted

### Context

A follow-up turn must name the conversation it continues: `POST /turn` carries `conversation_id`,
and `api/answer-engine`'s design states only that "null starts one" (its 10.6). No CONTRACTS §4b
event, envelope field, or response header carries a conversation id back to this surface, so there
is no channel by which the engine could issue one. Yet 1.7 makes every question over a rendered
answer a follow-up, and 12.5's re-ask must start a new conversation — both require the client to
say which conversation a turn belongs to.

### Decision

The thread sends `conversation_id: null` on the first turn of a thread — the specced way to start a
conversation — and mints one id (`crypto.randomUUID()`) once that turn is accepted, sending it on
every follow-up in the thread. `clear()` (1.7's fresh context-free thread) resets the id to null.

### Rationale

The engine retains a single current conversation in memory (its §10), so the id's job is only to
distinguish "continue what you are holding" from "discard and start over". Null already means the
latter by specification; any stable non-null token serves the former. Minting client-side needs one
engine-side sentence — a non-null id continues the current conversation — rather than a new
response channel, and it keeps 12.5's `conversation_id: null` re-ask exactly as the design states
it.

### Alternatives Considered

- **The engine issues the id in a response header or stream event**: The conventional shape -
  Rejected: it amends CONTRACTS §4b's closed event set (or invents an ungoverned header) for a
  value the single-conversation engine never needs to disambiguate.
- **Mint the id before the first turn and never send null**: One code path - Rejected: "null starts
  one" is the only specced start primitive, and 12.5 names `conversation_id: null` explicitly; a
  first turn carrying an unknown id would rest on a larger unspecced assumption.

### Consequences

**Positive:**
- Follow-up continuity works against the engine as specified, with no contract amendment.
- The re-ask and fresh-thread paths remain exactly as the requirements and design word them.

**Negative:**
- The engine must treat a non-null `conversation_id` as continuing its current conversation; that
  sentence is owed to `api/answer-engine`'s design when the route is implemented.
- Two rapid first submits can both carry null and start two conversations; the engine's own
  cancel-on-new-question rule (its 9.13) already bounds the effect to the abandoned turn.

---

## Decision 9: 4.2's no-reflow guarantee covers the streamed prose, not the sub-answer sections

**Date**: 2026-08-15
**Status**: accepted

### Context

CONTRACTS §4b leaves `citation`, `contributing_sources` and `uncovered_parts` unordered relative
to `body_delta`, so a citation entry can paint below a body that is still growing — and every
later delta then pushes that entry down. Read literally, 4.2 ("the system SHALL NOT change the
vertical position of text that has already been rendered" while streaming) forbids this. But the
design's own 5.8 approach records the citation element's rect before expansion *because* "content
above may have grown while streaming continued", and 5.18 prefetches passages on focus — both
presuppose citations that exist and are usable while the stream is still running. A review pass
flagged the tension; deferring the citation list to stream end was tried and broke 5.8's
mid-stream expansion, which the browser suite exercises deliberately.

### Decision

4.2 is honoured for the streamed prose — block typing fixed at the first line, width-stable
markers, the working indicator below the thread — while the citation list, contributing-sources
line and uncovered-parts section paint as their events land, below the growing body. 5.8's
rect-based position restore is the compensation for the movement this permits.

### Rationale

The two requirements are jointly satisfiable only by scoping 4.2: 5.8 and 5.18 make no sense
unless citations are interactable mid-stream. The reading cost 4.2 protects against — text
shifting under the user's eyes — concerns the prose being read; the list below is chrome the user
reaches deliberately, and the one interaction that cares about its position (collapse after
expansion) restores it explicitly. The e2e no-reflow proof samples exactly the prose block
classes, which is this scoping stated as a test.

### Alternatives Considered

- **Defer the sub-answer sections until the turn settles**: Structurally satisfies 4.2's letter -
  Rejected: breaks 5.8's mid-stream expansion and 5.18's focus prefetch during long streams, and
  contradicts the design's recorded 5.8 approach.
- **Reserve fixed space for the citation list up front**: No movement, no deferral - Rejected: the
  entry count is unknown until the stream ends, so the reservation is either wrong or a scrollable
  inner region — a disclosure by another name, which 5.x forbids for citation obligations.

### Consequences

**Positive:**
- Citations are readable and expandable as soon as they arrive, keeping 5.18's 150 ms target
  reachable during long streams.
- The streamed prose keeps its structural no-reflow guarantee, provable by the browser suite.

**Negative:**
- Already-painted citation entries move down while the body grows; a user reading the list during
  a long stream sees it shift. 5.8's restore covers the expansion path only.

---

## Decision 10: Sources and symptoms are pictogram tiles; the expanded picker is a panel

**Date**: 2026-08-16
**Status**: accepted

### Context

The surface was legible but uniformly typographic: choosing a source meant reading a line of
16 px text per entry inside a list, and the four symptom shortcuts were text buttons the size of
their words. Sitting back from the second screen, nothing on the page said *what to click* — every
control had to be read before it could be aimed at. That is the gap [2.14](requirements.md#2.14)
(in/out of scope readable at 1.5 m without reading body text) and [11.7](requirements.md#11.7)
(reading budget before action) already name as targets, and neither was being met by the list.

Making the targets large enough to satisfy them costs viewport height, and
[11.8](requirements.md#11.8) budgets that height: at rest, with the picker collapsed, question and
answer must hold ≥ 70% of a 1280×800 window. A first pass that put the tiles in the layout — a
two-row header and a column of large shortcut tiles — measured 0.59, below even 11.8's band.

### Decision

Sources and symptom shortcuts are **tiles carrying a pictogram**, and the expanded picker is an
**absolutely positioned panel** under the scope bar rather than a block in the page layout. Every
pictogram is `aria-hidden` and sits beside the words it illustrates. The pictogram set and the
source-to-pictogram rule live in `web/src/lib/components/pictograms.ts`, rendered by
`Pictogram.svelte`; nothing else in the surface may declare a picture.

### Rationale

Floating the expanded picker is what makes the tiles affordable: 11.8 measures the *collapsed*
state ([2.11](requirements.md#2.11)), so a panel that overlays the thread costs the answer nothing
while giving the tiles the full width of the scope bar. With the panel floated, the chrome that
remains in the layout is one bar and one row of shortcuts, and the measured ratio is 0.73.

The picture is an *additional* channel, never a replacement. In/out of scope is still carried by
the filled-versus-hollow marker, the words "in scope" / "out of scope", and the solid-versus-dashed
tile edge — three channels that all survive greyscale ([11.6](requirements.md#11.6)) — and the
accessible name of every control is unchanged, which is why the existing suites pass untouched.

Pictograms are line art in a 24-unit box, not photographs of gear: a photograph would need per-device
assets the repository does not have and could not fetch (the surface is served from loopback and
must work offline), and it would not read at all in greyscale at 1.5 m. Which pictogram a manual
gets is a keyword table over the vendor and product words the engine already reports, with a
neutral book as the fallback — presentation only, deciding no behaviour.

### Alternatives Considered

- **Photographs or vendor logos per device**: The most recognisable picture possible - Rejected:
  needs binary assets per device, cannot be fetched at run time from a loopback-only surface, and
  fails 11.6's greyscale reading and 11.4's indicator contrast at small sizes.
- **Keep the picker expanded at rest so the checkboxes are always on screen**: Removes the click
  that opens it - Rejected: 2.11 requires collapsed-at-rest and 11.8 measures the chrome budget
  there; the tiles in the layout measured 0.59, outside 11.8's band entirely.
- **Tiles in the layout, with the shortcuts shrunk to compensate**: No overlay machinery -
  Rejected: it trades one target's legibility for another's, and the measurement showed it does not
  buy back enough height to reach 11.8's target anyway.
- **Leave the picker as a text list and raise only the type size**: Simplest change - Rejected:
  2.14's "without reading any body text" is a criterion about *not reading*; larger text is still
  text.

### Consequences

**Positive:**
- In/out of scope is readable from across the room from the tile's shape and weight alone, with the
  pictogram naming the device before its label is read (2.14, 11.7).
- The expanded picker gained room: source tiles reflow into a grid that holds twelve sources
  without scrolling (2.13) and collapses to one column at 640 px without horizontal scroll (13.7).
- 11.8 improved against the pre-change surface (0.73 measured, target ≥ 0.70), because the panel
  left the layout.
- Native controls now render dark (`color-scheme: dark` on `:root`), <!-- spelling-ignore -->
  so an unchecked checkbox is no longer a white square on a dark tile.

**Negative:**
- The collapsed scope bar clips its source names with an ellipsis when three long names plus the
  affordance exceed the bar's width. 2.6's names remain complete in the button's accessible name
  and in the panel, but a sighted user on a narrow window sees them truncated — the alternative was
  a second flex line costing 26 px, which puts 11.8 under its target.
- The picker's expanded panel overlays the thread rather than pushing it down, so the first lines
  of an answer are covered while the picker is open.
- A keyword table decides which pictogram a manual wears; a device whose name matches no term gets
  the neutral book. The table is presentation-only, but it is a place where adding a manual can
  produce a mildly wrong picture until a term is added.
