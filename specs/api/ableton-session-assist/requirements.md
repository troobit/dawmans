# Requirements: Ableton Session Assist

**Domain:** `api` · **Capability:** ableton-session-assist · **Status:** draft

## Purpose

A producer with the Live set open asks an agent chat (Claude Code, Codex, Gemini, or a local
harness) about their mix; the agent observes the actual session through the AbletonMCP server,
advises, and — behind a terse confirmation — applies fixes. The assistant teaches when asked a
question and executes when given an instruction, so the user gets better at Live without the tool
becoming the mixer. This is also a pivot of the product surface: the corpus becomes local MCP
tools any agent loads (§9), a launcher provisions a ready session (§10), a web chat wrapper
follows as phase two (§11), and the cited turn pipeline is superseded — the legacy lane, kept
working but no longer protected from change.

## Non-Goals

- The turn pipeline and the ask-and-source-picker mode are superseded — the agent lane is the
  baseline. They receive no new capability; agent-lane work MAY change, reduce, or break them
  where that removes friction, destructively if need be, provided the change is a logged
  decision rather than a side effect.
- No web-surface work in phase one — §11 is specified now, built only after the launcher lane has
  been used in real sessions.
- No audio-signal analysis: the MCP surface carries no metering, so no loudness, peak, or spectral
  measurement is performed or claimed.
