"""`make bench` — the real-provider, real-index timing runs (4.1, 4.6–4.8).

CI covers 4.2 and 4.3 against a synthetic index (`tests/answer/test_timing.py`);
everything needing a real provider and a real view runs here, and skips
honestly when either is absent — the same limitation the sibling specs
accept for their full-corpus budgets. Prerequisites (the Keychain key, an
ingested corpus): specs/api/answer-engine/prerequisites.md.

Measured, per provider class:
- first token p95 against 4.6/4.7 (1.2 s hosted, 2.5 s local), with the
  narrowing-shaped question held to the same first-token target and never
  to a completion target that would have to precede it (7.3);
- completion p95 against 4.8 (6 s hosted, 15 s local), non-narrowing turns;
- 4.1's composed figure estimated as first token + the 100 ms transport
  and paint allowance the UI owns.

Also calibrates Decision 8's history-token margin: the resident BGE
tokeniser's counts against the provider's count_tokens over sample
prompts, reporting whether the configured 10% covers the observed
divergence — the margin is a guess until this runs.
"""

import argparse
import asyncio
import sys
from pathlib import Path

HOSTED_TARGETS = {"first_token_ms": 1200.0, "completion_ms": 6000.0}  # 4.6, 4.8
LOCAL_TARGETS = {"first_token_ms": 2500.0, "completion_ms": 15000.0}  # 4.7, 4.8
RETRIEVAL_TARGETS_MS = {"median": 10.0, "p95": 50.0}  # 4.2, real embed + real index
PAINT_ALLOWANCE_MS = 100.0  # 4.1's transport-and-paint share, owned by the UI
COMPOSED_TARGETS_MS = {"hosted": 1500.0, "local": 2800.0}  # 4.1
HISTORY_MARGIN = 0.10  # Decision 8

QUESTIONS = [
    ("What does the Track Activator do?", "answer"),
    ("How do I re-enable a muted track?", "answer"),
    ("Which MIDI note does the kick drum use in a drum rack?", "answer"),
    ("no sound from track 3", "narrowing"),
]


def p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def skip(reason):
    print(f"SKIP: {reason}")
    print("      see specs/api/answer-engine/prerequisites.md")
    raise SystemExit(0)


async def run_turn(pipeline, question, sources):
    timings = outcome = None
    async for event in pipeline.turn(question, sources=sources):
        if event.name == "outcome" and outcome is None:
            outcome = event.data.outcome
        if event.name == "timings":
            timings = event.data
    return outcome, timings


def bench_provider(label, binding, watcher, embedder, count_tokens, targets, composed_target):
    from dawmans.answer.state.null import NullStateSource
    from dawmans.answer.turn import TurnPipeline

    pipeline = TurnPipeline(
        watcher=watcher,
        binding=binding,
        state_source=NullStateSource(),
        embedder=embedder,
        count_tokens=count_tokens,
    )
    sources = [record["source_id"] for record in watcher.view.sources]
    first_token, completion, retrieval = [], [], []
    print(f"\n== {label} ==")
    for question, shape in QUESTIONS:
        outcome, timings = asyncio.run(run_turn(pipeline, question, sources))
        if timings is None or timings.first_token_ms is None:
            print(f"  {question!r}: outcome={outcome} — no stream, not measured")
            continue
        retrieval.append(timings.retrieval_ms)
        first_token.append(timings.first_token_ms)
        line = f"  {question!r}: outcome={outcome} first_token={timings.first_token_ms:.0f}ms"
        if shape == "narrowing":
            # 7.3: the same first-token target as any other response for
            # this provider class; no completion target precedes it.
            line += " (narrowing: first-token target only)"
        elif timings.completion_ms is not None:
            completion.append(timings.completion_ms)
            line += f" completion={timings.completion_ms:.0f}ms"
        print(line)

    failed = False
    if retrieval:
        import statistics

        # 4.2 over the full reference corpus with the real embed — CI's
        # figure comes from a synthetic index with the embed stubbed.
        median = statistics.median(retrieval)
        tail = p95(retrieval)
        ok = median <= RETRIEVAL_TARGETS_MS["median"] and tail <= RETRIEVAL_TARGETS_MS["p95"]
        failed |= not ok
        print(
            f"  retrieval median {median:.1f}ms vs {RETRIEVAL_TARGETS_MS['median']:.0f}ms, "
            f"p95 {tail:.1f}ms vs {RETRIEVAL_TARGETS_MS['p95']:.0f}ms "
            f"[{'ok' if ok else 'MISSED'}]"
        )
    if first_token:
        observed = p95(first_token)
        ok = observed <= targets["first_token_ms"]
        failed |= not ok
        print(
            f"  first token p95: {observed:.0f}ms vs {targets['first_token_ms']:.0f}ms "
            f"[{'ok' if ok else 'MISSED'}]"
        )
        composed = observed + PAINT_ALLOWANCE_MS
        print(
            f"  4.1 composed estimate (+{PAINT_ALLOWANCE_MS:.0f}ms paint): "
            f"{composed:.0f}ms vs {composed_target:.0f}ms "
            f"[{'ok' if composed <= composed_target else 'MISSED'}]"
        )
    if completion:
        observed = p95(completion)
        ok = observed <= targets["completion_ms"]
        failed |= not ok
        print(
            f"  completion p95: {observed:.0f}ms vs {targets['completion_ms']:.0f}ms "
            f"[{'ok' if ok else 'MISSED'}]"
        )
    return not failed


