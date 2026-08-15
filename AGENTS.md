# AGENTS.md

Guidance for any coding agent working in this repository. Harness-neutral by intent: there is no
separate `CLAUDE.md`, and anything added here should read the same to every tool.

DAWMans answers home-studio questions strictly from the owner's own sources — vendor manuals plus
an authored triage store — with every claim cited. `README.md` is the product and stack intro;
this file is the working guidance that isn't in it.

## Build / Test / Lint

All tooling runs through the repo-root **Makefile** — `make help` lists targets — and `make` stays
the canonical entry point: the targets wrap the `uv run …` and `pnpm …` commands rather than
replacing them. Python dependencies are managed with **uv**, the SvelteKit side with **pnpm** —
not pip/poetry, not npm/yarn.

```
make build      # uv sync --all-extras + the web build
make test       # pytest + vitest
make lint       # spelling + ruff (check and format --check) + svelte-check
make format     # ruff format
make dev        # vite dev on 5173 and `dawmans serve` on 8722, in parallel
```

Non-obvious, and worth knowing before you run anything:

- **A single Python test:** `uv run pytest tests/answer/test_ground.py::test_name`. There is no
  make target for it; `make test-py` is the whole suite.
- **A single web test:** `cd web && pnpm vitest run src/lib/state/scope.test.ts`.
- **`tests/` carries no `__init__.py`**, so pytest imports test modules by bare basename and
  **every test filename in the tree must be unique**. Two specs each landed a `test_scope.py` on
  their own branch and the merge failed to collect. Name a test file after what it tests, not after
  the module it mirrors.
- **`addopts` pins `-m 'not bench'`**, which is what actually keeps the full-corpus timing test out
  of `make test`. `make bench` passes `-m bench` on the command line and pytest takes the last `-m`
  it is given, so the two do not fight.
- **`make fetch-model` is a one-off per machine** and needs network. It fills the gitignored
  `models/` cache with `BAAI/bge-small-en-v1.5`. Ingestion sets `HF_HUB_OFFLINE=1` in its own
  process environment and fails immediately when the cache is absent, so nothing silently
  downloads mid-run. Tests that need the model skip when it is missing.
- **`make fixtures` and `make bench-ingest` need the vendor PDFs** in `manuals/`, which are
  gitignored. Both degrade rather than fail: `fixtures` writes the synthetic rejections only,
  `bench-ingest` skips. See `specs/data/manual-corpus/prerequisites.md`.
- **`make web-e2e` needs the Playwright browser installed** — `cd web && pnpm exec playwright
  install chromium`, once per machine. The suite starts its own stub engine on 8788 and a vite dev
  server on 4173; it never touches the real engine.
- **`make build-serve` (`uv sync --extra serve`) is what an API host installs** — see AGPL
  confinement below. Dev installs both extras, which is why the confinement tests exist.

## Conventions

- Stack: Python (uv) for ingestion and the answer engine, SvelteKit (pnpm) for the browser surface,
  with a loopback HTTP boundary between them. The reasoning, the alternatives, and the costs are in
  `specs/DECISIONS.md` Decision 10 — read it there rather than relitigating it here.
- **PyMuPDF is AGPL and confined to `src/dawmans/corpus/pdf/`.** Three things enforce it and all
  three must keep passing: a ruff `banned-api` on `fitz`/`pymupdf`, `tests/test_agpl_confinement.py`
  for the package, `tests/answer/test_no_pymupdf.py` for the served process. Do not import it
  elsewhere, and do not add it to the `serve` extra. `data/manual-corpus` `decision_log.md`
  Decision 6 is the rule.
- **`src/dawmans/cli.py` defers its serve-side imports into the functions that need them.** The two
  halves install different extras, so importing starlette or fastembed at module scope would break
  `dawmans --help` in an ingest-only environment. Keep new imports in the same shape.
- Svelte work MUST use the Svelte MCP server tools and the `svelte-*` skills when creating or
  editing any `.svelte` file or `.svelte.ts` / `.svelte.js` module. The official Svelte MCP server
  supplies documentation lookup and an autofixer; run the autofixer again after applying its
  corrections to confirm the issues are resolved. The project is **runes mode**, forced in
  `web/vite.config.ts` — no `export let`, no legacy stores.
- There is no `svelte.config.js`. The adapter (`adapter-static`) and the compiler options are
  configured through the `sveltekit()` plugin in `web/vite.config.ts`.
