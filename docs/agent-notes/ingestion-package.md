# The `dawmans` ingestion package

Python side of the repo: `src/dawmans/`, one installable package, managed with uv.
Implements `specs/data/manual-corpus`. SvelteKit owns the browser surface and is a
separate tree.

## Layout and tooling

- `src/` layout, `pyproject.toml` at the repo root, hatchling build backend. Everything
  runs through the Makefile: `build` (`uv sync`), `test` (`uv run pytest`), `lint`
  (spelling + `ruff check` + `ruff format --check`), `clean`, `fetch-model`, `bench`.
- uv resolved to Python 3.12 (`requires-python = ">=3.12"`).
- Dependencies arrive with the code that uses them. Declared so far: `pymupdf` (task 1,
  for the AGPL rule to have something to bite on) and `fastembed` (needed by
  `make fetch-model`). `bm25s`, `lingua-language-detector`, `fonttools` and `pyyaml`
  come with their phases.
- `ruff format` rewrites Python code blocks **inside Markdown**, which would reflow the
  deliberately aligned samples in `specs/`. `extend-exclude = ["*.md"]` in `pyproject.toml`
  stops it; do not remove that line.
- `tools/check_spelling.sh` scans every git-tracked file, source included, and is
  case-sensitive. Write `normalised`, `initialise`, `serialise` in Python too — a
  banned word in a docstring fails `make lint`.

## The AGPL confinement

PyMuPDF is AGPL-3.0-or-later, so publishing this repository conveys a combined work
under the same licence (`decision_log.md` Decision 6). It may be imported **only** under
`src/dawmans/corpus/pdf/`, which keeps the constraint on the ingestion tool and away
from the process `api/answer-engine` runs. Two mechanisms enforce it, deliberately:

- `[tool.ruff.lint.flake8-tidy-imports.banned-api]` bans `fitz` and `pymupdf`, with a
  per-file-ignore for `src/dawmans/corpus/pdf/*`. Fast, but it reads one file at a time.
- `tests/test_agpl_confinement.py` walks the package AST, so `make test` catches it too,
  including `importlib.import_module("fitz")`, which the linter does not see.

## Records

`records.py` is CONTRACTS §1 and §2 verbatim — no field added, none dropped, asserted by
`tests/test_records.py` against the field set itself. Both records are frozen, slotted
and keyword-only so they read in the CONTRACTS table's order.

Non-obvious constructor rules, all of them from the spec rather than from taste:

- Kind-dependent fields are enforced **both ways**: an `authored-triage` source refuses
  `vendor`/`product`/`doctype`/`lang`/`doc_version`/`page_count`/`low_text`, and a
  `vendor-manual` requires all seven. 9.1 asks for "not applicable" rather than an
  invented value, and a `None` on a manual would be exactly such an invention.
- An `authored-triage` record is pinned to `source_id == "authored/triage"` and
  `hardware_applicability.status == "assumed"` (CONTRACTS §1).
- `hardware_applicability` is a small record of `(status, device, revision)` — the shape
  of a `rig.yaml` `source_applicability` entry, which is where it comes from.
