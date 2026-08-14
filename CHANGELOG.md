# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- Machine entry points for external tools such as sdd-ui (`specs/template-refinement/prd.md`):
  `tools/new_project.sh` / `make new-project` for non-interactive project creation from the
  template (placeholder filling, `nextup.md` intent seeding, git init, optional worked-example
  removal), and `tools/status.sh` / `make status` for a plain-English or `--json` summary of
  where a project stands.

### Changed

- `nextup.example.md` now uses the canonical `<!-- USER -->` / `<!-- LM -->` zone markers and
  documents the `act autonomously` flag; README gained a "Machine entry points" section.
