# Design: Symptom Triage

**Domain:** `data` · **Capability:** symptom-triage · **Status:** draft

Implements [`requirements.md`](requirements.md) against [`CONTRACTS.md`](../../CONTRACTS.md)
(governing). Criteria are referenced by ID and not restated.

## Overview

A committed folder of hand-written Markdown entries — one file per symptom, YAML frontmatter for the
machine-readable fields — is loaded by a second `SourceLoader` behind the seam
[`data/manual-corpus`](../manual-corpus/design.md) already defines, and emitted as ordinary
`Passage` records. The load-bearing work is not the parsing: it is resolving each cause's fix
pointer into the ingested vendor corpus on every run, and deciding whether a pointer that does not
resolve is the author's mistake (reject, 2.2) or the manual moving underneath a working entry
(flag, 8.4).

---

## Architecture

### Dependencies on `data/manual-corpus`

That design is under review. Every specific this one rests on is named here, so a change there is
traceable to what it breaks.

| Depended-on specific | Used for | Consequence if it changes |
|---|---|---|
| `SourceLoader`, `Discovered`, `LoadResult`, `Region`, `Unit`, `UnitFlags` | `TriageLoader` is the second loader | this spec's whole emission path |
| chunker preserves `Region.units` order | 1.5 | cause ranking silently reordered |
| `Unit.atomic` + `repeat_on_split` | 3.3 split-between-causes, symptom repeated | 3.3 needs special-casing in the chunker |
| `UnitFlags.unbacked`, carried through untouched (its 12.6) | 2.4, 8.5 | the flag cannot reach `Citation` |
| `passage_id(source_id, text)` in `corpus/passage_id.py` | 3.9 | authored IDs diverge from manual IDs |
| `index/passages.jsonl` + `sources.json` as committed, readable artefacts | pointer resolution input | resolution needs a new read path |
| `manifest.corpus_revision` | store fingerprint (below) | drift re-checking loses its trigger |
| `rig.yaml` device ids and `source_applicability` | 4.2, 4.6, 3.8 | scope validation loses its vocabulary |
| stage ordering: **the authored load must run after every vendor shard has committed** | 2.1 — resolution reads vendor passages | pointers resolve against a stale corpus |
| per-`passage_id` vector reuse within the authored shard | 5.6 | every run re-embeds every entry |

The last two rows are requests on that design rather than uses of it, as is one more: its citation
header, `f"{display_name} — §{section_number} {section_title}\n{text}"`, must degrade to
`f"{display_name} — {section_title}"` when `section_number` is `None`, or every authored chunk is
embedded with the literal `§None` (3.4).

### The store on disk

`triage/` at the repository root, sibling to `manuals/` (1.6). It is **committed**: `.gitignore`
excludes `manuals/*.pdf`, not the folder itself, and needs no change. Discovery is a flat glob of
`triage/*.md` on every run, with no index file (1.6, 1.7). A non-`.md` file there is skipped **with**
a report line — the opposite of `manuals/`, where the skip is silent — because a `no-sound.txt` the
author expected to be ingested must not disappear quietly. Filenames carry no meaning: not identity
(1.8), not scope, not ordering.

### Entry grammar

```markdown
triage/no-sound-from-track.md

---
devices: [ableton/live-12]
---

# No sound from a track

also: track is silent; can't hear track 3

## The Track Activator is off
check: the track's number is dimmed in the mixer
fix: ableton/live-12 §16.4

## Another track is soloed
check: a blue S is lit on any track
why: one glance, and it is the commonest cause after the activator
fix: ableton/live-12 §16.5

## Direct monitoring is on at the interface
check: the DIRECT MONITOR button is lit
fix: focusrite/scarlett-solo-4g "Direct Monitor Button"

## The buffer size is too high for tracking
check: latency is audible when playing in, but the recording lines up on playback
undocumented: focusrite/scarlett-solo-4g

## Otherwise
Check the master track before assuming this track is at fault.
```

