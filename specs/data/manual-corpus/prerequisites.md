# Prerequisites for Manual Corpus

These tasks require human intervention outside of code. `tasks.md` cannot complete without them.

## Before Starting

- [ ] **Place the vendor PDFs in `manuals/`.** The directory is gitignored — the PDFs are
      copyrighted vendor documents kept locally and never committed — so every machine supplies its
      own copies. Each must be named to the convention of requirements 2.1–2.3,
      `<vendor>_<product>_<doctype>_v<version>_<lang>.pdf`, or discovery rejects it:
      - `ableton_live-12_reference-manual_v12_en.pdf`
      - `akai_apc-key-25_user-guide_v1.0_multi.pdf`
      - `alesis_nitro-max_user-guide_v1.0_en.pdf`
      Blocks task 11 (fixture capture), which reads them to produce the committed extraction
      snapshots, and `make bench` (requirement 8.1).

## During Implementation

- [ ] **Run `make fetch-model` once on this machine.** It downloads `bge-small-en-v1.5` (67 MB)
      from Hugging Face into a gitignored `models/`. This is deliberately outside the ingestion
      path: ingestion runs with `HF_HUB_OFFLINE=1` and fails immediately if the cache is absent
      (requirement 8.5). Needs network access once; nothing afterwards does.
      Blocks task 31 onwards, and every test that embeds.

## Not Prerequisites — corpus gaps, and why they must not be closed silently

Two known gaps are recorded in the requirements as the standing examples the rig-gap tests assert
against. Closing either is a legitimate thing to do, but it **changes the expected values in task
39's tests**, so do it deliberately and update the tests in the same change:

- **No Focusrite Scarlett Solo manual.** The interface is owned and undocumented — the standing
  owned-but-undocumented case (11.4). Adding the manual removes `focusrite/scarlett-solo` from that
  report.
- **The wrong Akai manual is ingested.** `akai_apc-key-25_user-guide_v1.0_multi.pdf` documents the
  original APC Key 25; the rig holds the mk2, which differs in pads and shift layer. It is the
  standing documented-but-unconfirmed case (11.5). Obtaining the mk2 guide from akaipro.com is the
  real fix; until then the declared `hardware_applicability` shown inline on citations is the
  mitigation.