- No mixer-fader writes: the installed server exposes track volume, pan and sends as read-only.
  Level moves execute through device parameters ([5.2](#5.2)) or are taught.
- No autonomous mixing ("mix this song for me" end-to-end) — every state change is individually
  proposed and confirmed.
- No MIDI composition or arrangement authoring; note-writing and arrangement tools exist on the
  server but are out of scope except under the named-only rule ([5.3](#5.3)).
- No contribution to the ableton-mcp fork's training dataset; recording stays disabled and its
  feedback tools unused ([7.2](#7.2)).
- No restatement of the corpus product's citation rules — mixing advice is governed here, corpus
  Q&A remains governed by `api/answer-engine` and `CONTRACTS.md`.

## Terms

| Term | Meaning |
|---|---|
| **Assistant** | The agent (any harness) following this workflow with the AbletonMCP tools available. |
| **Session** | The Live set currently open in Ableton Live 12 Standard on this machine. |
| **Observation** | Data read from the session through the MCP server: track list, mixer state, device chains and parameters, clip inventory, tempo, playback state. |
| **Transport** | Session-state changes that create or destroy no material: start/stop playback, firing or stopping a clip, switching view, moving the arrangement position. |
| **Write** | Any MCP call that changes session state, excluding transport. |
| **Teach mode** | Response style for questions: explanation, click-path, shortcut, mnemonic. |
| **Do mode** | Response style for instructions: proposal, confirmation, execution, one-line report. |
| **Destructive operation** | A write that discards existing material: deleting a clip or track, clearing or overwriting notes, replacing or displacing a device. |
| **Rig** | The declared hardware and software inventory in `rig.yaml`, including the Live edition. |
| **Corpus tools** | Read-only MCP tools served locally by DAWMans over the committed index: search and passage fetch, carrying citation fields. |
| **Launcher** | The single command that starts a provisioned mixing session: chosen harness, both MCP servers, rig and workflow context loaded. |

---

## Requirements

### 1. Observation Before Advice

**User Story:** As a producer, I want advice grounded in what my session actually contains, so that suggestions name my real tracks, devices, and settings rather than guesses.

**Acceptance Criteria:**

1. <a name="1.1"></a>WHEN a request concerns the current session, the assistant SHALL read the relevant session state through the MCP server before advising, and SHALL refer to tracks and devices by their observed names and indices.
2. <a name="1.2"></a>The assistant SHALL NOT state a session fact it has not observed this conversation, and SHALL NOT claim any measured audio quantity (loudness, peak, frequency content) — level judgements are expressed in terms of observed parameter values and the user's own listening.
3. <a name="1.3"></a>WHEN observation fails or partially fails (server unreachable, Ableton not running, remote script mismatched), the assistant SHALL say in one sentence what could not be observed and SHALL NOT guess at it; a question then proceeds on rig-general advice, an instruction is answered with the manual route to do it by hand.
4. <a name="1.4"></a>WHEN observed session state contradicts the user's description (e.g. "the compressor on track 5" where track 5 has none), the assistant SHALL name the discrepancy before proposing anything.
5. <a name="1.5"></a>Observation SHALL be scoped to the request: per-track reads by default, and a full-session read SHALL exclude MIDI note contents and bulk parameter dumps unless the request needs them.

### 2. Mode Selection by Phrasing

**User Story:** As a producer in flow, I want the assistant to infer whether I want teaching or doing from how I ask, so that I never manage a mode.

**Acceptance Criteria:**

1. <a name="2.1"></a>WHEN a request seeks understanding ("why is the guitar washed out?", "can you explain compression and drive?"), the assistant SHALL respond in teach mode and SHALL NOT execute writes unless subsequently instructed; transport for audition remains available in either mode.
2. <a name="2.2"></a>WHEN a request directs an action, including polite-interrogative phrasing ("normalise track 3", "can you raise the compressor threshold on track 5?"), the assistant SHALL respond in do mode.
3. <a name="2.3"></a>IF phrasing is genuinely ambiguous, THEN the assistant SHALL default to teach mode and end with a one-line offer to execute.

### 3. Teach Mode

**User Story:** As a producer, I want explanations tied to my rig with the exact route to the control and a hook to remember it, so that next time I do not need to ask.

**Acceptance Criteria:**

1. <a name="3.1"></a>A teach-mode response SHALL contain: the concept in plain terms applied to the observed session, and the exact Live 12 route to the relevant control (menu path, click-path, or key command).
2. <a name="3.2"></a>A teach-mode response SHOULD include a mnemonic or rule-of-thumb when one exists that is shorter than the explanation it compresses.
3. <a name="3.3"></a>Teaching SHALL account for the rig declared in `rig.yaml` where relevant (currently e.g. monitoring via the audio interface's direct-monitor control, pads and shift layer per the declared controller revision), read at need rather than assumed.
4. <a name="3.4"></a>A recommendation SHALL be checked against the rig's declared Live edition, and one that requires a device or feature that edition lacks (Suite-only, Max for Live) SHALL be flagged as such.
5. <a name="3.5"></a>WHEN asserting a reference claim about Live 12 or any rig device — a menu path, control location, default value, key command, or shift-layer behaviour — the assistant SHALL check it via the corpus tools regardless of its own confidence, and SHALL name the supporting source and document version alongside the claim; IF the supporting passage's hardware applicability is `assumed` rather than `confirmed` for the rig's declared revision, the claim SHALL be flagged as such; IF the corpus does not cover the claim, or the tools are unavailable, the assistant SHALL say so and mark the claim unverified. Mixing judgement and general audio knowledge require no citation.
6. <a name="3.6"></a>WHEN the user asks for something the MCP surface cannot verify or do (true peak normalisation, a fader move), the assistant SHALL state the limit in one line and teach the in-Live route instead.

### 4. Do Mode: Suggest, Confirm, Execute

**User Story:** As a producer, I want fixes applied with minimal ceremony but never by surprise, so that flow survives and the set stays mine.

**Acceptance Criteria:**

1. <a name="4.1"></a>Before any write, the assistant SHALL state the exact change(s) in the fewest words that remain unambiguous, ending with the literal prompt "robot go?". The proposal form per write class: parameter change — target track/device, parameter, current value → proposed value; device load — device, target track, and the fact that placement is not controllable and an existing device may be displaced; rename or tempo — old value → new value.
2. <a name="4.2"></a>The assistant SHALL execute only after an affirmative reply, and SHALL execute exactly the proposed set — no additional writes ride along. A reply that modifies the proposal is a decline plus a new instruction and produces a fresh proposal; any other non-affirmative or ambiguous reply is a decline.
3. <a name="4.3"></a>WHEN confirmation arrives after intervening turns or user activity in Live, the assistant SHALL re-read the targeted state immediately before executing; IF a current value no longer matches the proposal's baseline, the assistant SHALL re-propose instead of executing.
4. <a name="4.4"></a>After executing, the assistant SHALL report what changed in one line, and SHOULD append the equivalent manual route (shortcut or click-path) in one further line.
5. <a name="4.5"></a>WHEN a write fails or the post-write observed value does not match the proposed value, the assistant SHALL report the actual resulting state rather than the intended one.
6. <a name="4.6"></a>A multi-step fix SHALL be proposed as one confirmation covering the whole ordered set; IF a step fails, the assistant SHALL halt the remaining steps, report which steps executed and which did not, and re-propose the remainder.
7. <a name="4.7"></a>Transport MAY be performed without confirmation whenever it serves the current request.

### 5. Write Scope

**User Story:** As a producer, I want a hard boundary on what the assistant may touch, so that confirmation fatigue never erodes into damage.

**Acceptance Criteria:**

1. <a name="5.1"></a>Confirmed writes MAY change exactly: track and clip names, tempo, parameters of devices already present, and loading an instrument or effect from the browser onto a track where it displaces nothing. Any write the server exposes that is not named here is out of scope and handled per [5.3](#5.3) — the list is default-deny, not illustrative.
2. <a name="5.2"></a>WHEN an instruction concerns level, the assistant SHALL route it through device parameters (an existing gain-bearing device, or a loaded utility gain device) since mixer volume, pan and sends are read-only on this server; WHERE no such route exists, [3.6](#3.6) applies.
3. <a name="5.3"></a>The assistant SHALL NOT propose or perform a destructive operation or any out-of-scope write (creating or deleting tracks or clips, writing or clearing notes, arrangement moves, a device load that would displace an existing device) unless the user's own words name that operation; when named, it still requires the §4 confirmation. WHEN a requested fix would be better served by an out-of-scope operation, the assistant SHALL say so and hand the user the route to do it themselves.
4. <a name="5.4"></a>The rollback mechanism is Live's undo, which the assistant cannot observe or invoke; at proposal time the assistant SHALL flag any write it cannot promise is one-undo-reversible, and verification of any rollback is by re-observation.

### 6. Call Economy

**User Story:** As the only user, I want the cheapest sufficient path taken for every step, so that hosted-model spend tracks the difficulty of the work rather than the volume of it.

**Acceptance Criteria:**

1. <a name="6.1"></a>WHERE a request is a reference lookup with no session dependence, the assistant SHALL answer it from a corpus-tool search under [3.5](#3.5)'s rules rather than from hosted-model recall.
2. <a name="6.2"></a>WHERE the harness supports delegation, the assistant MAY route mechanical sub-work (bulk observation summarisation, name normalisation) to a cheaper or local model, keeping mixing judgement with the orchestrating model.
3. <a name="6.3"></a>The assistant SHALL prefer one request-scoped observation over repeated polling, re-reading only what its own writes may have changed or what [4.3](#4.3) requires.

### 7. Privacy and Supply Chain

**User Story:** As the owner of unreleased music, I want nothing about my session leaving this machine except to the model provider I chose, so that using the assistant is not a disclosure.

**Acceptance Criteria:**

1. <a name="7.1"></a>Every launcher configuration that starts the MCP server SHALL set `ABLETON_MCP_DISABLE_DATASET=1` and `ABLETON_MCP_DISABLE_TELEMETRY=1` and SHALL pin the package version; the tracked `.mcp.json` is the reference instance.
2. <a name="7.2"></a>The assistant SHALL NOT invoke the server's dataset and feedback tools (`record_audition`, `rate_last_action`, `reject_last_action`, `prefer_candidate`, `submit_intent`, `set_dataset_consent`), and SHALL omit or pass empty the `user_prompt` telemetry parameter every tool carries.
3. <a name="7.3"></a>WHEN the pinned ableton-mcp version is changed, the new version's outbound behaviour SHALL be re-audited before the pin is updated, and the audit outcome recorded in the decision log.
4. <a name="7.4"></a>The assistant SHALL NOT grant dataset or telemetry consent on the user's behalf; a consent prompt from the server is relayed verbatim and answered only by the user.
5. <a name="7.5"></a>WHERE the server package is already cached locally, the workflow SHALL remain usable with no network access when driven by a local-model harness; offline operation is a supported degraded mode.

### 8. Workflow Documentation

**User Story:** As a single developer using several harnesses, I want the workflow written down harness-neutrally, so that Claude, Codex, Gemini, or a local agent can each follow the same contract.

**Acceptance Criteria:**

1. <a name="8.1"></a>The workflow SHALL be documented in `docs/workflows/` in harness-neutral terms — naming MCP tools and conventions, never one vendor's harness — following the precedent of `triage-from-threads.md`.
2. <a name="8.2"></a>The document SHALL carry §§1–7 in full — observation honesty, mode rules, teach-mode obligations, the confirmation contract, the write scope, the routing preferences, and the privacy rules — as the normative checklist an agent loads before a mixing session.
3. <a name="8.3"></a>The README's identity paragraph and `CONTRACTS.md` §8 SHALL be updated so that offline operation is stated as a supported degraded mode rather than the product identity, and the citation invariant is scoped to corpus-grounded answers while the Live-edition constraint stays universal.
4. <a name="8.4"></a>The supersession SHALL be recorded where it survives regeneration: a `superseded — legacy lane, no new capability` status marker in the `api/answer-engine` and `ui/ask-and-source-picker` requirements headers, and a statement in the README; `specs/OVERVIEW.md` is generated, never hand-edited, and surfaces the markers on regeneration.

### 9. Corpus Tools for Agents

**User Story:** As a producer in an agent chat, I want the manuals searchable as a tool in the same conversation that sees my session, so that grounded lookups beat what a generic search would give me.

**Acceptance Criteria:**

1. <a name="9.1"></a>The corpus tools SHALL expose the committed index over MCP, read-only: a search returning ranked passages, and a passage fetch addressed by `passage_id`. Both SHALL return the `CONTRACTS.md` §2 `Passage` record and §3 citation fields in full — dropping no member (`unbacked`, the degraded-text and figure flags, and `entry_location` included) and honouring the pageless rules for `authored-triage` passages rather than synthesising section or page for them.
2. <a name="9.2"></a>The tools SHALL serve only the committed view — the same data an engine turn reads. WHEN no committed view is loadable, a tool call SHALL return an error naming `dawmans ingest`, never an empty result presented as no-coverage; WHEN a newer manifest is unreadable while a loaded view is retained, the tools SHALL keep serving the retained view and carry a fault notice on results — the engine's own behaviour.
3. <a name="9.3"></a>The tools SHALL run locally and make no network request.
4. <a name="9.4"></a>Search SHALL accept an optional source scope and result limit; unscoped search covers all ingested sources, ranked by relevance with a default cap of 10 passages.
5. <a name="9.5"></a>The tools SHALL read the index through the same reader the engine uses, making [9.2](#9.2)'s same-data guarantee structural rather than asserted. `CONTRACTS.md` SHALL be amended to register the corpus tools as a consumer of `Passage` and `Citation`, and `api/answer-engine`'s scope statement SHALL name the shared reader.

### 10. Session Launcher

**User Story:** As a single developer, I want one command that starts a fully provisioned mixing session, so that no session begins with manual context assembly.

**Acceptance Criteria:**

1. <a name="10.1"></a>A single command SHALL start a mixing session: the chosen agent harness launched with the AbletonMCP server and the corpus tools configured, and the session context preloaded — the rig declaration and the workflow contract of [8.1](#8.1).
2. <a name="10.2"></a>WHEN no harness is named, the launcher SHALL use a configured default; WHEN the requested harness is not installed, it SHALL fail with a one-line error naming what is missing, not a partial session.
3. <a name="10.3"></a>WHEN Ableton is not running or the committed index is absent at launch, the session SHALL still start with the gap named in one line at launch (naming `dawmans ingest` for the index case); [1.3](#1.3) and [9.2](#9.2) govern in-session behaviour.
4. <a name="10.4"></a>WITH a local-model harness and the server packages cached, a launched session SHALL work with no network access ([7.5](#7.5)).
5. <a name="10.5"></a>Per-harness server configuration SHALL be derived from the tracked reference (`.mcp.json`) rather than restated, so the version pin and kill-switches of [7.1](#7.1) cannot drift between copies.

### 11. Web Chat Wrapper (phase two)

**User Story:** As a producer, I want the browser page to be a thin window onto the same agent session, so that the web surface and the terminal stop being different products.

**Acceptance Criteria:**

1. <a name="11.1"></a>The web surface SHALL offer an agent-session mode that renders a chat backed by an equivalently provisioned session — same context, same MCP tools, same workflow contract as a launcher session; attaching to a live terminal session is not required.
2. <a name="11.2"></a>The wrapper SHALL add no capability beyond rendering, input, and streaming; mode rules, confirmation, and write scope remain the agent's per §§2–5, and "robot go?" is answered in the chat, not by a dedicated UI control.
3. <a name="11.3"></a>WHERE the legacy ask-and-source-picker mode still exists, it SHALL remain reachable beside the agent-session mode; removing it is permitted as a logged decision, never as a side effect of wrapper work.
4. <a name="11.4"></a>Phase two SHALL NOT begin before the launcher lane has been used for real mixing sessions and its friction recorded in the decision log — the record is the entry criterion.
