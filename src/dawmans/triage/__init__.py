"""Authored symptom-triage tooling (specs/data/symptom-triage).

Only `terms` lives here so far — the 2.6 term extraction that
`dawmans.answer.ground` reuses. The loader, validator and ledger land
with that spec's own implementation. Nothing in this package may pull in
an ingest-only dependency: the answer engine imports it, and the
no-PyMuPDF import test walks it automatically.
"""