| Construct | Rule |
|---|---|
| frontmatter | required, `---`-fenced YAML at byte 0. `devices` required and non-empty (4.1). Any other key is flagged, not fatal |
| device identity | `<vendor>/<product>`, optionally `@<revision>` (4.6) — `akai/apc-key-25@mk2`, `ableton/live-12@suite` |
| symptom | the single `#` H1. Zero or two H1s is a rejection |
| `also:` | 0+ lines between the H1 and the first H2; `;`-separated alternative phrasings (1.3) |
| cause | each `##` H2. Document order **is** the likelihood ranking (1.1); nothing re-orders it (1.5) |
| `check:` | exactly one per cause (1.2) |
| fix | one or more `fix:` lines, **or** exactly one `undocumented:` line naming a device (2.3) |
| `why:`, loose prose, `###`+ | optional, anywhere in a cause; retained verbatim in the passage text (1.3) |
| closing statement | the final H2 carrying neither `check:` nor a fix line. Not a cause; excluded from the 2–6 count (1.4) |

A keyed line is matched case-insensitively after stripping leading `-`, `*`, `>`, `#` and `**`, so
`**Check:**`, `- check :` and `CHECK:` are one line; a value continues until a blank line, a heading
or another keyed line. Position, not vocabulary, identifies the closing statement, so there is no
reserved title to remember. The cost: a final section meant as a cause that lost *both* its check
and its fix reads as a note. Losing only the fix — the likelier slip — still rejects under 1.2.

Requirement 7.3's elimination step needs no construct of its own: "the distortion is deliberate" is
an ordinary cause whose check names the distortion devices in the chain and whose fix points at the
Live manual's section for one of them. It counts toward the 2–6 limit.

### Fix pointers

```
fix: <source_id> §<section-number>              ableton/live-12 §16.4
fix: <source_id> "<section title>"              akai/apc-key-25 "Shift Functions"
fix: <source_id> §<section-number> "<title>"    title corroborates, does not select
```

The title form is not a convenience: the APC Key 25 guide has no numbering at all
(`manual-corpus` 6.4), so a number-only syntax could not point into a third of the corpus. **No page
form exists** — 8.1 forbids page-only addressing, and admitting a page even as a qualifier would
reintroduce the breakage 8.3 exists to avoid.

Resolution runs against `(source_id, section_number) → passages` and
`(source_id, normalised title) → passages` maps built in one pass over `index/passages.jsonl`. The
source token must name an indexed `vendor-manual`; an `authored-triage` target is a rejection (2.7)
and an unknown source an unresolved pointer. A number matches exactly after `§` is stripped. A title
matches on the normalised form (casefold, collapse whitespace, strip a leading section number and
trailing punctuation), else on a unique prefix; two matches is unresolved with the candidates named,
never an arbitrary pick. Where both are given the number selects and the title corroborates — a
disagreement is a **flag**, the cheapest renumbering detector available and free to the author.

**A pointer addresses a section, and resolves to the ordered set of passages that section produced.**
Where the section split into *k* chunks it resolves to all *k*, the cause carries all of them, and
the engine cites whichever it retrieves. Nothing here picks one chunk: which chunk holds the sentence
about the control is an artefact of the 350-word cap and changes under a re-chunk.

### The term check (2.6)

The checked span is the **cause statement plus its `check:` value** — nothing else. `why:`, loose
prose and the closing statement are reasoning about ordering and elimination, which 2.5 and
CONTRACTS §8 entitle the author to write unsupported. Two term classes are extracted: runs of
consecutive Capitalised or ALL-CAPS tokens (`Track Activator`, `Audio To`, `DIRECT MONITOR`), a
single-token run at a sentence start being dropped unless the token also appears capitalised
elsewhere in the entry; and numeric literals with an optional unit (`0 dB`, `-12 dB`, `44.1 kHz`).
Terms equal to a declared device's id, product token or display name are discarded, as are tokens
under three characters. Containment is a casefolded, whitespace-collapsed substring test over the
resolution set's concatenated text, numerals matched at word boundaries so `0` does not satisfy `10`.

A miss is a **flag naming the term and the section**, and does **not** set `unbacked`: the pointer
resolved, and what failed is a heuristic over an author's prose whose false-positive rate cannot be
bounded. 2.4 and 8.5 remain the only two producers of `unbacked`.

### Passage emission

