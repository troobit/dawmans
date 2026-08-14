# Specs Overview: DAWMans

**Generated index.** Regenerated from the folders under `specs/`, never hand-merged — see
[`PROCESS.md`](PROCESS.md) §9. On a merge conflict, regenerate rather than resolve. Everything
below is derived from the files actually present; nothing is anticipated.

**Generated:** 2026-08-14 · **Specs:** 4 · **Anchored acceptance criteria:** 398

---

## What DAWMans is

DAWMans is a localhost webapp that answers home-studio questions **strictly from the user's own
sources** — the vendor manuals for their gear plus an authored symptom-triage source they write
themselves — with every factual claim cited to a section and a page, and with NotebookLM-style
per-source scoping so the user chooses which sources may ground a given answer. It is built for one
person, on one machine, glancing at a second screen mid-session: the rig is **Ableton Live 12
Standard, an Akai APC Key 25 mk2, a Focusrite Scarlett Solo and an Alesis Nitro Max, on macOS**. It
answers from the manual corpus only; session awareness sits behind a defined but unbuilt
`StateSource` seam (DECISIONS Decision 4, refined by Decision 8).

## Governing documents

| Document | Standing |
|---|---|
| [`PROCESS.md`](PROCESS.md) | The process source of truth: how specs are written, gated, and turned into code. Kept as shipped by the template. |
| [`CONTRACTS.md`](CONTRACTS.md) | **Governing** for anything crossing a spec boundary — `SourceRecord`, `Passage`, `Citation`, `AnswerEnvelope`, the source kinds, the closed outcome taxonomy, the composed latency budget. Where a spec and CONTRACTS disagree, **CONTRACTS wins and the spec is the defect**. A spec may not invent a field on a shared record nor silently drop one. |
| [`DECISIONS.md`](DECISIONS.md) | The cross-cutting meta log — nine ADRs shaping the project as a whole. It is a synthesis: per-spec `decision_log.md` files remain **authoritative for detail**, and where the two disagree the per-spec log wins. |
| `OVERVIEW.md` (this file) | Generated index. Regenerate; do not hand-merge. |

## Domains

Four domains, with `ops` pruned (DECISIONS Decision 1). The set is closed — adding to it is an
amendment to that decision, not an ad-hoc `mkdir`.

| Domain | Owns | Specs |
|---|---|---|
| `platform` | App shell, build, packaging, **provider key configuration** | **none — see the open gap below** |
| `data` | Manual ingestion, chunking, the searchable corpus | 2 |
| `api` | Local HTTP backend, outbound LLM provider integrations, future Ableton state sources | 1 |
| `ui` | The browser surface | 1 |

> **Open gap — `platform` has no spec.** Decision 1 assigns provider key configuration to
> `platform`, but no `specs/platform/` folder exists. That work is currently described only from
> the two sides that consume it: `api/answer-engine` §6 (provider abstraction and credential
> handling) and `ui/ask-and-source-picker` §10 (the configuration surface, by provider kind).
> Nothing owns the shell, the build, or where a key is actually stored on the machine.

## Specs

All four are at **requirements complete, design not started**.

| Path | Domain | Capability | What it delivers | Phase | Criteria |
|---|---|---|---|---|---|
| [`data/manual-corpus/`](data/manual-corpus/requirements.md) | `data` | manual-corpus | Ingestion only: turns a folder of vendor PDFs and the authored triage source into a queryable, citable corpus — discovery, extraction fidelity, English selection, glyph repair, section-aware chunking with citation metadata, index build, inventory, and the rig-versus-corpus applicability report. | requirements ✅ · design ⬜ | 78 |
| [`data/symptom-triage/`](data/symptom-triage/requirements.md) | `data` | symptom-triage | The `authored-triage` source kind: symptom-to-cause entries the studio owner writes, each with ranked candidate causes, an observable check per cause, and a fix pointer into a vendor manual — plus the grounding rules, authoring loop, coverage reporting, starter set and drift handling. | requirements ✅ · design ⬜ | 60 |
| [`api/answer-engine/`](api/answer-engine/requirements.md) | `api` | answer-engine | The middle layer: retrieval over ingested chunks, grounding and honest refusal, citation assembly, source scoping, the pluggable provider abstraction and credential handling, the `StateSource` seam, and the localhost-only HTTP contract. Speed is the headline property. | requirements ✅ · design ⬜ | 109 |
| [`ui/ask-and-source-picker/`](ui/ask-and-source-picker/requirements.md) | `ui` | ask-and-source-picker | The browser surface: the ask input and its one-key starters, the source picker and the corpus gaps it exposes, answer and narrowing rendering, citation inspection and open-at-page, waiting and error states across the whole outcome taxonomy, provider configuration, history, legibility and accessibility. | requirements ✅ · design ⬜ | 151 |

