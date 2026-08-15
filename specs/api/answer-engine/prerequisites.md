# Prerequisites for Answer Engine

These tasks require human intervention outside of code. `tasks.md` builds and passes CI against
stubs without them, but the real-provider paths and `make bench` cannot run until they are done.

## During Implementation

- [ ] **Store a real provider API key in the macOS Keychain.** The engine reads credentials via
      keyring under service `dawmans`, one account per provider kind (Decision 6) — for the
      Anthropic provider, account `anthropic`. Task 27 stubs keyring in CI, so the live Keychain
      read path never runs there; it is exercised only on a developer machine holding a key. The
      key is never written to a configuration file or environment variable. Blocks the real-key
      verification of tasks 23–24 and every `make bench` run against the Anthropic provider
      (task 45).
- [ ] **Grant Keychain access once.** The first read of the `dawmans` service item prompts macOS
      to allow the Python interpreter (or test runner) to read it. Choose "Always Allow" so
      unattended `make bench` runs do not stall on the prompt.

## Before Testing (`make bench`, task 45)

- [ ] **Build a real index.** `make bench` measures 4.1 and 4.6–4.8 against a live view, not the
      synthetic 1,200-chunk CI index. That means the manual-corpus prerequisites are met first —
      vendor PDFs in `manuals/` and `make fetch-model` run, per
      `specs/data/manual-corpus/prerequisites.md` — and `dawmans ingest` has committed a view.
      `make bench` skips honestly when the index or the manuals are absent.
- [x] **Optional — run a local OpenAI-compatible server on loopback.** Benching the local provider
      class (4.6–4.8 for that kind, and 6.14's no-outbound-request property against a real
      stream) needs a server on `127.0.0.1` (e.g. llama.cpp or LM Studio serving an
      OpenAI-compatible endpoint). Without one, `make bench` covers the Anthropic kind only.

      **Done 2026-08-15**, and worth recording as the shortest path to a working install,
      because it needs no key and makes no outbound request:

      ```
      lms server start --port 1234            # or llama.cpp / Ollama on loopback
      lms load openai/gpt-oss-20b --gpu max
      uv run dawmans serve --local-url http://127.0.0.1:1234
      curl -s -H "Origin: http://127.0.0.1:8722" -H "Content-Type: application/json" \
        -X PUT http://127.0.0.1:8722/provider \
        -d '{"kind":"local","model":"openai/gpt-oss-20b","disclosure_ack":true}'
      ```

      Then open `http://127.0.0.1:8722`. Two things learned doing it:

      - **Name the model.** `--local-model` for `make bench`, `model` in the PUT body. A server
        holding more than one model answers an unnamed request with "Multiple models are loaded",
        which arrives as `provider-error` on every question and looks like an engine fault.
      - **A reasoning model can miss 4.9 before it says anything.** The 27B distilled model
        thinks past the 10 s first-token watchdog, so every turn ends `timeout` with no output.
        That is the watchdog working. Pick a model that starts emitting quickly, or the engine
        will (correctly) refuse to wait for it.