**One passage per entry** (3.3), splitting only when the entry exceeds the chunker's 350-word cap.
An entry of five causes runs to roughly 150 words, so the split path is rare but real. Mapping onto
the corpus loader's types, which gives 3.3 for free:

| Entry part | Emitted as |
|---|---|
| symptom + `also:` phrasings | `Unit(repeat_on_split=True)` — first, so a split passage never carries a cause without its symptom |
| each cause: statement, `check:`, `why:`, prose | one `Unit(atomic=True)` — never split within a cause |
| closing statement | one `Unit(atomic=True)` |
| — | `Region(section_number=None, section_title=<symptom>, page_start=None, page_end=None)` (3.4, 3.5) |
| a cause under 2.3, or with a drifted pointer | `UnitFlags.unbacked` on that cause's unit (2.4, 8.5) |

Alternative phrasings sit in `Passage.text` rather than in metadata precisely so BM25 sees them;
they are the only mitigation the requirements offer for a question phrased unlike the entry. Fix
pointers do **not**: CONTRACTS §2 fixes the field set, so per-cause structure travels in a sidecar
(below), which also keeps a pointer retarget from changing the passage's identity.

Because the flag is per-unit, a split entry marks only the passage carrying the unbacked cause and
an unsplit entry marks the whole thing — the over-marking 2.4 chose, no worse than it mandates, and
the coverage report names the cause in both cases (6.4).

### Identity

`source_id` is the constant **`authored/triage`**, and `passage_id` is
`corpus.passage_id("authored/triage", passage_text)` unchanged — the same digest over the same
canonical form, so authored and manual IDs behave identically under re-ingestion.

> **Contract defect to reconcile.** CONTRACTS §1 and 3.1 say the authored `source_id` is "derived
> from the source's own content". A digest over the store's content cannot serve: it changes on
> every edit to any entry, and since `passage_id` is prefixed with `source_id`, it would orphan
> **every** citation in retained history on every edit — the opposite of 3.9 and 8.2. The clause's
> operative half is "independent of any filename", which a declared constant satisfies. The
> constant should be written into CONTRACTS §1 rather than the digest reading being implemented.

What is hashed is the passage's rendered text: the symptom, the alternative phrasings, and the
causes' statements, checks, why-notes and prose, in order, in a canonical rendering. Excluded, each
deliberately:

| Excluded | Because |
|---|---|
| frontmatter | a device added to scope must not orphan the entry's history |
| fix pointers | retargeting after a manual renumbers is the frequent maintenance event, and must not orphan history — the argument `manual-corpus` uses for excluding `section_number` |
| the file's name and path | 1.8 |
| authoring cosmetics | marker style, blank lines, CRLF, frontmatter key order; the canonical rendering strips them before hashing |

**Editing one cause changes the whole entry's ID**, because the entry is the passage. Other entries
are untouched — that is the point of one file per symptom. A citation held in retained UI history
then fails to resolve, and must render as no-longer-available rather than resolving to the edited
text: the author edited the entry because it was wrong, and silently reattaching the old citation to
the corrected text is the one outcome worse than a dead link.

### Device scope

Frontmatter `devices` → validated → published per `passage_id` in the sidecar → consumed by
`api/answer-engine` 5.12–5.13 as the per-passage predicate. This spec filters nothing itself (4.3).

| Declared device | Result |
|---|---|
| in `rig.yaml` and indexed as a `vendor-manual` | scoped normally |
| in `rig.yaml`, no indexed source (`focusrite/scarlett-solo`) | scoped, and reported as applying to an undocumented device (4.4) |
| in neither | flag naming the declaration (4.5); the entry still ingests |
| `@revision` differing from the rig device's `revision` | flag (4.6). Compared casefolded with non-alphanumerics stripped, either-contains — `rig.yaml` holds free text such as `12 Standard` |

The Scarlett Solo stays reachable with no work here: `api/answer-engine` 5.12 puts every
owned-but-undocumented rig device into the turn's device scope unconditionally, so an entry
declaring `focusrite/scarlett-solo` survives 5.13's filter although no Focusrite source can be
selected. That is why 2.3's allowance and 4.4's report are sufficient, and no pseudo-source is
registered for undocumented gear.

