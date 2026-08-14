# Shared Contracts: DAWMans

**Status:** governing. Where a per-spec `requirements.md` and this file disagree, this file wins and
the spec is a defect to be reconciled.

DAWMans is split across four specs — [`data/manual-corpus`](data/manual-corpus/requirements.md),
[`data/symptom-triage`](data/symptom-triage/requirements.md),
[`api/answer-engine`](api/answer-engine/requirements.md) and
[`ui/ask-and-source-picker`](ui/ask-and-source-picker/requirements.md). `PROCESS.md` §10 requires a
root overview holding the shared assumptions when a capability is split. This is that overview.

It exists because the three specs were drafted in parallel and diverged at every seam: capabilities
were produced and never consumed, and the same interaction was described two ways. This file defines
the four records that cross a spec boundary, and who owns each field. **A spec may not invent a
field on a shared record, and may not silently drop one.**

---

## 1. `SourceRecord` — produced by `data/manual-corpus`, consumed by both others

One per ingested **source**, of either kind (§4a). Backs the source picker, the citation, and the
corpus inventory.

| Field | Owner | Notes |
|---|---|---|
| `kind` | corpus | `vendor-manual` or `authored-triage`, per §4a. **Must reach the user** — see §3. No source is indexed without one. |
| `source_id` | corpus | For `vendor-manual`, derived from the filename as `<vendor>/<product>`, stable while the filename is. For `authored-triage`, derived from the source's own content and **independent of any filename**. |
| `vendor`, `product`, `doctype`, `lang` | corpus | From the filename fields for `vendor-manual`. Not applicable to `authored-triage`. |
| `doc_version` | corpus | From the filename for `vendor-manual`. **Must reach the user** — see §3. Not applicable to `authored-triage`. |
| `display_name` | corpus | Human-readable, for the picker and citations. Both kinds. |
| `hardware_applicability` | corpus | Which hardware revision this source describes, and whether that is *confirmed* or *assumed*. **Never inferred automatically** — see §5. |
| `page_count` | corpus | `vendor-manual` only; a pageless source reports it as not applicable. |
| `ingested_at`, `chunk_count` | corpus | Inventory only. Both kinds. |
| `low_text` | corpus | Text layer present but sparse. Ingested, not rejected. `vendor-manual` only; inventory and picker marking only. |

`vendor`, `product`, `doctype`, `lang`, `page_count`, `ingested_at` and `chunk_count` are
**inventory-only** — reported, not required to reach any other surface. Every other field on this
record has a named consumer, and a future audit should treat an unconsumed one as a defect.

## 2. `Passage` — emitted by `data/manual-corpus`, consumed by `api/answer-engine`

The unit of retrieval and of citation. `data/manual-corpus` emits the record for **both** source
kinds; for `authored-triage` the content and its chunking are specified by
[`data/symptom-triage`](data/symptom-triage/requirements.md), which supplies what the record carries.

**Pageless sources.** `section_number`, `page_start` and `page_end` are absent on an
`authored-triage` passage and SHALL NOT be synthesised, exactly as `section_number` is absent on an
unnumbered document. No criterion may reject a source for lacking them.

| Field | Owner | Notes |
|---|---|---|
| `passage_id` | corpus | **Content-derived and stable across re-ingestion.** Retained history must still resolve after a manual is re-ingested. |
| `source_id` | corpus | |
| `section_number` | corpus | Absent where the document has no numbering; never invented. |
| `section_title`, `page_start`, `page_end` | corpus | |
| `text` | corpus | |
| `degraded` | corpus | Contains characters that could not be repaired. **Must be consumed** — §3 and §4. |
| `has_figures` | corpus | The section contains figures, with their page. **Must be consumed** — §3. |
| `unbacked` | triage | An authored cause that rests on no vendor-manual passage — either none was ever given (a device with no ingested manual, such as the Scarlett Solo) or the pointer has since stopped resolving. **Must be consumed** — §3. |

