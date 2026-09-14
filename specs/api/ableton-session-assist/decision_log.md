# Decision Log: Ableton Session Assist

## Decision 1: Live-session assistance lands at the agent harness; DAWMans provisions it

**Date**: 2026-09-14
**Status**: accepted

### Context

DECISIONS.md Decision 4 deferred session awareness behind an engine-side `StateSource` seam, and
Decision 8 fixed the first implementation as saved-file/log-file reading, rejecting a live feed
because it rides Live's undocumented control-surface API. The ableton-mcp package has since been
installed: it bundles its own remote script and exposes the live session as MCP tools, which every
agent harness in use (Claude Code, Codex, Gemini, local) already speaks.

### Decision

Live-session mixing assistance is delivered through agent chats using the AbletonMCP server
directly; the agent harness is the runtime. DAWMans' role is provisioning: corpus MCP tools, a
session launcher, and — phase two — a web page that is a thin window onto the same agent session
(Decision 6). The turn pipeline's `StateSource` seam and Decision 8's file-route plan stand,
unbuilt, in the legacy lane.

### Rationale

The harnesses already provide the MCP client, the conversation surface, and multi-model routing —
rebuilding those inside the engine buys nothing for a single user. The maintenance risk Decision 8
priced (undocumented API breaking between Live versions) is now carried by the upstream package
rather than by this repository. The workflow contract ships immediately; DAWMans code is additive
provisioning rather than a redesign of the turn pipeline.

### Alternatives Considered

- **Engine-integrated MCP client with a confirm UI in the web surface**: One product, any provider,
  including local — Rejected for cost: the provider protocol is text-deltas-only, so action
  proposals, tool loops, and a confirmation UI are a redesign of the engine's core contract for no
  gain over surfaces that exist today.
- **Build the live feed in-house per Decision 8's designed-for path**: Own remote script, engine
  StateSource implementation — Rejected because it re-acquires exactly the ownership cost
  Decision 8 declined, now with a maintained third-party alternative installed.

### Consequences

**Positive:**
- Usable now; the workflow is harness-neutral by construction.
- Model routing (hosted for judgement, local/cheap for mechanical work) comes free from the harness.

**Negative:**
- Until phase two, the mixing assistant lives outside the DAWMans web UI.
- Session context and conversation history are per-harness, not shared with the legacy lane.
- A Live update that breaks the bundled remote script disables the capability until upstream fixes it.

---

## Decision 2: Pin ableton-mcp and hard-disable its dataset recording and telemetry

**Date**: 2026-09-14
**Status**: accepted

### Context

PyPI `ableton-mcp` 1.4.0 (installed via uvx) is a fork of ahujasid/ableton-mcp carrying a
telemetry layer and a dataset recorder that uploads prompts, MIDI notes, track/clip names, and
device settings to Supabase. Recording is opt-out and ON by default — an unanswered consent prompt
records. On this install it is inert only because the wheel omits the credentials module
(`MCP_Server/config.py`), so a routine package update could activate uploading silently. The
session content at stake is unreleased creative work.

### Decision

`.mcp.json` pins `ableton-mcp==1.4.0` and sets `ABLETON_MCP_DISABLE_DATASET=1` and
`ABLETON_MCP_DISABLE_TELEMETRY=1` in the server's environment; every other launcher configuration
carries the same pair (requirements 7.1). The env kill-switch overrides all consent state by
design, so this holds regardless of the consent file. The fork's collection design also lives in
its tool surface — six dataset/feedback tools, a `user_prompt` telemetry parameter on every call,
and a session snapshot defaulting to full MIDI and parameter capture — so the assistant is barred
from those tools and that parameter, and broad reads exclude note contents (requirements 7.2,
1.5). Any version bump requires re-auditing outbound behaviour first (7.3), and consent is never
granted by an agent on the user's behalf (7.4).

### Rationale