`hardware_applicability` (3.8) is source-level and cannot vary per entry. It is read from
`rig.yaml`'s existing `source_applicability` map, keyed `authored/triage`; absent means `assumed`,
which is the standing state. No new configuration file.

### Reject versus flag, with no memory

2.2 rejects a pointer that never worked; 8.4 flags one that stopped working. Nothing in the entry
distinguishes them, and `index/` is derived and deleted by a rebuild, so it cannot be the memory.

The memory is **`triage/.pointer-ledger.json`** — machine-written, committed, never hand-edited,
one row per `(entry_key, pointer)` recording that the pointer resolved and to what.

- `entry_key` = sha256 over the normalised symptom and the sorted device ids. It survives a cause
  edit, a file rename and a re-chunk, which `passage_id` does not. The same key detects the 1.9
  duplicate.
- A pointer with **no ledger row** has never been verified by anyone ⇒ unresolved is a **rejection**
  (2.2). This covers a new cause added to an old entry: the entry is known, the pointer is not.
- A pointer **with** a ledger row ⇒ unresolved is a **flag** plus `unbacked` on its cause (8.4, 8.5),
  the entry stays ingested, and the row is retained so a later resolution clears the flag (8.5).
- Rows for entries no longer in the store are pruned on ingest.
- Deleting the file is safe and re-arms 2.2 for everything — the honest degradation, since the file
  is the only claim that a pointer once worked.

`dawmans validate` (5.4) reads the ledger and never writes it, so checking work before committing to
it cannot promote a broken pointer to "previously fine".

### Discovery, fingerprint and the run budget

The store's `Discovered.fingerprint` is sha256 over the sorted `(relative path, file digest)` pairs
**concatenated with `manifest.corpus_revision`**. The corpus revision belongs in it because the
authored source's validity is a function of the manuals as well as its own text: without it, an
unchanged store would be skipped by the corpus's change detection and 2.1's per-run re-check would
never run after a manual changed.

5.6's five seconds: parsing, resolving and term-checking 200 entries is a single pass over ~1,000
vendor passages plus ~1,200 substring tests — comfortably under a second. Embedding is what could
blow the budget, so the authored shard reuses vectors by `passage_id` and re-embeds only entries
whose text changed, typically one. A **cold** run additionally pays the 7.2 s model load that
`manual-corpus` measures; 5.6 is met warm, and the authoring loop the criterion is really about is
`dawmans validate`, which embeds nothing at all.

### Coverage without a taxonomy

There is no enumerable universe of symptoms, so the report has no denominator and states **no
percentage**. It is an inventory of what exists plus the one gap that *is* enumerable — the rig side
(6.3). Rows: every entry with symptom, scope, cause count and pointer health (6.1); every rejection
and flag with its reason (6.2); rig devices no entry mentions (6.3); causes without a pointer and
the device each names (6.4); entries flagged for drift with the source that changed (8.6); entries
scoped only to a device that has left the rig (8.7).

`dawmans coverage` renders it to stdout and writes it into the sidecar's report block (6.5), which
travels alongside the corpus inventory to the engine and picker (6.6) by the same channel
`api/answer-engine` 9.6 already relays.

### Module placement

Inside `dawmans/triage/`, the package `manual-corpus` reserves for this spec.

```
src/dawmans/triage/
  loader.py     TriageLoader — the SourceLoader for kind authored-triage
  parse.py      entry file → Entry; canonical rendering
  pointers.py   pointer grammar, the section index, resolution, the ledger
  terms.py      2.6 extraction and containment
  scope.py      device declarations against rig.yaml; the sidecar
  coverage.py   the §6 report
```

`dawmans/cli.py` gains `coverage`; its existing `validate` gains the entry store.

---

## Components and Interfaces