## 3. `Citation` — produced by `api/answer-engine`, rendered by `ui/ask-and-source-picker`

Every field here is rendered or actionable. Nothing on this record may dead-end.

| Field | Rendering requirement |
|---|---|
| `source_id`, `display_name` | Shown. |
| `kind` | **Shown inline**, never behind a disclosure, distinguishable in greyscale. The user must be able to see that a claim rested on their own note rather than on the manufacturer's manual. |
| `doc_version` | **Shown inline** for a `vendor-manual`. This is the mk1/mk2 mitigation; it fails if hidden. Absent on a pageless authored source. |
| `unbacked` | **Shown inline** on any cause resting on no manual passage, so a broken or never-provided fix pointer is never presented as documented. |
| `hardware_applicability` | **Shown inline** where applicability is assumed rather than confirmed, not behind a disclosure. |
| `section_number`, `section_title`, `page` | Shown. |
| `passage_id` | Backs passage expansion and the open-at-page action. |
| `degraded` | Expanded passage marked as containing unreadable characters. |
| `has_figures` | Shown as "figure on p*N*" — the sole offset for a text-only index. |

**Open at source.** Any citation SHALL offer a one-activation action opening the cited source at the
cited location. For a `vendor-manual` that is the PDF at the cited page — with figures excluded from
the index, a citation that is only a string strands the user in a 1009-page document. For an
`authored-triage` source, which has no pages, it is the entry itself, so the user can correct a
wrong entry at the moment they discover it.

**Location fields on a pageless source.** An `authored-triage` citation carries no page and no
section number. These are rendered as absent, never invented — the same rule §2 applies to an
unnumbered document — with the entry's symptom title occupying the location slot.

## 4. `AnswerEnvelope` — produced by `api/answer-engine`, rendered by `ui/ask-and-source-picker`

| Field | Notes |
|---|---|
| `outcome` | One of §6. The UI SHALL render every outcome and SHALL NOT invent outcomes the engine cannot emit. |
| `direct_answer` | The actionable answer, first, before qualification. The UI's "≤25 words to the instruction" target depends on the engine producing this; it is not achievable by UI work alone. |
| `body` | Carries machine-identifiable structure — headings, ordered steps, key terms. |
| `citations[]` | Per §3. |
| `contributing_sources[]` | Which selected sources actually supplied passages. **Rendered** — this is how the user notices a controller question was answered from the Live manual. |
| `uncovered_parts[]` | Named parts of the question the sources did not cover. Rendered subordinate to the answer, not as a refusal. |
| `narrowing` | A question plus 2–4 candidates, each selectable in one activation. |
| `required_device` | On a coverage failure, the device whose documentation would answer it — distinct from naming an ingested source. |
| `ungrounded` | Set after streaming completes; the UI marks an already-rendered answer rather than withholding it. |
| `timings` | Per-stage, for verifying the latency budget. |

## 4a. Source kinds

Not every source is a vendor PDF. Two kinds exist, and both flow through the same `SourceRecord`,
`Passage` and `Citation` records — a source's kind changes what it is trusted for, never how it is
cited.

| Kind | Origin | Trusted for |
|---|---|---|
| `vendor-manual` | A manufacturer's PDF, ingested from `manuals/`. | What a control **is** and **does**. Authoritative on fact, silent on practice. |
| `authored-triage` | Written by the user. See [`data/symptom-triage`](data/symptom-triage/requirements.md). | Which documented control to **check**, and in what order, for a given symptom. |

**Why the second kind exists.** Measured against the real corpus: the phrase "gain staging" appears
**zero** times in the 1009-page Live 12 manual, and "troubleshoot" appears twice. Live's manual
documents the Track Activator as *"to mute the track's output, turn off the Track Activator"* — an
instruction for muting, never as a **cause** of silence. A reference manual documents controls, not
practice. So a strictly manual-grounded system cannot answer the two questions a producer most often
asks mid-session, and the narrowing flow in §4 is unimplementable, because no passage contains the
distinguishing conditions it must draw candidates from.

