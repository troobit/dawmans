# Authoring a triage entry from forum threads

A procedure for any coding agent with web access. It turns what people report on forums
into a triage entry that is **grounded in the vendor manuals** — or it fails loudly and
you write nothing.

Nothing here needs new code in `dawmans`. The whole loop is the existing CLI plus one
lookup script. Read [`docs/agent-notes/triage-entry-grammar.md`](../agent-notes/triage-entry-grammar.md)
for how the format is parsed; the governing spec is [`specs/data/symptom-triage/`](../../specs/data/symptom-triage/).

## What this is, and what it is not

A forum thread is **not a source**. It is never fetched at answer time, never ingested,
never cited, and never stored in the repository. It is background reading that helps a
human decide *which documented control to suspect* — and the entry that results is the
studio owner's own writing, cited to the manuals, exactly as
[`specs/data/symptom-triage/requirements.md`](../../specs/data/symptom-triage/requirements.md)
§5 already describes.

That boundary is the spec's standing non-goal — *"a forum or community corpus… nothing
imports entries from the web"* — and this procedure does not weaken it. If you find
yourself wanting to paste thread text into an entry, stop: the entry states a **causal**
link the author is entitled to assert (2.5), and every **factual** claim about what a
control is, does, or is called must come from the manual passage the cause points at
(2.6).

## The loop

### 1. Pick a symptom that is not already covered

```
uv run dawmans coverage
ls triage/
```

Two entries declaring the same symptom in the same scope reject **both** (1.9). Extend
an existing entry rather than adding a near-duplicate.

### 2. Read around the symptom

Use your web search and fetch tools. Search the vendor's own forum, the subreddit for the
device or DAW, and the manufacturer's support pages. You are looking for one thing only:

> **which control, when in which state, produces this symptom** — and how often people
> report each one.

Frequency is what sets the cause order, and that order is load-bearing: it becomes the
`rank` that the answer engine emits and the browser surface shows (1.5). Note roughly how
many independent reports back each cause; you will not cite them, but you are ranking on
them.

Discard anything that is technique advice, anything about gear not in `rig.yaml`, and
anything you cannot tie to a named control.

### 3. Find the real manual sections

**Never write a section number from memory.** Look each one up:

```
make sections ARGS="direct monitor"        # search titles and passage text
make sections ARGS="--titles monitoring"   # titles only
make sections ARGS="--list"                # what is indexed at all
```

Output is paste-ready `fix:` syntax, copied from the committed index:

```
fix: focusrite/scarlett-solo-4g "Direct Monitor Button"
fix: ableton/live-12 §17.1 "Monitoring"
```

If a control appears nowhere, the cause **cannot be written**. The no-pointer allowance
(2.3) is narrow: it covers only a device that is in `rig.yaml` and has no ingested source
at all, and today no device qualifies.

### 4. Write the entry

One file per symptom in `triage/`, named for the symptom in kebab-case. Copy the shape of
an existing entry — [`triage/no-sound-from-track.md`](../../triage/no-sound-from-track.md)
is the fullest worked example.

```markdown
---
devices: [ableton/live-12]
---

# No sound from a track

also: the track is silent; I can't hear track 3

Work down the list in order.

## The Track Activator is off
check: the Track Activator switch at the bottom of the track is unlit
why: it sits next to the volume slider, so a mis-aimed click catches it
fix: ableton/live-12 §18.1 "The Live Mixer"

## Another track is soloed
check: a Solo switch is lit on some other track
fix: ableton/live-12 §18.6 "Soloing and Cueing"

## Otherwise
Check the Main track before assuming this track is at fault.
```

The rules that reject or flag an entry:

| Rule | What it requires |
|---|---|
| 1.1, 1.4 | Between **2 and 6** causes, most likely first. Seven is a rejection. |
| 1.2 | Every cause carries a statement (the `##` heading), one `check:`, and one `fix:`. |
| 4.1, 4.2 | `devices:` is mandatory and must use `rig.yaml` identities exactly. |
| 2.2 | Every pointer must resolve, or the **whole entry** is rejected at first ingest. |
| 2.6 | A control, parameter or value named in a cause must appear in the passage it points at. |
| 2.7 | A pointer may not target another authored entry. |

Two details that catch people out, both from the grammar note:

- `check:` and `why:` continue until a blank line, a heading, or another keyed line.
  `fix:`, `also:` and `undocumented:` end at their own line — a note written under a `fix:`
  is **not** swallowed into it.
- The final `##` section is treated as a closing statement if it carries neither `check:`
  nor `fix:`. A section missing both **in the middle** of the file is a cause, and rejects.

Write each `check:` as a single observation someone can make without interpreting anything
— "a Solo switch is lit on some other track", not "check your routing is sane".

### 5. Validate before committing

```
uv run dawmans ingest
uv run dawmans validate
```

`validate` re-resolves every pointer in the store and reports failures by symptom and
cause, in plain words (5.3, 5.4). It exits non-zero on a rejection **or** a term-check
miss (Decision 14). Fix what it names and run it again.

**Check `validate`'s exit code, not `ingest`'s.** A rejected entry is expected and
per-entry: `ingest` excludes it, reports the reason, ingests everything else and still
exits **0**, because one bad entry must not cost the author the other entries (5.2). Only
`validate` fails the run. An agent that checks `ingest` alone will conclude a broken entry
landed fine.

A rejection names the pointer and suggests the nearest real section:

```
triage/no-sound-from-track.md — "No sound from a track"
  rejected: cause 1 "The Track Activator is off" points at ableton/live-12 §99.99,
  which is not a section of that manual. Nearest: §19.9. Correct the pointer or drop
  the cause.
```

A `flagged:` line reading *"the final section … is read as a closing statement rather
than a cause"* appears for every entry that has an `## Otherwise` section. That is an
inventory line, not a problem (Decision 6) — the parser cannot distinguish an intended
closing statement from a cause that lost both its keys, so it says so every time.

A term-check miss usually means the cause named a control the pointed-at section does not
discuss — the pointer is aimed one section too high or too low. Re-run step 3.

### 6. Hand it over

Show the human the entry, what `validate` said, and which threads informed the cause
**order**. They review and commit; you do not commit an entry on their behalf.

## Provenance

Once committed, the entry carries no record of which thread suggested a cause — the
`fix:` pointers cite manuals, and nothing cites a forum. If that link is worth keeping,
put it in the commit message. There is deliberately no field for it: an entry is the
owner's, and a URL in the file would read as a citation the answer engine never made.

## Failure modes worth naming

- **A plausible cause nothing documents.** Common on forums, and it cannot be written.
  That is the grounding discipline working, not a gap in the tooling.
- **Ranking on thread volume rather than on this rig.** A cause that dominates a
  subreddit may be rare on four devices and one DAW. The rig is `rig.yaml`.
- **A confident wrong entry.** Nothing detects a causal claim that is simply false — the
  spec names this as its most serious risk. Visible provenance mitigates it; review is
  what actually catches it.