```python
class TriageLoader:                       # satisfies corpus SourceLoader
    def __init__(self, store: Path, corpus: CorpusView, rig: Rig, ledger: Ledger): ...
    def discover(self) -> Iterable[Discovered]: ...   # 0 or 1 — the store is one source
    def load(self, d: Discovered) -> LoadResult: ...  # regions in file-name order, sidecar in .report

@dataclass(frozen=True)
class Entry:
    symptom: str; phrasings: list[str]
    devices: list[DeviceRef]              # id + optional revision
    causes: list[Cause]                   # declared order, never sorted
    closing: str | None
    source_file: Path
    line: int                             # the H1's line — the CONTRACTS §3 open-at-source target

@dataclass(frozen=True)
class Cause:
    statement: str; check: str; notes: str
    fixes: list[Pointer]                  # empty ⇔ undocumented_device is set (2.3)
    undocumented_device: str | None

def resolve(p: Pointer, idx: SectionIndex) -> list[str] | Unresolved   # passage_ids, in section order
def terms(cause: Cause) -> list[str]                                   # 2.6 extraction
```

`CorpusView` is a read-only wrapper over `index/passages.jsonl` and `sources.json`; the loader never
touches vendor shards or PDFs (5.7, `manual-corpus` 12.4). `load` never rewrites an entry file; the
ledger is its only mutable output, and only `ingest` writes it.

---

## Data Models

### The sidecar — `index/reports/authored-triage.json`

Everything `Passage` cannot carry, keyed by `passage_id`. Written by the corpus from
`LoadResult.report`, and **read by `api/answer-engine`**, which promotes that report channel from
diagnostic output to a contract — the second request on `manual-corpus` and the one most likely to
be missed.

```json
{"passages": [
  {"passage_id": "authored/triage#9f3c1a…",
   "entry_key": "a41e…",
   "symptom": "No sound from a track",
   "devices": [{"id": "ableton/live-12", "revision": null}],
   "source_file": "triage/no-sound-from-track.md", "line": 7,
   "causes": [
     {"statement": "The Track Activator is off",
      "check": "the track's number is dimmed in the mixer",
      "fix": [{"source_id": "ableton/live-12", "section": "16.4",
               "passage_ids": ["ableton/live-12#4b12…"]}],
      "undocumented_device": null, "flags": []},
     {"statement": "Direct monitoring is on at the interface",
      "check": "the DIRECT MONITOR switch is pushed in",
      "fix": [], "undocumented_device": "focusrite/scarlett-solo",
      "flags": ["unbacked-cause"]}]}],
 "report": {"entries": 5, "rejected": 0, "flagged": 1,
            "pointers": {"checked": 14, "resolved": 13, "unresolved": 0, "without_pointer": 1}}}
```

`devices` here is the input to the 5.13 predicate; `causes` in order is the input to
`api/answer-engine` 7.2 and 7.6, which need the ranked list with its checks and fix citations, not
just the passage text. The pointer counts are 2.8.

### The ledger — `triage/.pointer-ledger.json`

```json
{"a41e…": {"ableton/live-12 §16.4": {"resolved_at": "2026-08-14T10:00:00Z",
                                      "passage_ids": ["ableton/live-12#4b12…"]}}}
```

---

## Error Handling

Per **entry**, not per source: a rejection excludes one entry, the rest ingest, the run succeeds
(5.2). The whole source is rejected as `authored-invalid` (`manual-corpus` 12.6) only when no entry
survives, since a source with no passages is not a source.

| Rejection | Raised when | Criterion |
|---|---|---|
| `frontmatter-missing` / `-malformed` | no `---` fence at byte 0, or YAML that will not parse | 4.1 |
| `no-devices` | `devices` absent or empty | 4.1 |
| `no-symptom` | zero or two H1s | 1.1 |
| `too-few-causes` / `too-many-causes` | outside 2–6 | 1.1, 1.4 |
| `cause-missing-check` / `cause-missing-fix` | a cause lacking one, and not the closing statement | 1.2 |
| `pointer-unresolved` | no ledger row and it does not resolve | 2.2 |
| `pointer-authored-target` | the pointer names `authored/triage` | 2.7 |
| `undocumented-claim-invalid` | `undocumented:` names a device absent from the rig, or one that *is* indexed | 2.3 |
| `duplicate-symptom` | two entries share an `entry_key` — **both** rejected | 1.9 |

