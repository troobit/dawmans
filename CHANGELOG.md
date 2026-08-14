# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- DAWMans MVP requirements: four specs totalling 398 anchored EARS criteria —
  `data/manual-corpus` (vendor PDF ingestion into a citable corpus),
  `data/symptom-triage` (an authored symptom-to-cause source), `api/answer-engine`
  (retrieval, grounding, providers, the `StateSource` seam) and
  `ui/ask-and-source-picker` (the localhost browser surface).
- `specs/CONTRACTS.md` — governing shared contracts for the spec seams: the
  `SourceRecord`, `Passage`, `Citation` and `AnswerEnvelope` records, a closed outcome
  taxonomy, and a composed end-to-end latency budget.
- `specs/DECISIONS.md` (9 ADRs) and a generated `specs/OVERVIEW.md` index.
- Research notes in `docs/agent-notes/` for Ableton state integration and the retrieval
  approach, both verified by measurement on the target machine.
- `manuals/` for the reference PDFs, with the filename convention documented; the PDFs
  themselves are gitignored as third-party and not redistributable.

### Added (template)

- Machine entry points for external tools such as sdd-ui (`specs/template-refinement/prd.md`):
  `tools/new_project.sh` / `make new-project` for non-interactive project creation from the
  template (placeholder filling, `nextup.md` intent seeding, git init, optional worked-example
  removal), and `tools/status.sh` / `make status` for a plain-English or `--json` summary of
  where a project stands.

### Changed

- `nextup.example.md` now uses the canonical `<!-- USER -->` / `<!-- LM -->` zone markers and
  documents the `act autonomously` flag; README gained a "Machine entry points" section.