The env vars are the fork's own strongest off-switch ("wins outright" over consent state), survive
package updates, and live in the tracked `.mcp.json` where every harness inherits them. Pinning
turns a silent-activation risk into a deliberate, audited step.

### Alternatives Considered

- **Vendor the upstream ahujasid server into `tools/`**: No telemetry code at all — Rejected for
  now as the highest-effort option; the pin + kill-switches give the same observable behaviour and
  the audit-on-bump rule catches regressions. Revisit if an audit ever fails.
- **Rely on the missing credentials file**: It is inert today — Rejected because that is an
  accident of packaging, not a control; one wheel rebuild upstream ends it.
- **Opt in and contribute to the dataset**: Rejected by the user; the session content is unreleased
  work.

### Consequences

**Positive:**
- No session content leaves the machine through the MCP server, provably by configuration.
- Updates become deliberate: the pin forces the audit conversation.

**Negative:**
- Bug fixes and new tools upstream arrive only via a manual, audited bump.
- The audit rule is process, not enforcement — nothing mechanical blocks an unaudited pin change.

---

## Decision 3: Mixing advice is uncited; the citation invariant stays with the corpus product

**Date**: 2026-09-14
**Status**: accepted

### Context

DAWMans' corpus product promises that every factual claim carries a citation, and Decision 7
extended sources rather than relax that rule. Live mixing advice is different in kind: it blends
observed session state (not in any manual), general audio engineering knowledge (in the model, not
the corpus), and judgement ("washed out") that has no citable ground truth.

### Decision

Session-assist advice carries no citation requirement. The manuals serve as grounding context —
akin to a system prompt — and the model's broader knowledge is in play. Two honesty rules replace
citations: session facts must be observed, never assumed (requirements 1.2), and doubtful Live 12
reference claims (menu paths, key commands, defaults) are verified against the committed index
before being asserted (3.5). `CONTRACTS.md` §8 is amended in the same pass: its citation
obligation is scoped to corpus-grounded answers, while its Live-edition constraint stays universal
and is imported here as requirement 3.4 — scoping the whole spec out of §8 would silently discard
that constraint.

### Rationale

The user is results-driven here: nixing good advice because it cannot be referenced would discard
the value the model brings. The corpus product's differentiator (Decision 7's rationale) is
untouched because this is a separate surface with a separate contract — the failure mode citations
guard against (confident fabrication) is handled by the observation and verification rules instead.

### Alternatives Considered

- **Extend the citation model with a "session snapshot" citation kind**: Teaching claims cite
  manuals, observations cite a timestamped snapshot — Rejected by the user as process over results;
  it also drags the engine's citation machinery into a capability that runs outside the engine.
- **Forbid model knowledge, corpus-only advice**: Rejected because the manuals document controls,
  not mixing practice (Decision 7 established this measurably); corpus-only mixing advice is an
  empty set.

### Consequences

**Positive:**
- Advice quality is bounded by the model, not by what vendors chose to document.
- The corpus product's citation promise is not diluted — the two contracts are stated separately.

**Negative:**
- Wrong mixing advice is only as detectable as the user's ears; there is no citation to check.
- Two adjacent surfaces now have different grounding rules, which must stay legible to avoid
  eroding trust in the cited one.

---

## Decision 4: Suggest-first with a terse fixed confirmation; write scope includes device loading; destructive only when named

**Date**: 2026-09-14
**Status**: accepted

### Context

Interventions during mixing must not break flow, but an agent with write access to an open set can
do irreversible damage. The MCP surface spans reads, device-parameter writes, device loading,
transport, and destructive operations (delete clip, clear notes). Source verification of
ableton-mcp 1.4.0 established two facts the scope must respect: there is **no mixer write path** —
track volume, pan and sends are read-only (`mixer_device` is only ever read; the remote script's
dispatch table has no volume/pan/send/mute/solo command) — and `load_instrument_or_effect` takes
no chain position, so placement is Live's choice and a load onto an occupied track can displace
the existing device.

### Decision