- Irish/British English spelling in docs, comments, and user-facing strings — lint with `make lint`
  (or `bash tools/check_spelling.sh` directly).
- Commits: `[type]: Sentence-case subject`, where type is one of `feat`, `fix`, `doc`, `chore`,
  `style`. Branches are named for the work they carry, prefixed by its stage —
  `specs/<name>`, `tasks/<capability>`.
- **CI checks spelling and nothing else.** `.github/workflows/` runs `check_spelling.sh` over the
  diff plus the two Claude review workflows; no workflow runs pytest, vitest or ruff. Run
  `make test` and `make lint` locally — a green PR is not a passing suite.
- Log notable changes in `CHANGELOG.md` (Keep a Changelog format, under `[Unreleased]`).
- Module knowledge lives in `docs/agent-notes/` — read the relevant note before changing a module,
  update it after the work.
- Repeatable procedures live in `docs/workflows/`, written for any harness. The one that exists is
  [`triage-from-threads.md`](docs/workflows/triage-from-threads.md): how to turn forum reading into
  a triage entry that is grounded in the manuals. **Read it before authoring anything in `triage/`.**
  A forum thread is never a source — it is never fetched at answer time, ingested, cited or
  committed; it only informs which documented control a human decides to suspect. `make sections
  ARGS="…"` prints paste-ready `fix:` pointers from the committed index, so a section number is
  never written from memory.
- `.claude/settings.json` ships a git/make permission baseline only. Running `/project-init` to add
  Python and Node permissions is still outstanding.

## Secrets and the network

- **The Anthropic key lives in the macOS Keychain** under service `dawmans`, account `anthropic` —
  never in a file, an environment variable, or a log line. `credentials.read_key()` has exactly one
  caller, a provider's client constructor; every other path takes `mask()`. A `SecretFilter` on the
  root log handler is the backstop, not the mechanism.
- **The engine binds loopback or refuses to start.** No fallback bind, and `HostOriginGuard` rejects
  any non-loopback `Host` or `Origin`. Do not add a `--host 0.0.0.0` escape hatch; `api/answer-engine`
  9.1–9.3 is the constraint.
- **No filesystem path may appear in any response payload.** A manifest fault reports a fixed notice
  instead of the path that failed.
- The dev vite proxy has to rewrite `Origin` itself — `changeOrigin: true` only rewrites `Host`, so
  without the rewrite every proxied request in dev is a 403. Point it elsewhere with
  `ENGINE_ORIGIN`.

## Stack preferences

Default tooling choices for work that reaches beyond the current stack. Maintainer guidance; not
user-facing.

- **IaC:** OpenTofu (`tofu`), not Terraform.
- **Cloud:** Azure over AWS where cloud hosting is required.
- **AI / compute:** prefer local and FOSS solutions over paid API or hosted-ML calls unless there's
  a clear reason the local option won't do. The `local` provider kind is that preference in code.

The `.github/workflows/` tree still carries two dormant template workflows —
`build-container.yml` (no Dockerfile exists) and `opentofu-deploy.yml` (no IaC exists). Neither
applies to a loopback-only app; leave them alone or delete them deliberately, but don't wire work
into them by accident.

## Spec-driven workflow

The full process is `specs/PROCESS.md` — read it before creating or changing a spec.

Feature work is organised under `specs/<domain>/<capability>/`. This project's domain set is
`platform`, `data`, `api`, and `ui` — `ops` was pruned (see `specs/DECISIONS.md` Decision 1);
amending the set is an amendment to that decision. A spec folder may hold `requirements.md`,
`design.md`, `tasks.md`, and a `decision_log.md` — not all are always present, but every file
in the folder is relevant to that capability. Name the folder for the capability it delivers,
never for the layer, the effort/phase (`mvp`, `v2`), or the word `feature`.

`specs/CONTRACTS.md` is **governing** for anything crossing a spec boundary — the shared
records, the outcome taxonomy, and the composed latency budget. Where a spec and CONTRACTS
disagree, CONTRACTS wins and the spec is the defect (see `specs/DECISIONS.md` Decision 6).

All four specs are implemented and merged on `main`. `platform` has no spec and owns real
outstanding work: the app shell, the build, and where a key is stored on the machine are currently
described only from the two sides that consume them. `specs/OVERVIEW.md` is generated — regenerate
it rather than hand-merging it.
