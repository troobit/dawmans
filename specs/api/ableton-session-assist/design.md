# Design: Ableton Session Assist

**Domain:** `api` · **Capability:** ableton-session-assist · **Status:** draft
Requirements: [`requirements.md`](requirements.md). Phase one only — §11 (web wrapper) is
deliberately not designed here; its design happens at phase-two entry (11.4).

## Overview

Four deliverables: a corpus MCP server (`dawmans-corpus-mcp`) exposing the committed index to any
harness (§9), a session launcher (`dawmans assist`) with adapters for Claude Code, Codex, and
LM Studio (§10), the harness-neutral workflow document (§8), and the 8.3/8.4 documentation edits.
No engine, HTTP-surface, or web changes.

## Architecture

```
harness (claude / codex / LM Studio chat)
  ├── AbletonMCP server        (uvx ableton-mcp==1.4.0, env-killed telemetry)  ← .mcp.json
  └── dawmans-corpus-mcp       (stdio, new)
        └── ViewWatcher → CorpusView   (answer/view.py — the engine's reader, 9.5)
              └── retrieve()           (answer/retrieve.py — same constants, hybrid)
```

New package `src/dawmans/assist/`: `corpus_mcp.py` (server), `launch.py` (launcher + adapters).
It imports from `dawmans.answer.{view,retrieve}` and `dawmans.index.lexical` — consumption, not
modification of behaviour; the legacy lane keeps working (Non-Goals), though it is superseded,
not frozen — changing it in service of this lane is permitted as a logged decision.

Entry points: the launcher is a `dawmans assist` subcommand in `cli.py`; the corpus server gets
its **own console script** `dawmans-corpus-mcp = dawmans.assist.corpus_mcp:main`. It cannot live
in `cli.py`: that module imports `PdfLoader` at module level, which imports `pymupdf` — so any
`cli.py` subcommand pays the AGPL import in its process. The separate script keeps the corpus-mcp
process clean, enforced by an assist-side confinement test mirroring `test_no_pymupdf.py`.
(That `cli.py` module-level ingest import also means `dawmans serve` in a serve-only environment
imports `pymupdf` — a pre-existing defect this suite fixes in passing, now that the legacy lane
is superseded rather than frozen: a task defers `cli.py`'s module-level ingest imports into the
command functions, which also unbreaks `dawmans --help` and `serve` in a serve-only environment.
The separate console script stays regardless — it is the cleaner entry either way.)

**Both MCP servers are declared in the tracked `.mcp.json`** — `DawmansCorpus` is added beside
`AbletonMCP`. That file is the single reference (7.1, 10.5): the Claude adapter uses it natively,
the Codex and LM Studio adapters *translate* it at launch rather than restating it.