An `authored-triage` source closes that gap without weakening grounding: its entries are retrieved,
ranked and **cited exactly like any other source**, and the UI shows their provenance as authored by
the user rather than by the manufacturer. Every fix an entry points to still cites a vendor manual.

## 5. Hardware applicability

A source may be **present, cited, and wrong for the user's rig.** The ingested Akai guide is Manual
Version 1.0 describing the original APC Key 25; the user owns the mk2, which differs in pads and
shift layer. A confidently cited procedure for the wrong revision is this product's worst failure
mode, and it is worse than a refusal because the citation *increases* the user's confidence.

Therefore: the system SHALL hold a declared rig inventory — the hardware the user owns — separately
from the corpus inventory of what is indexed. It SHALL be able to report **owned-but-undocumented**
(the Scarlett Solo today) and **documented-but-unconfirmed** (the APC guide today).

## 6. Outcome taxonomy

The complete set the engine may emit and the UI SHALL render. Neither side may hold a private
member.

| Outcome | Meaning |
|---|---|
| `answered` | Fully answered from in-scope sources. |
| `partially-answered` | Answered in part; `uncovered_parts[]` names the rest. **Not a refusal** — renders as an answer. |
| `needs-narrowing` | A narrowing question with candidates. |
| `refused-not-covered` | In-scope sources do not cover it; another ingested source might. |
| `out-of-domain` | A technique question, not a control question. A reference manual documents controls, not practice; no ingested manual will ever cover it. Suppresses source suggestions. |
| `no-manual-for-device` | Answerable, but needs a manual not ingested. Names the device and the filename to add. |
| `no-sources-selected` | Defence in depth; the UI does not submit an empty scope. |
| `unknown-source-id` | |
| `corpus-empty` | Nothing ingested yet. |
| `provider-unconfigured` / `-unreachable` / `-rate-limited` / `-error` | `rate-limited` carries a retry-after. |
| `timeout` | Attributed to the provider, distinct from unreachable. |
| `incomplete` | Synthesis stopped before the answer finished. What was produced is retained and marked. |
| `cancelled` | The caller abandoned the turn — a new question arrived mid-stream, or the user cancelled. |

## 7. Latency budget

Measured end to end, keypress to first painted token — the only figure the user experiences. Stage
budgets must compose into it, not be stated at incompatible boundaries.

| Stage | p95 |
|---|---|
| Retrieval | 50 ms |
| Session state acquisition | 100 ms, **excluded** from the engine overhead cap below |
| Engine overhead (prompt assembly, citation resolution, framing) | 150 ms |
| Provider time to first token | 1.2 s hosted / 2.5 s local |
| Transport and paint | 100 ms |
| **Keypress → first painted token** | **1.5 s hosted / 2.8 s local** |

The end-to-end figure is a **target** with an acceptance band, per `PROCESS.md` §5: ≤2.0 s hosted and
≤3.5 s local at p95. The stage budgets above are hard, the composed figure converges. A spec stating
that band is conforming, not disagreeing.

A narrowing question SHALL be budgeted as a first-token target consistent with the provider class,
not as a completion target that beats it.

## 8. Known constraints that cross every spec

- **Live 12 Standard, not Suite.** The manual documents the full product. An answer recommending a
  Suite-only device or a Max for Live feature is manual-accurate and useless. It must be flagged.
- **Chunk size is bounded by the embedding window, not by readability alone.** 500 words is ~600
  tokens and overflows a 512-token window, silently truncating the tail of every maximal chunk.
- **Grounding versus reasoning.** Facts SHALL be cited, without exception. Choosing *which
  documented control to check* is reasoning over cited facts and is permitted; it is not "general
  knowledge" and the no-general-knowledge rule SHALL NOT be written so as to forbid it. Without this
  split, symptom triage is simultaneously required and prohibited.
