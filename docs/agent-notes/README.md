# Agent notes

Implementation notes that preserve knowledge across sessions — how modules work
(architecture, data flow, key abstractions), non-obvious behaviour and gotchas,
why approaches were chosen or rejected, and setup details the code doesn't show.

Conventions:

- One file per topic or module (`auth.md`, `api-layer.md`) — not per date or task.
- Read the relevant note before changing a module; update it after the work.
- Keep notes factual and concise; update existing notes rather than adding duplicates.

Repo-wide gotcha, learned on a merge: `tests/` carries no `__init__.py`, so pytest
imports test modules by bare basename and **every test file in the tree needs a unique
name**. Two specs each landed a `test_scope.py` on their own branch and the merge failed
to collect; the triage one is now `test_device_scope.py`. Name a test file after what it
tests, not after the module — `test_<module>.py` is what collides.