New dependency: `mcp>=2.2,<3` (official Python SDK v2 — server class `mcp.server.MCPServer`,
verified against PyPI 2.2.0; v1's `FastMCP` API no longer exists in the stable line). It lives in
a new `assist` extra — `assist = ["dawmans[serve]", "mcp>=2.2,<3"]` — mirroring the
ingest/serve split so an answer-engine host installs no SDK it never imports. No AGPL concern.

### Reuse audit (second consumer of the legacy lane's internals)

| Symbol | Existing consumers | corpus-mcp use | Change needed |
|---|---|---|---|
| `CorpusView.load` / `ViewWatcher` | `cli.run_serve`, `cli.run_validate` | `watcher.check()` per call; construction wrapped (see Error Handling — `ViewWatcher.__init__` **raises** on an unreadable manifest, so the server builds it lazily and retries per call) | none in the legacy lane; wrapping is assist-side |
| `retrieve(view, question, query, selected_source_ids, *, config)` | `answer/turn.py` | same constants except `base_cap`: the cap formula is `max(base_cap, qualifying-source floor, …)`, so a `limit` above 8 is inert against `DEFAULT_CONFIG` — the tool passes `replace(DEFAULT_CONFIG, base_cap=limit)` and still slices down to `limit` (the floor can exceed it); `limit <= 0` is rejected. `query` is a precomputed vector: the tool embeds via `embed_query`, adapting `index.embed`'s `.encode()` to the `.embed()` protocol it expects | none — config + slice in the tool |
| `index.embed.load_embedder` | ingestion | **imported, not reimplemented**: it already pins `HF_HUB_OFFLINE=1`, checks the cache, and reads the package-relative `models/` (`embed.CACHE_DIR`) — exactly the no-network discipline 9.3 needs; serve's tmp-cache silent download is the behaviour being avoided. No pymupdf on its import path | none |
| device filter (`answer/scope.py`) | `turn.py` via `candidate_pool` | applied exactly as an engine turn applies it — `candidate_pool` derives `device_scope(view, selected)` internally and no bypass exists. Unscoped search selects all sources, making the filter near-vacuous (an authored cause declaring only devices absent from every manual and from the gap report is still filtered — engine behaviour, kept); a **scoped** search behaves precisely as an engine turn with that selection would. Engine parity, documented and tested, not silent narrowing | none |

## Components and Interfaces

### 1. Corpus MCP server — `dawmans-corpus-mcp`

stdio `MCPServer`, two tools (9.1), both `async def` on the single event loop — the blocking
work (encode, retrieve, view swap) runs inline, so calls serialise by construction and
`ViewWatcher`'s lock-free mutation is safe exactly as it is in the engine's single-loop app.
Startup: `index.embed.load_embedder()` + warm encode, fail naming `make fetch-model` if the
cache is empty; then guarded view access — a small holder (`index_dir`, `watcher: ViewWatcher |
None`, `ensure()`) catches `ViewLoadError` at construction, the server starts anyway, and
`ensure()` retries per call, raising the SDK's in-band tool-error (`ToolError`) so index faults
reach the agent in-conversation (9.2), never as JSON-RPC protocol errors and never by a dead
server. `--index-dir`/`--root` flags as `serve` has.

```python
search_manuals(query: str, source_ids: list[str] | None = None, limit: int = 10) -> SearchResult
# SearchResult = {"results": [PassagePayload, ...], "below_threshold": bool,
#                 "manifest_warning": str | None}
get_passage(passage_id: str) -> PassagePayload
```

The envelope exists because a bare list has nowhere to carry result-set metadata; 9.1's
pass-through rule governs each `results[]` member, not the wrapper.

- `PassagePayload` is the CONTRACTS §2 `Passage` record **passed through verbatim from the view
  row** — no field list in assist code, so a corpus-side field addition flows through without an
  edit here (that is how "dropping no member" is made structural, 9.1) — joined with the §3
  citation fields from the owning `SourceRecord` under a `source` key, **contract names
  verbatim** (`kind`, `doc_version`, `hardware_applicability`, `display_name` — no assist-side
  respelling). Authored-triage rows carry no section/page in the view; pass-through preserves
  that (pageless rule).
- `search_manuals` ranks via `retrieve()` with `replace(DEFAULT_CONFIG, base_cap=limit)`, then
  slices to `limit` (default 10, 9.4 — without the config override, `retrieve`'s
  `max(base_cap=8, …)` makes any limit above 8 inert). WHEN nothing passes the qualification
  gate (`retrieve` returns empty `supplied`), the tool falls back to the fused-order
  top-`limit` candidates with `below_threshold: true` — the gate exists for citation refusal,
  which does not govern this surface (Decision 3); an agent gets low-confidence results
  labelled as such, never a silent empty. Unknown `source_ids` and unknown `passage_id` raise
  `ToolError` naming the id.
- Every call runs `ensure()` + `watcher.check()`. Semantics are the engine's, by the same code
  (9.5): no loadable view at all → `ToolError` naming `dawmans ingest` (9.2); a *newer* manifest
  that is unreadable while a live view is retained → the retained view keeps serving and
  `manifest_warning` carries a **fixed notice** (reuse the engine's `MANIFEST_FAULT_NOTICE`) —
  never `watcher.manifest_fault` verbatim, whose `ViewLoadError` text embeds the manifest's
  filesystem path, which no payload may carry (CONTRACTS' no-path rule; paths leak usernames to
  the model provider).
- Read-only by construction: no tool takes a write.

### 2. Launcher — `dawmans assist [--harness claude|codex|lmstudio] [--root …]`

Default harness `claude`; override by flag, then `DAWMANS_ASSIST_HARNESS` env (10.2's
"configured default"). Steps:

1. **Preconditions.** Harness binary on PATH (fail one-line, 10.2). Index manifest readable
   (warn + continue, naming `dawmans ingest`, 10.3). Embedding cache populated — resolved through
   `dawmans.index.embed.CACHE_DIR`, which is package-relative, **not** `<root>/models`, so the
   check and the server cannot disagree (warn + continue). Ableton reachability: one TCP probe of
   the remote script's port (9877, loopback — confirm against the installed remote script at
   implementation); unreachable → one warning line, session still starts (10.3).
   A `--offline` flag sets `UV_OFFLINE=1` in the spawned servers' environment so a cached
   `uvx ableton-mcp==1.4.0` resolves without touching the network (10.4 — without it, uvx may
   consult the index even with a warm cache).
2. **Config derivation (10.5).** Parse `.mcp.json` once; adapters translate:

   Exactly two servers are translated — `AbletonMCP` and `DawmansCorpus`; other `.mcp.json`
   entries (`devtools`) are none of the mixing session's business and are never propagated.

   | Adapter | Mechanism | Context delivery |
   |---|---|---|
   | `claude` | none — Claude Code reads `.mcp.json` in the repo root natively | opening prompt as the CLI argument |
   | `codex` | `-c mcp_servers.<name>.command/args/env=…` CLI overrides for the two servers; the serialization shape is pinned to the Codex CLI version verified at implementation and recorded in the decision log — a Codex update that breaks it fails at launch, visibly | opening prompt as the CLI argument |
   | `lmstudio` | merge the two servers into `~/.lmstudio/mcp.json` (Claude-compatible schema per LM Studio docs), keyed by server name, idempotent. A `.bak` of the pre-merge file is refreshed on **every** merge — a backup taken only once protects only the first mistake. The merge is last-writer-wins against a running LM Studio, which can rewrite its config on exit — the launcher says "restart LM Studio to pick this up". A repo move leaves stale absolute paths until the next launch re-merges | LM Studio chat cannot be pre-prompted from a CLI: the launcher prints the opening context block for pasting, and says so |

   Nothing is ever copied by hand into a harness config; env (kill-switches) and the version pin
   travel with the translation (7.1). Generated entries must be **cwd-independent**: LM Studio
   launches servers from an arbitrary working directory, so the `DawmansCorpus` translation emits
   `uv run --project <abs repo> dawmans-corpus-mcp --root <abs repo>` — never a bare `uv run`
   that resolves against whatever directory the harness happens to hold (`uvx ableton-mcp` is
   already location-free).
3. **Opening prompt.** One block: instructs the agent to read
   `docs/workflows/mixing-session.md` and `rig.yaml` before responding (10.1 — the contract and
   rig arrive by the agent reading the tracked files, not by inlining copies that can drift),
   plus the launch-time status lines (index missing / Ableton note).

The launcher does not check whether Ableton is running — the agent discovers that through the MCP
server and 1.3 governs (10.3 names only what the *launcher* knows: the index).

### 3. Workflow document — `docs/workflows/mixing-session.md`

Harness-neutral, precedent `triage-from-threads.md` (8.1). Carries **requirements §§1–7 in
full** as a normative checklist (8.2) — the document and the opening prompt are the only
mechanism delivering those rules to an agent, so observation honesty (§1) and the teach-mode
rules including 3.5's verify-and-name-the-source obligation (§3) are in, not just the
mode/confirmation/scope/routing/privacy sections. Includes the concrete AbletonMCP usage rules
the requirements imply: `get_track_info` as
the default read; `get_session_snapshot` only with `include_notes=False, include_params=False`
(1.5); never populate `user_prompt`; the six barred dataset/feedback tools by name (7.2). Plus a
friction-log instruction: after a session, append one line to the decision log if anything
fought the flow (feeds 11.4).

### 4. Documentation edits (8.3, 8.4)

| File | Edit |
|---|---|
| `README.md` | Identity paragraph: offline becomes "runs fully offline in a degraded mode"; add the supersession statement and a short Session Assist section (launcher, corpus tools). |
| `specs/api/answer-engine/requirements.md` | Header status → `superseded — legacy lane, no new capability` (scope sentence already amended). |
| `specs/ui/ask-and-source-picker/requirements.md` | Add the same status marker to its header block (it carries none today). |
| `specs/CONTRACTS.md` | Already amended (§ preamble, §2 consumer, §8 scoping) during requirements. |
| `specs/OVERVIEW.md` | Regenerate via `/specs-overview` at the review gate — never hand-edited. |

## Error Handling

| Condition | Behaviour |
|---|---|
| No loadable view (index absent, or manifest unreadable with no retained view — including at startup, where the guarded watcher catches `ViewLoadError` and the server still starts) | Tool call returns an in-band tool error (`isError`) naming `dawmans ingest`; construction retried per call (9.2) |
| Newer manifest unreadable, live view retained | Retained view keeps serving — engine parity by the same code — with `manifest_warning` set to the fixed notice, never the raw fault text (it embeds a filesystem path) |
| Offline launch, servers cached | `dawmans assist --offline` sets `UV_OFFLINE=1` on the spawned servers; a cold cache then fails naming the package rather than hanging on the network (10.4) |
| Index absent (launcher) | One warning line at launch; session starts (10.3) |
| `models/` not populated | corpus-mcp fails at startup naming `make fetch-model`; it runs under `HF_HUB_OFFLINE=1` and never downloads (9.3), so the launcher pre-warns on the same check |
| Ableton port unreachable (launcher probe) | One warning line; session starts (10.3) |
| Unknown `source_ids` in search / unknown `passage_id` in fetch | Tool error naming the id — never silent narrowing, never a protocol error |
| Nothing passes the qualification gate | Fused-order top-`limit` returned with `below_threshold: true` — labelled low confidence, never a silent empty |
| Harness binary missing | Launcher exits non-zero, one line naming the binary (10.2) |
| `~/.lmstudio/mcp.json` malformed | Refuse to merge; print the entries to add by hand — never overwrite a file that cannot be parsed |
| Re-ingest mid-session | Next tool call swaps to the new revision wholesale; a passage id from the old revision then errors (same contract as engine corpus routes) |

## Testing Strategy

Test tree: `tests/assist/` (filenames unique repo-wide — no `__init__.py` convention):
`test_corpus_mcp_tools.py`, `test_assist_launch.py`.

- **Payload completeness.** A plain loop over every passage of the fixture index (pass-through
  makes this a one-line equality — hypothesis machinery adds nothing here):
  `get_passage(p.passage_id)` returns every key of the view row (no dropped member, 9.1), plus
  the §3 source fields under contract names; for `authored-triage` rows, section/page absent,
  never synthesised.
- **Search contract.** Results ⊆ view passages; sliced to `limit` even when `retrieve`'s
  qualifying-source floor exceeds it; scoped search returns only in-scope sources **and** applies
  the engine's device filter identically (parity asserted against a direct `retrieve()` call);
  below-threshold fallback returns fused order flagged `below_threshold`; unknown source id and
  unknown passage id error by name (9.4).
- **Same-reader guarantee.** The behavioural test is the revision swap: rewrite the fixture
  manifest, the next call serves the new revision; corrupt the *new* manifest and assert the
  retained view still serves with `manifest_warning` set to the fixed notice and no path
  substring in any payload.
- **Error paths.** Missing index dir, and manifest-present-but-unreadable at startup → server
  alive, tool error naming `dawmans ingest` (9.2).
- **Confinement and network.** Assist-side mirror of `test_no_pymupdf.py`: the corpus-mcp process
  never imports `pymupdf`; `HF_HUB_OFFLINE=1` is set in its environment before the embedder
  constructs (9.3).
- **Opening prompt.** Pure string test: names `docs/workflows/mixing-session.md` and `rig.yaml`,
  and carries the index/Ableton warning lines when the precondition checks say so (10.1, 10.3).
- **Launcher (pure functions only, no spawning).** `.mcp.json` → codex `-c` overrides translation
  preserves command/args/env including both kill-switches (10.5, 7.1); LM Studio merge is
  idempotent and refuses malformed JSON; precondition checks return the right warn/fail set for
  index-absent and binary-absent.
- **Existing suites** (`make test`) must stay green — the only legacy-lane diff this design
  makes is the `cli.py` deferred-import fix, which changes import timing, not behaviour; the
  existing suite plus the two confinement tests hold it.

Workflow-document conformance (does an agent follow §4?) is not machine-testable and is not
claimed: it is exercised by the friction log and the phase-two gate (11.4).
