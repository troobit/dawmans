# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **This is a template repository.** New projects are created from it. The sections
> below are intentionally minimal — fill in the `TODO` placeholders once a stack is
> chosen, and delete this note in derived repos.

## Build / Test / Lint

<!-- TODO: record the non-obvious commands a derived project needs (non-standard
     scripts, required flags, or sequences). Drop anything obvious from the manifest.
     Still outstanding: how to run a single test, once `test` is configured. -->

Python owns ingestion and the answer engine; SvelteKit owns the web surface. Python
dependencies and environments are managed with **uv** (`uv run …`, `uv sync`), and the
SvelteKit side with **pnpm** (`pnpm install`, `pnpm dev`) — not pip/poetry, not npm/yarn.

All tooling runs through the repo-root **Makefile** — `make help` lists targets — and
`make` stays the canonical entry point: once configured, the targets wrap the `uv run …`
and `pnpm …` commands rather than replacing them. `make lint` runs the spelling check
only today. `build`, `test`, and `clean` still error: they are not yet configured for the
chosen stack, and doing so is outstanding work.

## Conventions

<!-- TODO: record only rules that DIFFER from language defaults, plus repo etiquette
     (branch naming, PR/commit style) and any required env vars or setup steps. -->

- Stack: Python (uv) for ingestion and the answer engine, SvelteKit (pnpm) for the
  browser surface, with a loopback HTTP boundary between them. The reasoning, the
  alternatives, and the costs are in `specs/DECISIONS.md` Decision 10 — read it there
  rather than relitigating it here.
- Svelte work MUST use the Svelte MCP server tools and the `svelte-*` skills when
  creating or editing any `.svelte` file or `.svelte.ts` / `.svelte.js` module. The
  official Svelte MCP server supplies documentation lookup and an autofixer; run the
  autofixer again after applying its corrections to confirm the issues are resolved.
- Irish/British English spelling in docs, comments, and user-facing strings — lint
  with `make lint` (or `bash tools/check_spelling.sh` directly).
- Log notable changes in `CHANGELOG.md` (Keep a Changelog format, under `[Unreleased]`).
- Module knowledge lives in `docs/agent-notes/` — read the relevant note before
  changing a module, update it after the work.
- `.claude/settings.json` ships a git/make permission baseline; run `/project-init`
  after choosing a stack to add language-specific permissions.

## Stack preferences

Default tooling choices when a stack is being set up. These inform tooling, CI, and
`.gitignore` decisions; they are maintainer guidance and need not be surfaced to end
users.

- **IaC:** OpenTofu (`tofu`), not Terraform.
- **Cloud:** Azure over AWS where cloud hosting is required.
- **AI / compute:** prefer local and FOSS solutions over paid API or hosted-ML calls
  (Claude API, etc.) unless there's a clear reason the local option won't do.

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

Root `nextup.md` is the universal entry point: run `/nextup` at the start of any
session to pick up where you left off. It has a clean divide — a "What I want" zone
you own (your words win) and a machine zone `/nextup` keeps as a plain-English
progress record. `/nextup` reads it, works out which phase to resume, and routes you
into the matching spec skill (or recommends implementation when the spec is done).
The live `nextup.md` is gitignored (personal working notes); `nextup.example.md`
ships the tracked structure and is what `nextup.md` is seeded from.
