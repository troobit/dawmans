# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **This is a template repository.** New projects are created from it. The sections
> below are intentionally minimal — fill in the `TODO` placeholders once a stack is
> chosen, and delete this note in derived repos.

## Build / Test / Lint

<!-- TODO: record the non-obvious commands a derived project needs (non-standard
     scripts, required flags, or sequences). Drop anything obvious from the manifest. -->

All tooling runs through the repo-root **Makefile** — `make help` lists targets.
`make lint` runs the spelling check today; `build`, `test`, and `clean` error until
the stack is chosen. Fill them in then, and note here how to run a single test.

## Conventions

<!-- TODO: record only rules that DIFFER from language defaults, plus repo etiquette
     (branch naming, PR/commit style) and any required env vars or setup steps. -->

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

Feature work is organised under `specs/<domain>/<capability>/`. The domain is one of the
project's fixed set (see `specs/DECISIONS.md` Decision 1 — confirm or edit that set before
writing the first spec). A spec folder may hold `requirements.md`, `design.md`, `tasks.md`,
and a `decision_log.md` — not all are always present, but every file in the folder is relevant
to that capability. Name the folder for the capability it delivers, never for the layer, the
effort/phase (`mvp`, `v2`), or the word `feature`.

Root `nextup.md` is the universal entry point: run `/nextup` at the start of any
session to pick up where you left off. It has a clean divide — a "What I want" zone
you own (your words win) and a machine zone `/nextup` keeps as a plain-English
progress record. `/nextup` reads it, works out which phase to resume, and routes you
into the matching spec skill (or recommends implementation when the spec is done).
The live `nextup.md` is gitignored (personal working notes); `nextup.example.md`
ships the tracked structure and is what `nextup.md` is seeded from.