Every write is proposed first in a per-class form (parameter: current → proposed; load: device,
target track, displacement risk; rename/tempo: old → new), ending with the literal prompt
"robot go?", executed only on affirmative, with multi-step fixes bundled into one confirmation
that halts and re-proposes on mid-sequence failure. Scope is default-deny: names, tempo,
existing-device parameters, and non-displacing device loads. Level instructions route through
device parameters (existing gain-bearing device or a loaded utility), since faders are read-only.
Destructive, structural, and displacing operations are never suggested and execute only when the
user's own words name them. Transport (play/stop/audition, view switching) is confirmation-exempt
— verified safe because the dispatch table contains no arm or record command. Live's undo is the
rollback, flagged at proposal time where a write cannot be promised one-undo-reversible, since
the assistant can neither observe nor invoke the undo stack.

### Rationale

A fixed two-word prompt is the cheapest confirmation that is still unambiguous, and one
confirmation per fix (not per parameter) keeps flow. Device loading is included because "add a
compressor and set it" is the natural unit of a fix; the learning cost is repaid by the
do-mode rule that the manual route is named after execution. The only-when-named rule for
destructive operations means confirmation fatigue can never erode into deleted material.

### Alternatives Considered

- **Read-only v1, user executes everything**: Purest teach mode — Rejected because the user
  explicitly wants "just do it" available; sometimes done beats learned.
- **Mixer/existing-device parameters only, no device loading**: Rejected as leaving the natural
  fix unit incomplete; the assistant would stop mid-fix to hand over.
- **Destructive operations behind the same confirmation as everything else**: Rejected because a
  habitual "robot go?" reflex is exactly the state in which a bundled deletion slips through.

### Consequences

**Positive:**
- One fixed prompt to habituate; no per-parameter nagging; flow preserved.
- The damage ceiling of a confirmed mistake is bounded by Live's undo.

**Negative:**
- Undo is trusted, not verified — a change Live does not put on the undo stack (some device loads)
  is harder to reverse than the rule implies.
- Phrasing-based mode selection (question vs instruction) will occasionally misread intent; the
  ambiguity rule defaults to teach, which costs a turn.

---

## Decision 5: Offline becomes a supported degraded mode, not the product identity

**Date**: 2026-09-14
**Status**: accepted

### Context

The README's identity paragraph and several documents state loopback-only operation as the
product's defining property: at answer time the only outbound request is the optional synthesis
call. Session assist runs in agent harnesses whose hosted models are network calls by nature, and
the MCP server itself is third-party code with (disabled) outbound machinery. Holding "no network"
as identity would make the new capability a contradiction.

### Decision

The repository's stated network posture loosens: the system runs fully offline as a supported
degraded mode (local-model harness, local provider kind, corpus retrieval — all network-free), and
networked operation is normal. Documents stating loopback-only as identity are updated as part of
this capability (requirements 8.3). Engine-level guarantees that are load-bearing for security —
loopback bind, Host/Origin guard, no key in logs — are unchanged.

### Rationale

The invariant that mattered was never "no packets": it was that retrieval is local, secrets stay in
the Keychain, and nothing leaves without the user choosing a provider. Those all survive. Restating
offline as a degraded mode keeps the honest version of the promise without forbidding the
capabilities the user actually wants.

### Alternatives Considered

- **Keep loopback-only identity and exempt the harness layer**: "The engine is offline; agents are
  not our concern" — Rejected as weasel wording; the user's workflow now includes networked agents
  reading their session, and the docs should say so plainly.
- **Route session assist through the local provider only**: Rejected because it caps advice quality
  at the local model permanently, for a purity the user has explicitly relaxed.

### Consequences

**Positive:**
- Documentation matches reality; the degraded mode is stated and testable (requirements 7.5).
- Engine security properties are explicitly severed from the network-posture claim, so they stop
  being collateral in this loosening.

**Negative:**
- A privacy property that was absolute becomes conditional on configuration, which is easier to
  erode by increments.