Flags, all leaving the entry ingested: `pointer-drifted` (8.4, sets `unbacked`), `unbacked-cause`
(2.3/2.4, sets `unbacked`), `term-not-in-passage` (2.6), `unknown-device` (4.5), `revision-mismatch`
(4.6), `title-number-disagreement`, `undocumented-device-scope` (4.4), `orphaned-scope` (8.7),
`unknown-frontmatter-key`.

Messages name the file, the symptom and the cause, and say what to change (5.3):

```
triage/no-sound-from-track.md — "No sound from a track"
  rejected: cause 2 "Another track is soloed" points at ableton/live-12 §16.5,
  which is not a section of that manual. Nearest: §16.4 "The Mixer",
  §16.7 "Mixing with Groups". Correct the pointer or drop the cause.

triage/kick-distorting.md — "A track is distorting"
  flagged: cause 1 says "Drum Buss" but ableton/live-12 §24.2 "Saturator"
  does not contain that term. Point at the section that documents it.
```

Nearest-section suggestions come from the same normalised title index, by edit distance, and are
what turn a rejection into something actionable at the desk rather than a lookup exercise.

---

## Testing Strategy

`pytest` + `hypothesis`, per `manual-corpus`.

### Genuine invariants (property-based)

Generators produce the `Entry` **model** and render it to Markdown, rather than generating Markdown
text — the reverse direction cannot state what the expected parse is.

| Property | Guarantee | Criteria |
|---|---|---|
| Order preservation | for any entry, the emitted causes are the declared causes, in order, unmerged and undeduplicated | 1.5 |
| Total parsing | for **any** byte string, the parser returns an `Entry` or a rejection naming the file; it never raises and never returns a half-built entry | 5.2 |
| Cosmetic invariance of `passage_id` | perturbing marker style, blank lines, key casing, line endings, frontmatter key order and pointer targets leaves the ID unchanged | 3.9, 8.2 |
| `passage_id` sensitivity | any change to symptom, phrasings, cause statement, check or notes changes the ID | 3.9 |
| Canonical idempotence | `render(parse(render(parse(f)))) == render(parse(f))` | 3.9 |
| Split invariants | for an over-cap entry, every emitted passage contains the symptom and no cause spans two passages | 3.3 |
| `unbacked` monotonicity | every passage carrying a 2.3 or 8.4 cause is flagged; no passage is flagged without one | 2.4, 8.5 |
| Term-check soundness | a cause whose terms are all lifted verbatim from the pointed-at passage never raises `term-not-in-passage` | 2.6 |
| Reject/flag state machine | over random sequences of (ingest, edit an entry, edit a manual, remove a manual, restore it), a pointer that resolved at least once is never again a rejection, only a flag — and resolving again clears it | 2.2, 8.4, 8.5 |

The last is the highest-value entry: the reject/flag rule is a function of history, only wrong after
a particular sequence of runs, and no example test reaches those sequences. Term-check soundness is
stated in one direction only, deliberately — recall is a heuristic, not an invariant, and asserting
it would pin the extractor's false-negative rate as if it were a contract.

**Not** properties, and written as examples: that `§16.4` and `"Shift Functions"` parse; that
`**Check:**` is recognised; that a duplicate rejects both entries; the five starter entries.

### Fixtures

| Fixture | Asserts |
|---|---|
| `triage/*.md`, the five starter entries (7.2–7.6) | product content that doubles as the grammar's worked examples; every fix cites a vendor passage except the Scarlett cause (7.8) |
| `live_sections.json` — section numbers, titles and text slices for the ~15 sections the starter set points at, extracted once from the real index and committed | pointer resolution and the term check run in CI with `manuals/` absent, exactly as the corpus's extraction snapshots do |
| `apc_sections.json` — unnumbered regions | the title form resolves where no section number exists |
| `split_section.json` — one section chunked into three | a pointer resolves to all three, and the term check sees their concatenation |
| malformed entries, one per rejection reason | message names file, symptom and cause; the other entries in the same run still ingest |
| `drift/` — the same section with edited text, plus a seeded ledger | first run rejects with no ledger row; seeded run flags and sets `unbacked`; restoring the text clears it |

7.7 needs the real manuals and a built index, so it is a `make bench`-style integration target that
skips when `index/` is absent — the same honest limitation `manual-corpus` accepts for its 8.1.
