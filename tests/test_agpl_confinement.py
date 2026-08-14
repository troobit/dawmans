"""PyMuPDF is confined to `dawmans/corpus/pdf/` — decision_log.md Decision 6.

Publishing a repository that imports PyMuPDF conveys a combined work that must carry
AGPL-3.0-or-later. Confining the import keeps that attached to the ingestion tool and
away from the process `api/answer-engine` runs. `pyproject.toml` states the same rule
as a ruff banned-api; this test is what makes `make test` catch it too, including the
import forms a linter reading one file at a time does not see.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "dawmans"
ALLOWED_DIR = PACKAGE_ROOT / "corpus" / "pdf"
BANNED_ROOTS = {"fitz", "pymupdf"}


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "import_module" and node.args and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str):
                    roots.add(value.split(".")[0])
    return roots


def test_pymupdf_is_imported_only_under_corpus_pdf() -> None:
    offenders = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if ALLOWED_DIR in path.parents:
            continue
        banned = _imported_roots(ast.parse(path.read_text(encoding="utf-8"))) & BANNED_ROOTS
        if banned:
            offenders.append(f"{path.relative_to(PACKAGE_ROOT.parent.parent)}: {sorted(banned)}")

    assert not offenders, (
        "PyMuPDF may only be imported under dawmans/corpus/pdf/ (AGPL, Decision 6): "
        + "; ".join(offenders)
    )
