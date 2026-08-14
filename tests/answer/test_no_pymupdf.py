"""Every served module must import with PyMuPDF poisoned.

The AGPL confinement of PyMuPDF to dawmans/corpus/pdf/ is only load-bearing if
the served process cannot reach it. A dev environment with both dependency
groups installed would hide an accidental `from dawmans.corpus.pdf import ...`,
so the import runs in a subprocess whose meta_path raises on `fitz` (and on
`pymupdf`, the same library's current import name).
"""

import subprocess
import sys

POISONED_IMPORT = """
import sys

class _PyMuPDFPoison:
    def find_spec(self, name, path=None, target=None):
        root = name.partition(".")[0]
        if root in ("fitz", "pymupdf"):
            raise ImportError(f"{name}: PyMuPDF must not be reachable from the served process")
        return None

sys.meta_path.insert(0, _PyMuPDFPoison())

import importlib
import pkgutil

import dawmans.answer

names = ["dawmans.answer"]
names += [m.name for m in pkgutil.walk_packages(dawmans.answer.__path__, "dawmans.answer.")]
try:
    triage = importlib.import_module("dawmans.triage")
except ModuleNotFoundError:
    pass  # data/symptom-triage has not landed dawmans/triage/ yet
else:
    names.append("dawmans.triage")
    names += [m.name for m in pkgutil.walk_packages(triage.__path__, "dawmans.triage.")]

for name in names:
    importlib.import_module(name)

print(len(names))
"""


def test_served_modules_import_with_pymupdf_poisoned():
    proc = subprocess.run(
        [sys.executable, "-c", POISONED_IMPORT],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    # dawmans.answer alone is 22 modules; a collapse to a handful means the
    # walk silently stopped importing, not that the confinement holds.
    assert int(proc.stdout) >= 22
