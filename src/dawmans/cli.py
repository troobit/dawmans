"""Command-line entry point.

`dawmans ingest`, `dawmans validate` and `dawmans inventory` land with
`data/manual-corpus`; `serve` is wired here.

Serve-side imports are deferred into the functions that need them: this
module is shared with the ingest commands, whose environment installs the
`ingest` extra only — importing starlette or fastembed at module import
time would break `dawmans --help` there.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8722
# llama.cpp's default; LM Studio and Ollama differ, so it is configuration.
DEFAULT_LOCAL_URL = "http://127.0.0.1:8080"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def _load_model() -> tuple[Any, Callable[[str], int]]:
    """The resident embedding model and its tokeniser-backed counter.

    The same tokeniser serves retrieval's query embedding and Decision 8's
    local history budget — no provider SDK call occurs before stream().
    """
    from fastembed import TextEmbedding

    embedder = TextEmbedding(EMBEDDING_MODEL)

    def count_tokens(text: str) -> int:
        return embedder.token_count(text)

    return embedder, count_tokens


def _provider_factory(local_url: str):
    """The registry's constructors, one per kind (6.12): each provider
    builds its own client against its own base URL, and the keyed kind's
    constructor is the stored key's only reader (6.13)."""
    from dawmans.answer.provider import credentials
    from dawmans.answer.provider.anthropic import DEFAULT_MODEL, AnthropicProvider
    from dawmans.answer.provider.base import Provider, ProviderKind
    from dawmans.answer.provider.local import LocalProvider
    from dawmans.answer.provider.shared import SharedBackendProvider

    def factory(kind: ProviderKind, model: str | None) -> Provider | None:
        if kind is ProviderKind.KEYED_HOSTED:
            key = credentials.read_key(kind)
            if key is None:
                # Unconstructable: pre-flight reports missing-credential.
                return None
            return AnthropicProvider(key, model or DEFAULT_MODEL)
        if kind is ProviderKind.LOCAL:
            return LocalProvider(local_url, model)
        return SharedBackendProvider()

    return factory


def run_serve(
    *,
    index_dir: Path,
    manuals_root: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    static_dir: Path | None = None,
    local_url: str = DEFAULT_LOCAL_URL,
    load_model: Callable[[], tuple[Any, Callable[[str], int]]] | None = None,
    run_server: Callable[[Any, str, int], None] | None = None,
) -> None:
    """The four-step startup order of design §What the engine reads:

    1. manifest read and view load — refuse to serve a view the engine
       cannot interpret;
    2. model loaded, then warmed with one throwaway encode — the 7.2 s
       cold load is paid here, never on the user's first question;
    3. the surface assembled over the loaded components;
    4. bind last: a listener that accepts before the warm promises a
       budget it cannot meet.

    The loopback check runs first of all — a configuration that can never
    serve must not pay the model load before being refused (9.2).
    """
    import logging

    from dawmans.answer.http.app import ProviderRegistry, _stored_secrets, create_app
    from dawmans.answer.http.guard import ensure_loopback_bind
    from dawmans.answer.provider.credentials import SecretFilter
    from dawmans.answer.state.null import NullStateSource
    from dawmans.answer.turn import TurnPipeline
    from dawmans.answer.view import ViewWatcher

    ensure_loopback_bind(host)

    # 6.11's backstop travels with the wiring: every handler this process
    # logs through drops any record containing a stored secret.
    handler = logging.StreamHandler()
    handler.addFilter(SecretFilter(_stored_secrets))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    watcher = ViewWatcher(index_dir)

    embedder, count_tokens = (load_model or _load_model)()
    list(embedder.embed(["warm-up"]))  # the throwaway encode

    registry = ProviderRegistry(_provider_factory(local_url))
    pipeline = TurnPipeline(
        watcher=watcher,
        binding=registry.binding,
        state_source=NullStateSource(),
        embedder=embedder,
        count_tokens=count_tokens,
    )
    app = create_app(
        watcher=watcher,
        port=port,
        registry=registry,
        manuals_root=manuals_root,
        pipeline=pipeline,
        static_dir=static_dir,
    )

    if run_server is None:
        import uvicorn

        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        run_server(app, host, port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dawmans")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Run the loopback answer-engine API")
    serve.add_argument("--index-dir", type=Path, default=Path("index"))
    serve.add_argument("--manuals-root", type=Path, default=Path("manuals"))
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument(
        "--static-dir",
        type=Path,
        default=None,
        help="Built browser surface to mount at / (defaults to web/build when present)",
    )
    serve.add_argument("--local-url", default=DEFAULT_LOCAL_URL)
    args = parser.parse_args(argv)
    if args.command == "serve":
        static_dir = args.static_dir
        if static_dir is None and Path("web/build").is_dir():
            static_dir = Path("web/build")
        run_serve(
            index_dir=args.index_dir,
            manuals_root=args.manuals_root,
            host=args.host,
            port=args.port,
            static_dir=static_dir,
            local_url=args.local_url,
        )


if __name__ == "__main__":
    main()
