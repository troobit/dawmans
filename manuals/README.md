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

**Adding a manual.** Downloading the Focusrite Scarlett Solo 4th Gen user guide, version 3, English,
gives `scarlett-solo-4th-gen-user-guide.pdf` from the vendor. Rename it to
`focusrite_scarlett-solo-4g_user-guide_v3_en.pdf`, drop it in this directory, add a row to the table
below, and re-run ingestion — no code change and no manifest edit is needed, because ingestion
discovers files rather than reading a list.

## Expected files

| Filename | Vendor / product | Pages | Where to obtain |
|---|---|---|---|
| `ableton_live-12_reference-manual_v12_en.pdf` | Ableton / Live 12 | 1009 | ableton.com — Live 12 manual, PDF download from the Help and Support pages |
| `akai_apc-key-25_user-guide_v1.0_multi.pdf` | Akai / APC Key 25 | 24 | akaipro.com — APC Key 25 product page, Downloads section |
| `alesis_nitro-max_user-guide_v1.1_en.pdf` | Alesis / Nitro Max | 35 | alesis.com — Nitro Max Kit product page, Downloads section |

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

### Alesis Nitro Max user guide

- **35 pages**, produced by Adobe Illustrator.
- §5.2 contains a **two-column MIDI note table** that needs layout-preserving extraction. A naive
  linear text extraction interleaves the two columns and produces wrong note mappings.