- `Passage` has no `kind` field, so the pageless rule keys on
  `source_id == AUTHORED_SOURCE_ID`: no `section_number`, `page_start` or `page_end`,
  and `entry_location` required. A paged passage is the mirror image — pages required,
  `entry_location` refused — because CONTRACTS §2 makes them alternatives ("absent on a
  `vendor-manual`, which has a page instead"). If a second pageless kind ever appears,
  this is the line to revisit.
- `ingested_at` is an ISO-8601 UTC **string**, not a `datetime`: it goes straight into
  `sources.json` and the shard meta, and a string needs no encoder.

`version.py` holds `INGESTION_VERSION`, bumped by hand whenever anything from extraction
through chunking could change a chunk's text or metadata. It is a shard cache-key
component: without a bump, a fixed ingestion bug reaches nothing, because no PDF byte
changed and every shard is reused.

## The loader seam

`corpus/loader.py` is interfaces only — no behaviour and no validation, on purpose, so
there is no test task in front of it. `SourceLoader` is the protocol both stores
implement; `data/symptom-triage` supplies `TriageLoader` and it is not written here.
Everything downstream of `Region` is shared code, which is what makes requirement 12.2
structural rather than a set of `if kind ==` branches.

`Unit` carries `page_start` **and** `page_end` because a procedure that fits the chunk
cap may still span p11–p12, and 6.10 forbids splitting it.

## Discovery — `corpus/discover.py`

Stage 1. Reads directories and hashes bytes; opens no PDF. Two halves, one module:

**The filename grammar.** `FILENAME_PATTERN` is one anchored expression and
`SourceIdentity.filename` is its exact inverse, because `api/answer-engine` rebuilds the
name from a `SourceRecord`'s own fields (CONTRACTS §3a, §4e). Two details that look like
nits and are not:

- `doc_version` is stored **without** the leading `v`, so the inverse is
  `_v{doc_version}_` and never `_vv1.0_`.
- Digits are `[0-9]`, not `\d`. Python's `\d` matches Arabic-Indic and other scripts'
  digits, which would admit a name two other specs must rebuild byte for byte.
- `display_name` is mechanical title-casing of vendor + product: `akai_apc-key-25` →
  `Akai Apc Key 25`. Ugly on acronyms and deliberate — the version is never appended,
  because CONTRACTS §3 already shows `doc_version` inline on the citation.

A file whose suffix is not `.pdf` (case-insensitively) is skipped silently per 1.3;
`FOO.PDF` therefore reaches the grammar and is *rejected*, rather than vanishing. That is
the intended reading: silently skipping a mis-named PDF loses it with no report line.

**Store scanning.** `StoreScan.available` is the whole point of the type. An absent,
unreadable or not-a-directory store returns `available=False`, meaning its discovery set
is **unknown**, and `remove_absent_sources` removes nothing for it. Only an existing,
empty store yields an empty set and removes its shards. Without that split an unmounted
volume deletes every authored passage and reports success.

Other non-obvious rules here:

- Removal is keyed on the `store` recorded in `shards/<slug>.meta.json`, not on which
  scan is running, so 9.5's "never test a source of one kind against the other kind's
  store" holds by construction. A shard from a store this run did not scan at all is
  kept, same as an unavailable one.
- A shard goes with its `.sidecar.json` and its `audits/<slug>.json`.
- A **rejected** source is not in `source_ids`, so its shard is removed — otherwise an
  answer could cite a source the run refused to index.
- An unparseable shard meta is skipped, never deleted: it names no store and no source,
  so nothing can tell whether its shard is stale.
- `discover_stores()` is the run-level pass, and it exists for exactly one case:
  `authored_triage_notes_v1_en.pdf` is legal grammar and lands on the authored store's
  constant `authored/triage`. Neither store's own scan can see that, and the slug rule
  cannot either (both sides form `authored_triage`), so the collision is caught on
  `source_id` and rejected in both stores under 2.6.
- `fingerprint_changed()` is only the **fingerprint** component of the shard cache key.
  `index/build.py` owns the other three (`ingestion_version`, embedding model, dimension)
  at task 34/35; a fixed ingestion bug changes no PDF byte and must still re-ingest.

`data/symptom-triage` owns the authored store (`triage/` at the repo root) and supplies
its own `StoreScan`; tests here build one by hand to stand in for `TriageLoader`.

## `make bench`

`bench` guards on `manuals/*.pdf` (gitignored, so a fresh clone has none) and runs
`pytest -m bench`. Pytest exits 5 when no test matches the marker; the target treats
that as "no benchmark registered yet" and succeeds. Requirement 8.1 needs the real
PDFs, so CI cannot verify it.
