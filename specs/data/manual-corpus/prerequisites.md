# Prerequisites for Manual Corpus

These tasks require human intervention outside of code. `tasks.md` cannot complete without them.

## Before Starting

- [ ] **Place the vendor PDFs in `manuals/`.** The directory is gitignored — the PDFs are
      copyrighted vendor documents kept locally and never committed — so every machine supplies its
      own copies. Each must be named to the convention of requirements 2.1–2.3,
      `<vendor>_<product>_<doctype>_v<version>_<lang>.pdf`, or discovery rejects it:
      - `ableton_live-12_reference-manual_v12_en.pdf`
      - `akai_apc-key-25_user-guide_v1.0_multi.pdf`
      - `alesis_nitro-max_user-guide_v1.1_en.pdf`
      - `focusrite_scarlett-solo-4g_user-guide_v4.0_en.pdf`
      `manuals/README.md` is the tracked record of the expected set, with a vendor download link
      for each. Blocks task 11 (fixture capture), which reads them to produce the committed
      extraction snapshots, and `make bench` (requirement 8.1).

## During Implementation

- [ ] **Run `make fetch-model` once on this machine.** It downloads `bge-small-en-v1.5` (67 MB)
      from Hugging Face into a gitignored `models/`. This is deliberately outside the ingestion
      path: ingestion runs with `HF_HUB_OFFLINE=1` and fails immediately if the cache is absent
      (requirement 8.5). Needs network access once; nothing afterwards does.
      Blocks task 31 onwards, and every test that embeds.

## Also required — declare the Scarlett's applicability in `rig.yaml`

- [ ] **Map `focusrite/scarlett-solo-4g` to the rig device `focusrite/scarlett-solo`** in
      `source_applicability`, with `revision: 4th-gen` and `status: confirmed`. This is mandatory,
      not optional (requirement 11.7): the filename's product carries the generation and the rig's
      device id does not, so the 11.2 default resolves the source to a device that is not in the
      inventory — the manual is present and its device reads as having none. `status: confirmed` is
      legitimate here and nowhere else in the corpus, the generation having been checked against
      Live's own log on this machine. Blocks tasks 39–40.

## Not Prerequisites — corpus gaps, and why they must not be closed silently

One known gap is recorded in the requirements as a standing example the rig-gap tests assert
against. Closing it is a legitimate thing to do, but it **changes the expected values in task 39's
tests**, so do it deliberately and update the tests in the same change:

- **The wrong Akai manual is ingested.** `akai_apc-key-25_user-guide_v1.0_multi.pdf` documents the
  original APC Key 25; the rig holds the mk2, which differs in pads and shift layer. It is the
  standing documented-but-unconfirmed case (11.5). Obtaining the mk2 guide from akaipro.com is the
  real fix; until then the declared `hardware_applicability` shown inline on citations is the
  mitigation.

The **owned-but-undocumented** gap that used to sit alongside it is closed: the Focusrite Scarlett
Solo 4th Gen guide is ingested, so 11.4's report is empty and every rig device is documented. Task
39 asserts that emptiness against the real rig and asserts the non-empty case against a fixture rig
declaring a device with no source — the report has to keep working for the next piece of gear, which
will sit in `rig.yaml` without a manual for as long as the download takes.
