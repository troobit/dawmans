---
references:
    - specs/api/ableton-session-assist/requirements.md
    - specs/api/ableton-session-assist/design.md
    - specs/api/ableton-session-assist/decision_log.md
---
# Ableton Session Assist

## Foundations

- [ ] 1. Packaging and server registration <!-- id:iq3mh9k -->
  - pyproject: assist extra = ["dawmans[serve]", "mcp>=2.2,<3"]; [project.scripts] dawmans-corpus-mcp = dawmans.assist.corpus_mcp:main; dev group gains dawmans[ingest,serve,assist]
  - .mcp.json: DawmansCorpus entry (uv run dawmans-corpus-mcp) beside the pinned, env-killed AbletonMCP entry
  - Config/wiring only - no test pair
  - Stream: 1
  - Requirements: [7.1](requirements.md#7.1)

- [ ] 2. Defer cli.py module-level ingest imports <!-- id:iq3mh9l -->
  - Stream: 1
  - [ ] 2.1. Red: import-surface test <!-- id:iq3mh9m -->
    - tests/assist/test_cli_import_surface.py: importing dawmans.cli must not import pymupdf (mirror of tests/test_agpl_confinement.py mechanics)
    - Fails today: cli.py:47 imports PdfLoader whose module imports pymupdf
  - [ ] 2.2. Green: move ingest imports into command functions <!-- id:iq3mh9n -->
    - cli.py: PdfLoader and other corpus.* module-level imports move into ingest/validate/coverage functions, same pattern the serve side already uses
    - Unbreaks dawmans --help and serve in a serve-only environment; existing make test stays green
    - Blocked-by: iq3mh9m (Red: import-surface test)

## Corpus MCP server

- [ ] 3. View holder and get_passage <!-- id:iq3mh9o -->
  - Blocked-by: iq3mh9k (Packaging and server registration)
  - Stream: 1
  - [ ] 3.1. Red: holder and payload tests <!-- id:iq3mh9p -->
    - tests/assist/test_corpus_mcp_tools.py against a fixture index
    - Holder: missing index -> ToolError naming dawmans ingest, server object still alive; index appearing later -> serves; corrupt NEW manifest -> retained view serves, manifest_warning = fixed notice, no filesystem path substring anywhere in payloads
    - Payload completeness: plain loop over every fixture passage - every view-row key present, section 3 source fields under contract names (kind, doc_version, hardware_applicability, display_name); authored-triage rows carry no section/page
    - Requirements: [9.1](requirements.md#9.1), [9.2](requirements.md#9.2)
  - [ ] 3.2. Green: implement holder, payload assembly, get_passage <!-- id:iq3mh9q -->
    - src/dawmans/assist/corpus_mcp.py: holder (index_dir, watcher: ViewWatcher | None, ensure() retries construction, raises ToolError)
    - Payload = view row passed through verbatim + source join under source key; unknown passage_id -> ToolError naming the id
    - Blocked-by: iq3mh9p (Red: holder and payload tests)
    - Requirements: [9.1](requirements.md#9.1), [9.2](requirements.md#9.2)

- [ ] 4. search_manuals <!-- id:iq3mh9r -->
  - Blocked-by: iq3mh9o (View holder and get_passage)
  - Stream: 1
  - [ ] 4.1. Red: search contract tests <!-- id:iq3mh9s -->
    - Envelope {results, below_threshold, manifest_warning}; results subset of view passages
    - limit: replace(DEFAULT_CONFIG, base_cap=limit) then slice - limit>8 effective, floor overflow sliced, limit<=0 rejected
    - Scoped search parity: identical passage set to a direct retrieve() call with the same selection, device filter included
    - Below-gate query -> fused-order top-limit with below_threshold true, never silent empty; unknown source_ids -> ToolError naming the id
    - Requirements: [9.2](requirements.md#9.2), [9.4](requirements.md#9.4)
  - [ ] 4.2. Green: implement search_manuals <!-- id:iq3mh9t -->
    - embed_query via index.embed.load_embedder adapted to the .embed() protocol (.encode() underneath, already L2-normalised)
    - Blocked-by: iq3mh9s (Red: search contract tests)
    - Requirements: [9.3](requirements.md#9.3), [9.4](requirements.md#9.4)

- [ ] 5. Server assembly and startup order <!-- id:iq3mh9u -->
  - MCPServer over stdio; both tools async def on one event loop (blocking work serialises by construction)
  - Startup: load_embedder + warm encode, exit naming make fetch-model on empty cache (test rides in test_corpus_mcp_tools.py); guarded holder; --root/--index-dir flags as serve; main() entry
  - Confinement + network tests: corpus-mcp process never imports pymupdf (mirror test_no_pymupdf.py); HF_HUB_OFFLINE=1 set before embedder construction
  - Blocked-by: iq3mh9r (search_manuals)
  - Stream: 1
  - Requirements: [9.3](requirements.md#9.3), [9.5](requirements.md#9.5)

## Launcher

- [ ] 6. Adapter and precondition functions <!-- id:iq3mh9v -->
  - Stream: 2
  - [ ] 6.1. Red: launcher pure-function tests <!-- id:iq3mh9w -->
    - tests/assist/test_assist_launch.py - pure functions only, nothing spawned
    - codex translation: exactly AbletonMCP + DawmansCorpus (never devtools), env kill-switch pair and version pin preserved, -c mcp_servers.* shape
    - lmstudio merge: cwd-independent absolute uv run --project entries, idempotent, .bak refreshed every merge, malformed JSON refused with entries printed
    - Opening prompt names docs/workflows/mixing-session.md and rig.yaml; carries index/Ableton warning lines when checks say so
    - Precondition matrix: harness binary missing -> fail; index missing -> warn; embedding cache via dawmans.index.embed.CACHE_DIR (not root/models) -> warn; TCP probe 9877 unreachable -> warn; --offline -> UV_OFFLINE=1 in spawned env
    - Stream: 2
    - Requirements: [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.3](requirements.md#10.3), [10.5](requirements.md#10.5), [7.1](requirements.md#7.1), [7.5](requirements.md#7.5)
  - [ ] 6.2. Green: implement launch.py <!-- id:iq3mh9x -->
    - src/dawmans/assist/launch.py; adapters claude (native .mcp.json) / codex / lmstudio per design table
    - Blocked-by: iq3mh9w (Red: launcher pure-function tests)
    - Stream: 2
    - Requirements: [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.3](requirements.md#10.3), [10.5](requirements.md#10.5)

- [ ] 7. Wire dawmans assist subcommand <!-- id:iq3mh9y -->
  - cli.py argparse: assist subcommand, --harness (default from DAWMANS_ASSIST_HARNESS else claude), --offline; deferred imports; spawns via launch.py
  - Wiring only - behaviour covered by 6.1 tests
  - Blocked-by: iq3mh9v (Adapter and precondition functions)
  - Stream: 2
  - Requirements: [10.1](requirements.md#10.1), [10.2](requirements.md#10.2), [10.4](requirements.md#10.4)

## Documentation and gate

- [ ] 8. Write docs/workflows/mixing-session.md <!-- id:iq3mh9z -->
  - Harness-neutral, precedent triage-from-threads.md; carries requirements sections 1-7 in full as the normative checklist
  - Concrete AbletonMCP rules: get_track_info default read; get_session_snapshot only with include_notes=False, include_params=False; user_prompt never populated; six dataset/feedback tools barred by name; robot go contract and proposal forms; level via device parameters
  - Friction-log instruction feeding 11.4
  - Stream: 3
  - Requirements: [8.1](requirements.md#8.1), [8.2](requirements.md#8.2)

- [ ] 9. README and legacy status markers <!-- id:iq3mha0 -->
  - README identity paragraph: offline = supported degraded mode; supersession statement; short Session Assist section
  - Status markers: superseded - legacy lane, no new capability on api/answer-engine and ui/ask-and-source-picker requirement headers (add Status line to the ui spec)
  - Stream: 3
  - Requirements: [8.3](requirements.md#8.3), [8.4](requirements.md#8.4)

- [ ] 10. Gate: OVERVIEW regeneration and full suite <!-- id:iq3mha1 -->
  - Regenerate specs/OVERVIEW.md via /specs-overview (never hand-edited)
  - make lint and make test green; review-gate check that code matches requirements and design
  - Blocked-by: iq3mh9k (Packaging and server registration), iq3mh9l (Defer cli.py module-level ingest imports), iq3mh9o (View holder and get_passage), iq3mh9r (search_manuals), iq3mh9u (Server assembly and startup order), iq3mh9v (Adapter and precondition functions), iq3mh9y (Wire dawmans assist subcommand), iq3mh9z (Write docs/workflows/mixing-session.md), iq3mha0 (README and legacy status markers)
  - Stream: 1
  - Requirements: [8.4](requirements.md#8.4), [9.5](requirements.md#9.5)