def calibrate_margin(api_key, model, view, count_tokens):
    """Decision 8: is the 10% margin enough for the tokeniser divergence?"""
    import anthropic

    from dawmans.answer.prompt import SYSTEM_PROMPT

    samples = [SYSTEM_PROMPT]
    texts = [record.get("text", "") for record in view.passages[:40]]
    for step in range(0, len(texts), 10):
        chunk = "\n\n".join(texts[step : step + 10])
        if chunk:
            samples.append(chunk)

    client = anthropic.Anthropic(api_key=api_key)
    print("\n== Decision 8 margin calibration ==")
    worst = 0.0
    for sample in samples:
        local = count_tokens(sample)
        provider = client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": sample}]
        ).input_tokens
        divergence = (provider - local) / local if local else 0.0
        worst = max(worst, divergence)
        print(f"  local={local} provider={provider} divergence={divergence:+.1%}")
    covered = worst <= HISTORY_MARGIN
    print(
        f"  worst under-count {worst:+.1%} vs the configured {HISTORY_MARGIN:.0%} margin "
        f"[{'covered' if covered else 'NOT COVERED — raise the margin'}]"
    )
    return covered


def main(argv=None):
    parser = argparse.ArgumentParser(description="Real-provider, real-index budgets")
    parser.add_argument("--index-dir", type=Path, default=Path("index"))
    parser.add_argument("--local-url", default=None, help="Bench a local provider too")
    args = parser.parse_args(argv)

    if not (args.index_dir / "manifest.json").is_file():
        skip(f"no ingested index at {args.index_dir}/manifest.json — run `dawmans ingest` first")

    from dawmans.answer.provider import credentials
    from dawmans.answer.provider.base import ProviderKind
    from dawmans.cli import _load_model

    api_key = credentials.read_key(ProviderKind.KEYED_HOSTED)
    if api_key is None and args.local_url is None:
        skip("no Keychain key stored for the Anthropic provider and no --local-url given")

    print("loading and warming the embedding model …")
    embedder, count_tokens = _load_model()
    list(embedder.embed(["warm-up"]))

    from dawmans.answer.turn import ProviderBinding
    from dawmans.answer.view import ViewWatcher

    watcher = ViewWatcher(args.index_dir)
    all_ok = True

    if api_key is not None:
        from dawmans.answer.provider.anthropic import DEFAULT_MODEL, AnthropicProvider

        provider = AnthropicProvider(api_key)

        def binding() -> ProviderBinding:
            return ProviderBinding(
                provider=provider,
                kind=str(ProviderKind.KEYED_HOSTED),
                requires_key=True,
                credential_stored=True,
                name="anthropic",
            )

        all_ok &= bench_provider(
            "hosted (anthropic)",
            binding,
            watcher,
            embedder,
            count_tokens,
            HOSTED_TARGETS,
            COMPOSED_TARGETS_MS["hosted"],
        )
        all_ok &= calibrate_margin(api_key, DEFAULT_MODEL, watcher.view, count_tokens)

    if args.local_url is not None:
        from dawmans.answer.provider.local import LocalProvider

        local_provider = LocalProvider(args.local_url)

        def binding() -> ProviderBinding:  # noqa: F811 — one binding per provider branch
            return ProviderBinding(
                provider=local_provider, kind=str(ProviderKind.LOCAL), name="local"
            )

        all_ok &= bench_provider(
            "local",
            binding,
            watcher,
            embedder,
            count_tokens,
            LOCAL_TARGETS,
            COMPOSED_TARGETS_MS["local"],
        )

    print("\nbench:", "all budgets met" if all_ok else "budgets MISSED — see above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
