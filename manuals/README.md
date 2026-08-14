# Manuals

This directory holds the vendor PDFs that DAWMans grounds its answers in. Ingestion reads whatever
manuals are present here and builds the searchable corpus from them.

**The PDFs themselves are not committed.** `manuals/*.pdf` is gitignored: the files total roughly
110MB and are third-party copyrighted documents we hold no redistribution licence for. See
[`specs/DECISIONS.md`](../specs/DECISIONS.md) Decision 3 for the reasoning. This README is tracked
and is the record of what a working checkout is expected to contain.

To set up a fresh clone, download each file from the vendor link below and rename it to the filename
in the table.

## Filename convention

```
<vendor>_<product>_<doctype>_v<version>_<lang>.pdf
```

- Fields are separated by `_`; words within a field use `-`. All lowercase.
- `vendor` — the manufacturer, one word where possible (`ableton`, `akai`, `alesis`).
- `product` — includes the generation or model where that distinguishes the hardware
  (`live-12`, `apc-key-25`, `scarlett-solo-4g`).
- `doctype` — what the document is (`reference-manual`, `user-guide`, `quickstart-guide`).
- `version` — the document's own version, prefixed with `v` (`v12`, `v1.0`, `v1.1`).
- `lang` — an ISO 639-1 code (`en`, `de`), or `multi` for a multilingual document.

The filename is the source's stable identity: the source ID shown in citations and in the source
picker is derived from `<vendor>/<product>`. Renaming a file changes what the user sees, so get the
name right on download. Full reasoning is in [`specs/DECISIONS.md`](../specs/DECISIONS.md)
Decision 2.

**Adding a manual.** Downloading the Focusrite Scarlett Solo 4th Gen user guide, version 4.0,
English, gives `scarlett-solo-4th-gen-user-guide.pdf` from the vendor. Rename it to
`focusrite_scarlett-solo-4g_user-guide_v4.0_en.pdf`, drop it in this directory, add a row to the
table below, and re-run ingestion — no code change and no manifest edit is needed, because ingestion
discovers files rather than reading a list.

One more step where the product carries a generation marker and the rig's device id does not, as
here (`scarlett-solo-4g` against `scarlett-solo`): **declare the mapping in `rig.yaml`'s
`source_applicability`.** Without it the manual is ingested and its device is still reported as
having no documentation — see `specs/data/manual-corpus/requirements.md` 11.7.

## Expected files

| Filename | Vendor / product | Pages | Where to obtain |
|---|---|---|---|
| `ableton_live-12_reference-manual_v12_en.pdf` | Ableton / Live 12 | 1009 | ableton.com — Live 12 manual, PDF download from the Help and Support pages |
| `akai_apc-key-25_user-guide_v1.0_multi.pdf` | Akai / APC Key 25 | 24 | akaipro.com — APC Key 25 product page, Downloads section |
| `alesis_nitro-max_user-guide_v1.1_en.pdf` | Alesis / Nitro Max | 35 | alesis.com — Nitro Max Kit product page, Downloads section |
| `focusrite_scarlett-solo-4g_user-guide_v4.0_en.pdf` | Focusrite / Scarlett Solo 4th Gen | 39 | [downloads.focusrite.com](https://downloads.focusrite.com/focusrite/scarlett-4th-gen/scarlett-solo-4th-gen) — Scarlett Solo 4th Gen, User Guide V4, English |

## Known issues with these documents

These are verified facts about the specific files above, recorded so ingestion work does not have to
rediscover them.

### Akai APC Key 25 user guide

- The document is **Manual Version 1.0** and is **multilingual**. English occupies only pp. 3–6 plus
  an appendix on p. 23; Spanish, French, Italian and German fill the rest. Ingestion must select the
  English ranges rather than treating the whole document as one language.
- It shows **no mk2 markers anywhere**, so it is probably the guide for the **original APC Key 25**,
  not the mk2 the user owns. Answers sourced from it may not match the user's hardware. Obtaining the
  mk2 guide would supersede this file.
- **Arrow glyphs extract as mojibake** — they come through as `ð`, `ñ`, `ô`, `õ`. Any extraction step
  needs to handle or strip these rather than pass them into the corpus as text.

### Ableton Live 12 reference manual

- **1009 pages**, produced by pandoc via WeasyPrint from the HTML manual.
- It has a **clean embedded text layer** — no OCR is required.
- Extraction is fast: roughly **0.7 seconds** for approximately **242,000 words**.
- Its **96MB size is screenshots, not text**. Do not treat file size as a proxy for extraction cost
  or corpus size.

### Focusrite Scarlett Solo 4th Gen user guide

- **39 pages, User Guide Version 4.0, English only.** Title metadata reads
  `Scarlett Solo 4th Gen User Guide`.
- **Generation is confirmed against the hardware, not assumed.** Live 12's log on this machine
  reports `Scarlett Solo 4th Gen`, serial `S11C8GT3404843`. Its `hardware_applicability` can
  therefore be `confirmed` — the only source in the corpus that can currently claim it.
- A **2nd Generation** guide was briefly present and was removed: it opens *"Thank you for purchasing
  this Second Generation Scarlett Solo"* and describes different hardware. It was not merely older —
  a cited answer from it about the front panel would have been wrong for this rig.
- **Most of the front panel is physical and self-evident** — gain control and gain halo, Inst, Air,
  Output, Direct Monitor, headphone output. The manual's value is not the knobs.
- **What is not self-evident, and why the file earns its place:** `Focusrite Control 2` is mentioned
  **76 times** — Air *mode* selection between Presence and Harmonic Drive lives there, as does
  **loopback** (22 mentions), which is not discoverable from the hardware at all.
- **The word "buffer" appears zero times.** Buffer size is not in this manual, and Live's own manual
  defers its Audio Settings walkthrough to an in-app tutorial (§17.1). So *"why is there latency when
  I monitor"* is still only partly answerable from vendor documentation even with this file present —
  Direct Monitor is covered here, buffer size is covered nowhere. That gap belongs to
  [`specs/data/symptom-triage`](../specs/data/symptom-triage/requirements.md).

### Alesis Nitro Max user guide

- **35 pages**, produced by Adobe Illustrator.
- §5.2 contains a **two-column MIDI note table** that needs layout-preserving extraction. A naive
  linear text extraction interleaves the two columns and produces wrong note mappings.
