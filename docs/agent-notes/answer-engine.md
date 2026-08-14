# Answer engine (`src/dawmans/answer/`)

Implements `specs/api/answer-engine/`. Phase 1 (package scaffold + envelope records) is done.

## Package setup

- First Python code in the repo: `src/` layout, hatchling, uv. `pyproject.toml` was created here
  even though the manual-corpus design nominally establishes the package — that spec had landed no
  code when this branch started, so the scaffold includes `src/dawmans/__init__.py` and `cli.py`
  (with only the `serve` stub registered; `ingest`/`validate`/`inventory` land with manual-corpus).
- Dependency split is load-bearing, not tidiness: `[project.optional-dependencies] ingest` holds
  PyMuPDF (AGPL) + lingua + fonttools; `serve` holds fastembed, bm25s, numpy, anthropic, starlette,
  uvicorn, keyring. The API host runs `uv sync --extra serve` and must never install `ingest`.
  `lingua-py` is `lingua-language-detector` on PyPI.
- `tests/answer/test_no_pymupdf.py` imports every `dawmans.answer.*` module in a subprocess with a
  `sys.meta_path` finder poisoning `fitz` and `pymupdf`. It walks packages dynamically and picks up
  `dawmans.triage` automatically once that package exists — no test change needed then.
- `make test` / `make lint` (ruff + spelling) / `make build` are configured; use them.

## Envelope records (`envelope.py`)

- `Citation`, `AnswerEnvelope`, `Cause`, `RequiredManual` are frozen dataclasses whose field sets
  are exactly the CONTRACTS §3/§4/§4c/§4e tables; tests assert set equality on
  `dataclasses.fields`, so adding a field means amending CONTRACTS first.
- Frozen but NOT slotted — `frozen=True, slots=True` breaks the unknown-attribute error path (see
  `rules/language-rules/python.md` in agentic-coding).
- Invariants enforced in `__post_init__` rather than by tests alone: absent-is-None (empty strings
  rejected), authored-triage citations reject `doc_version`/`section_number`/`page`,
  `entry_location` is authored-only, `causes[n].rank == n+1`, `retry_after >= 0` and unrounded,
  `framing` ∈ {parsed, unparsed}.
- `Outcome` (17) and `Reason` (5) are StrEnums mirroring CONTRACTS §6/§6a; the envelope validates
  membership at construction so an unlisted member cannot exist.
- Helper shapes not named as CONTRACTS records but implied by its payloads: `SourceRef`
  (`suggested_sources[]`/`scope_dropped[]` members), `Narrowing`/`NarrowingCandidate`,
  `RequiredDevice`, `Timings` (durations only; `corpus_reload_ms` is run-level).
- `body` is an untyped tuple for now; §4d block types arrive with `parse.py`.
