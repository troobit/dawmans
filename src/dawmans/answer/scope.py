"""Device scope derivation (5.12) and the passage predicate (5.13).

The scope is derived over source kind, because the two kinds carry
applicability differently: a vendor manual declares its device at the source
level, an authored entry declares its devices per passage in the sidecar,
and the authored source itself contributes nothing — CONTRACTS §1 fixes its
source-level applicability at `assumed` with no device, so reading one off
it would yield None and poison the set.

The predicate is a filter, never a ranking input. Device-match closeness is
not computed anywhere: 5.13 permits it as a ranking signal only, and there
is no evaluation set to tune it with, so it stays unbuilt.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from dawmans.answer.envelope import VENDOR_MANUAL
from dawmans.answer.view import CorpusView


def _gap_devices(gaps: Mapping[str, Any]) -> set[str]:
    # The owned-but-undocumented report is empty today and the union is
    # still computed (5.12): a device enters it the day one is declared in
    # the rig ahead of its manual, and omitting the term would silently
    # filter out the entries written for exactly that gap.
    return {
        member if isinstance(member, str) else member["device"]
        for member in gaps["owned_but_undocumented"]
    }


def device_scope(view: CorpusView, selected_source_ids: Iterable[str]) -> frozenset[str]:
    """The devices a turn may draw device-declaring passages for."""
    selected = [view.sources_by_id[source_id] for source_id in selected_source_ids]
    records = [record for record in selected if record["kind"] == VENDOR_MANUAL]
    if not records:
        # No vendor manual selected — an ordinary triage-only diagnostic
        # scope. Scoping to the gaps alone would filter out every entry
        # naming a documented device, so the scope widens to every indexed
        # vendor-manual device: the widest set the engine can name from
        # sources.json and gaps.json alone, without ever reading rig.yaml.
        records = [record for record in view.sources if record["kind"] == VENDOR_MANUAL]
    return frozenset(
        {record["hardware_applicability"]["device"] for record in records}
        | _gap_devices(view.gaps)
    )


def in_device_scope(view: CorpusView, passage_id: str, scope: frozenset[str]) -> bool:
    """5.13: False excludes the passage from the turn entirely.

    A passage with no sidecar entry — every vendor passage, and an authored
    one declaring nothing — declares no devices and is scoped by its source
    alone (5.1).
    """
    entry = view.sidecar.get(passage_id)
    if entry is None:
        return True
    declared = {member["id"] for member in entry["devices"]}
    if not declared:
        return True
    return not declared.isdisjoint(scope)
