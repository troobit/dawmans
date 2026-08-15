"""The `authored-triage` source: hand-written symptom-to-cause entries.

Owned by `specs/data/symptom-triage`. The entry model lives in `model`, the entry
grammar in `parse`, and the fix-pointer grammar in `pointers`.

Nothing in this package may pull in an ingest-only dependency: the answer engine
imports `terms`, and the no-PyMuPDF import test walks the package automatically.
"""
