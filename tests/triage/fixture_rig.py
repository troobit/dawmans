"""A fixture rig inventory and corpus, for the scope tests.

`rig.yaml`, its concrete record and the applicability mapping all belong to
`data/manual-corpus`. This is the minimum `scope.validate_scope` reads, and it is
a fixture rather than the real inventory because two rows of design 'Device
scope' have **no live instance**: today every rig device is documented, so 4.4's
row and the all-unrecognised rejection can only be exercised against gear that
does not exist. A fixture also keeps the tests from re-failing every time a
manual is added.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureRigDevice:
    """One `rig.yaml` device.

    `id` and `revision` are the two fields `scope.RigDevice` reads.
    `display_name` is read by nothing in `scope`: it belongs to the rig reports
    and to the term check, which discards a term naming the device the owner
    holds.
    """

    id: str
    revision: str | None = None
    display_name: str | None = None


RIG = (
    FixtureRigDevice("ableton/live-12", "12 Standard", "Ableton Live 12"),
    FixtureRigDevice("akai/apc-key-25", "mk2", "APC Key 25"),
    FixtureRigDevice("alesis/nitro-max", None, "Nitro Max"),
    FixtureRigDevice("focusrite/scarlett-solo", "4th-gen", "Scarlett Solo"),
    FixtureRigDevice("elektron/digitakt", "mk1", "Digitakt"),
)
"""The four real devices plus one owned-but-undocumented device (4.4's row)."""

INDEXED = frozenset(
    {
        "ableton/live-12",
        "akai/apc-key-25",
        "alesis/nitro-max",
        "focusrite/scarlett-solo-4g",
        "focusrite/scarlett-solo",
        "roland/tr-8s",
    }
)
"""Indexed vendor-manual source ids together with the device ids they document.

`focusrite/scarlett-solo-4g` is the source, `focusrite/scarlett-solo` the device
it declares under `source_applicability` — both are recognised identities
(Decision 8). `roland/tr-8s` is documented but absent from the rig: the third
row of the design's table, which scopes with no flag. `elektron/digitakt` is
deliberately missing, so it is in the rig and undocumented.
"""