Criterion counts are the `<a name=` anchors in each `requirements.md`.

---

## Per-spec detail

### `specs/data/manual-corpus/`

- **Files present:** `requirements.md` only.
- **Missing:** `design.md`, `tasks.md`, `decision_log.md`.
- 12 requirement sections, 78 anchored criteria. Owns `SourceRecord` and `Passage` from
  [`CONTRACTS.md`](CONTRACTS.md) §1–§2. Reference corpus: roughly 1068 pages across three manuals.
- Explicit non-goals include OCR, image understanding, non-English content, automatic manual
  acquisition, and inferring hardware applicability from a document's contents.

### `specs/data/symptom-triage/`

- **Files present:** `requirements.md` only.
- **Missing:** `design.md`, `tasks.md`, `decision_log.md`.
- 8 requirement sections, 60 anchored criteria. Header declares status *draft*.
- Exists because the manuals cannot answer diagnostic questions: "gain staging" appears **zero**
  times in the 1009-page Live 12 manual and "troubleshoot" appears twice (DECISIONS Decision 7).
  §7 specifies a five-symptom starter set as the acceptance test for the source.

### `specs/api/answer-engine/`

- **Files present:** `requirements.md` only.
- **Missing:** `design.md`, `tasks.md`, `decision_log.md`.
- 10 requirement sections, 109 anchored criteria. Header declares status *draft*.
- Produces `Citation` and `AnswerEnvelope` ([`CONTRACTS.md`](CONTRACTS.md) §3–§4) and may emit only
  the outcomes in §6 of that file. Must define `StateSource` while shipping a null implementation
  (Decision 4).

### `specs/ui/ask-and-source-picker/`

- **Files present:** `requirements.md` only.
- **Missing:** `design.md`, `tasks.md`, `decision_log.md`.
- 13 requirement sections, 151 anchored criteria — **126 behavioural [B]** and **25 target-and-band
  [T]**, the latter run as the iterative loop of [`PROCESS.md`](PROCESS.md) §5.
- Renders every outcome in the taxonomy and may invent none. Usage context (second screen, hands
  full, dim room) outranks feature richness in any trade-off.

No spec yet has a `decision_log.md`, so [`DECISIONS.md`](DECISIONS.md) is currently the only
decision record in the tree. There are no `specs/bugfixes/` folders and no `prerequisites.md` or
`smolspec.md` files.

---

## State of play

**What exists**

- Four `requirements.md` documents in EARS, criteria individually anchored, across three of the
  four domains.
- One governing shared-contract document covering the seams between them.
- Nine cross-cutting ADRs in `DECISIONS.md`, all *accepted*.

**What is next**

- The **design phase** for each of the four specs (`/starwave-design`), each behind its own
  approval gate. Nothing is ready for tasks or implementation.
- `CONTRACTS.md` records that its own first pass was found incomplete within an hour of being
  written (Decision 6). Reconciling each design against it is a precondition for approval, not a
  formality.

**Known open items**

| Item | Detail |
|---|---|
| `platform` has no spec | Decision 1 gives it provider key configuration, the app shell, and the build. Nothing owns them today. |
| Wrong Akai manual ingested | `akai_apc-key-25_user-guide_v1.0_multi.pdf` documents the **original** APC Key 25; the rig has the **mk2**, which differs in pads and shift layer (Decision 9). Mitigated by declared `hardware_applicability` shown inline on citations; the real fix is obtaining the mk2 guide from akaipro.com. |
| No Focusrite Scarlett Solo manual | The interface is owned but undocumented — the standing example of the *owned-but-undocumented* report required by [`CONTRACTS.md`](CONTRACTS.md) §5. |
| Triage starter entries unwritten | `data/symptom-triage` §7 specifies five starter entries (no sound from a track, a track distorting, monitoring latency, drum pad triggers the wrong sound, controller does nothing). None are authored yet, so the diagnostic questions the source exists to answer still refuse. |