- Every document restating the old identity is now stale until 8.3 is executed.

---

## Decision 6: The corpus becomes agent tooling; the cited turn pipeline is superseded

**Date**: 2026-09-14
**Status**: accepted

### Context

The turn pipeline and ask-and-source-picker surface — retrieval, grounding, citations, refusals —
have not demonstrably beaten a plain web search or a NotebookLM call given the same inputs. The
differentiator that remains real is local, cited lookup over the exact manuals for this rig,
available *inside* a conversation that can also see the live session. Meanwhile the user asked
for the web surface to become "a thin wrapper around agent chats with explicit context
provisioning".

### Decision

DAWMans exposes the committed index as local, read-only MCP tools, and ships a launcher that
starts a chosen harness with both MCP servers and the rig/workflow context preloaded. A web
agent-session mode is phase two — an equivalently provisioned session, not an attach to a live
terminal process — gated on recorded use of the launcher lane. The turn pipeline and its surface
are **superseded, not frozen**: the agent lane is the new baseline, the legacy lane receives no
new capability, and agent-lane work may change, reduce, or break it — destructively where that
removes friction — provided each such change is a logged decision, never a side effect. The user
set this explicitly at design approval ("this suite will be a new baseline; destructive changes
are OK") after the freeze's extend-vs-duplicate ceremony generated repeated review friction. The
supersession is recorded as status markers on the two legacy specs' headers and in the README
(OVERVIEW is generated and surfaces the markers).

The seam is shared, not duplicated: the tools read the committed view through the same index
reader an engine turn uses, and they
serve the full `CONTRACTS.md` §2 `Passage` record and §3 citation fields, no member dropped,
registered there as a second consumer. In the chat, a corpus-verified reference claim names its
source and document version, and flags `assumed` hardware applicability — provenance stated
inline, which is honesty machinery, not a revival of the citation pipeline Decision 3 declined.

### Rationale

The corpus's value survives the pivot; the bespoke answer pipeline around it is what failed to
beat generic tools. Re-homing the corpus as a tool puts it where the capability now lives — the
agent chat — at the cost of a thin MCP layer over an index that already exists, rather than
another iteration on a pipeline with no demonstrated edge. Superseding rather than deleting keeps
the only fully offline, fully cited surface functional while costing no further investment — but
without the freeze's protection ceremony, which in practice taxed every new-lane design decision
that touched shared code.

### Alternatives Considered

- **Keep investing in the turn pipeline alongside the agent lane**: Rejected — two lanes of
  capability work for one developer, one of which has not beaten a Google search, is the definition
  of misallocated effort.
- **Deprecate the turn pipeline outright**: Rejected for now — it is the offline degraded mode's
  only cited surface and it works; removal buys nothing until the agent lane has proven itself in
  use. Revisit after phase two.
- **CLI-only corpus access for agents (`make sections`)**: Rejected — shelling out is clunky per
  call, returns no citation payload, and puts a build tool in the conversation loop; the MCP form
  is the same index behind a contract every harness already speaks.

### Consequences

**Positive:**
- Grounded manual lookup and live-session observation meet in one conversation — the concrete
  capability a generic search cannot match.
- One lane receives investment; the legacy lane's status is explicit rather than decaying silently, and shared-code changes no longer need extend-vs-duplicate adjudication.
- The corpus tools are harness-neutral and outlive any particular surface, including phase two.

**Negative:**
- A superseded surface still carries maintenance (dependency updates, breakage from Live updates
  to ingested manuals) with no new value arriving, and "destructive changes are OK" makes its
  gradual erosion a real possibility — the logged-decision rule is the only brake.
- The citation-first product identity narrows to one lane; the README has to say so honestly
  (requirements 8.3, 8.4).
- Phase two's entry criterion is a judgement call recorded in this log, not a measurable gate.

---

## Decision 7: Design-phase choices — shared hybrid retrieval, pass-through payloads, three adapters off one reference

**Date**: 2026-09-14
**Status**: accepted

### Context

The design phase fixed four implementation choices the requirements left open: how corpus-tool
search ranks, how the tools honour the no-dropped-member rule, which harnesses the launcher
adapts, and where the new code lives.

### Decision

(1) `search_manuals` reuses the engine's hybrid retrieval — `retrieve()` with `DEFAULT_CONFIG`,
dense + BM25 + RRF — paying the ~7 s embedding-model load once at server start; the tool slices
to `limit` itself, and a below-gate result falls back to fused order flagged `below_threshold`
(the qualification gate serves citation refusal, which does not govern this surface). Scoped
searches inherit the engine's device filter exactly — parity, not a bypass, since none exists in
`candidate_pool`. Index semantics are the engine's by the same code: no loadable view errors
in-band; a retained view stale-serves with `manifest_fault` surfaced. (2) Tool payloads pass the
view's `Passage` rows through verbatim, joined with the owning source's §3 citation fields under
contract names. (3) Adapters: `claude` (native `.mcp.json`), `codex` (`-c mcp_servers.*`
overrides for exactly the two mixing servers, shape pinned to a verified Codex CLI version),
`lmstudio` (idempotent cwd-independent merge into `~/.lmstudio/mcp.json`, opening context printed
for pasting since its chat cannot be pre-prompted from a CLI); default harness `claude`; Gemini
dropped from v1 by the user. (4) New package `src/dawmans/assist/`; the corpus server is its own
console script `dawmans-corpus-mcp`, not a `cli.py` subcommand — `cli.py` imports `pymupdf`
transitively at module level, so any subcommand there taints the process (that pre-existing
pre-existing defect is fixed by a task in this suite, the lane being superseded rather than frozen). Its embedder is
`index.embed.load_embedder`, imported — it already pins `HF_HUB_OFFLINE=1` and reads the
package-relative `models/`, the no-network discipline 9.3 requires; serve's tmp-cache download is
the behaviour avoided. Search results ship in an envelope (`results`, `below_threshold`,
`manifest_warning` — the warning is a fixed notice, never raw fault text, which embeds a
filesystem path). SDK: `mcp>=2.2,<3` (`MCPServer`/`ToolError` — v1's FastMCP no longer exists in
the stable line), in a new `assist` extra so the answer-engine host installs nothing it never
imports.

### Rationale

Hybrid reuse extends 9.5's structural guarantee to ranking behaviour — a lookup ranks the same in
a chat as in a turn, so there is one retrieval behaviour to trust, not two (user-confirmed over
BM25-only's instant start). Pass-through payloads make the no-silent-drop rule mechanical: a
corpus-side field addition reaches agents without an assist edit. One tracked reference with
translation, not duplication, is what makes 10.5 enforceable.

### Alternatives Considered

- **BM25-only search**: instant server start — Rejected by the user; lexical-only ranking
  diverges from engine behaviour and is weaker on paraphrased asks.
- **Explicit payload schema in assist code**: self-documenting tool output — Rejected because a
  hand-kept field list is exactly the silent-drop mechanism CONTRACTS forbids; the schema lives
  in CONTRACTS §2/§3, the code passes through.
- **Gemini adapter in v1**: named in early scoping — Dropped by the user in favour of LM Studio;
  the adapter table grows when a harness is actually used.

### Consequences

**Positive:**
- One retrieval behaviour, one server-config reference, one payload truth.
- LM Studio setup is automated to the extent its surface allows, honestly labelled where not.

**Negative:**
- corpus-mcp start costs ~7 s and inherits the serving-side fastembed tmp-cache gotcha; offline
  cold starts fail without `make fetch-model` plus one warmed run.
- The LM Studio lane has a manual paste step for context; parity with claude/codex is partial.
- Codex `-c` override syntax is version-sensitive; a Codex CLI update can break the translation
  and only the launcher's own failure will reveal it.

---
