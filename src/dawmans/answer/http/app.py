"""Starlette app: routes and the SSE turn stream.

The route table is design §The local HTTP surface; every request passes
the Host/Origin guard (9.3). Each corpus route runs the same stat change
check as a turn, so a passage removed by a re-ingest stops resolving
immediately rather than at the next question.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dawmans.answer.envelope import VENDOR_MANUAL
from dawmans.answer.http.guard import HostOriginGuard
from dawmans.answer.provider import credentials
from dawmans.answer.provider.base import Provider, ProviderKind, mask, requires_key
from dawmans.answer.provider.credentials import scrub_detail
from dawmans.answer.turn import ProviderBinding, TurnEvent, TurnPipeline

logger = logging.getLogger("dawmans.answer.http")

QUESTION_LIMIT = 1000  # 9.12
TURN_STREAM_VERSION = "dawmans/turn-stream/1"  # 9.15

# The engine's own wording for a manifest fault. The ViewLoadError text
# names the manifest's path, and no filesystem path may appear in any
# payload — so the report is this fixed notice, never the raw fault.
MANIFEST_FAULT_NOTICE = (
    "a newer corpus manifest could not be read; the last good view is still being served"
)


def _not_found(kind: str, **fields: Any) -> JSONResponse:
    return JSONResponse({"not_found": kind, **fields}, status_code=404)


def _drop_absent(mapping: dict[str, Any]) -> dict[str, Any]:
    # CONTRACTS: absent means absent — a None field is not carried.
    return {key: value for key, value in mapping.items() if value is not None}


def _event_payload(event: TurnEvent) -> Any:
    """One §4b event's wire payload, per the table's Payload column."""
    data = event.data
    match event.name:
        case "scope_dropped" | "suggested_sources":
            return [asdict(member) for member in data]
        case "outcome" | "citation" | "timings" | "required_device" | "required_manual":
            return _drop_absent(asdict(data))
        case "direct_answer" | "body_delta":
            return {"text": data}
        case "cause" | "narrowing":
            return asdict(data)
        case "contributing_sources":
            return {"sources": list(data)}
        case "uncovered_parts":
            return {"parts": list(data)}
        case "ungrounded":
            return {"ungrounded": True}
        case "framing":
            return {"framing": data}
    return data  # done — already {"complete": True}


async def _sse(events: AsyncIterator[TurnEvent]) -> AsyncIterator[bytes]:
    try:
        async for event in events:
            payload = json.dumps(_event_payload(event))
            yield f"event: {event.name}\ndata: {payload}\n\n".encode()
    finally:
        # Closing this encoder closes the turn generator, whose own
        # finally releases the provider stream — a close, not a drain.
        await events.aclose()


class _TurnStreamResponse(StreamingResponse):
    """StreamingResponse never finalises its body iterator; on a caller
    disconnect the turn generator would only be closed by GC, which is
    what 9.10 forbids relying on — cancellation must be immediate."""

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()


class ProviderRegistry:
    """The mutable provider selection: the routes write it, a turn reads
    it once at start through `binding()` — which is what makes a change
    apply to the next turn without restart (6.3).

    `factory(kind, model)` constructs the provider for a recorded
    selection, or None where it cannot be constructed (a keyed kind with
    no stored key); the serve wiring supplies the real constructors."""

    def __init__(self, factory: Callable[[ProviderKind, str | None], Provider | None]) -> None:
        self._factory = factory
        self.kind: ProviderKind | None = None
        self.model: str | None = None
        self.provider: Provider | None = None
        self.acknowledged = False

    def select(self, kind: ProviderKind, model: str | None = None, *, disclosure_ack: bool = False) -> bool:
        """Record a selection. Returns False — recording nothing — where
        the shared backend is selected before its disclosure is
        acknowledged (6.15)."""
        if kind is ProviderKind.SHARED_BACKEND and not disclosure_ack and not self.acknowledged:
            return False
        self.kind = kind
        self.model = model
        if kind is ProviderKind.SHARED_BACKEND and disclosure_ack:
            self.acknowledged = True
        self.provider = self._factory(kind, model)
        if (
            kind is ProviderKind.SHARED_BACKEND
            and self.acknowledged
            and self.provider is not None
            and hasattr(self.provider, "acknowledge")
        ):
            # The instance's own gate is defence in depth behind the
            # pre-flight one; an acknowledged registry unlocks both.
            self.provider.acknowledge()
        return True

    def refresh(self) -> None:
        """A credential change applies from the next turn (6.3): the
        keyed provider is re-constructed so its constructor — the full
        value's only reader — re-reads the store."""
        if self.kind is not None and requires_key(self.kind):
            self.provider = self._factory(self.kind, self.model)

    def binding(self) -> ProviderBinding:
        """What one turn reads about the provider, once, at turn start."""
        if self.kind is None:
            return ProviderBinding()
        return ProviderBinding(
            provider=self.provider,
            kind=str(self.kind),
            requires_key=requires_key(self.kind),
            credential_stored=credentials.masked_key(self.kind) is not None,
            requires_ack=self.kind is ProviderKind.SHARED_BACKEND,
            acknowledged=self.acknowledged,
            name=str(self.kind),
        )

    def status_payload(self) -> dict[str, Any]:
        """9.8: at most the masked form, on every read path."""
        if self.kind is None:
            return {
                "kind": None,
                "configured": False,
                "masked": None,
                "model": None,
                "prompt_cache": None,
                "requires_disclosure_ack": False,
            }
        if self.provider is not None:
            status = self.provider.status()
            return {
                "kind": str(status.kind),
                "configured": status.configured,
                "masked": status.masked,
                "model": status.model,
                "prompt_cache": status.prompt_cache,
                "requires_disclosure_ack": status.requires_disclosure_ack,
            }
        return {
            "kind": str(self.kind),
            "configured": False,
            "masked": credentials.masked_key(self.kind),
            "model": self.model,
            "prompt_cache": None,
            "requires_disclosure_ack": (
                self.kind is ProviderKind.SHARED_BACKEND and not self.acknowledged
            ),
        }


def _stored_secrets() -> Iterable[str | None]:
    # The SecretFilter/scrub predicate needs the full values to compare
    # against; this closure is not a read *interface* — nothing returns
    # what it yields (6.13).
    return (credentials.read_key(ProviderKind.KEYED_HOSTED),)


def create_app(
    *,
    watcher: Any,
    port: int,
    registry: ProviderRegistry | None = None,
    secrets: Callable[[], Iterable[str | None]] = _stored_secrets,
    manuals_root: Path | None = None,
    pipeline: TurnPipeline | None = None,
    static_dir: Path | None = None,
) -> Starlette:
    """Assemble the guarded surface over the injected components; the
    `dawmans serve` wiring constructs them (phase 9)."""

    async def get_passage(request: Request) -> JSONResponse:
        # 3.4: a dict lookup, routed on the source_id prefix — a passage
        # whose source left the corpus never resolves to a substitute.
        watcher.check()
        view = watcher.view
        passage_id = request.path_params["passage_id"]
        source_id = passage_id.rsplit("#", 1)[0]
        if view is None or source_id not in view.sources_by_id:
            return _not_found("passage", passage_id=passage_id)
        record = view.passages_by_id.get(passage_id)
        if record is None:
            return _not_found("passage", passage_id=passage_id)
        return JSONResponse(dict(record))

    async def list_sources(request: Request) -> JSONResponse:
        # 9.5–9.7: the records for both kinds, and both gap reports —
        # relayed from the corpus's own publication, never derived here.
        watcher.check()
        view = watcher.view
        gaps = view.gaps if view is not None else {}
        return JSONResponse(
            {
                "sources": [
                    dict(record) for record in (view.sources if view is not None else ())
                ],
                "owned_but_undocumented": list(gaps.get("owned_but_undocumented", ())),
                "documented_but_unconfirmed": list(
                    gaps.get("documented_but_unconfirmed", ())
                ),
                "manifest_fault": (
                    MANIFEST_FAULT_NOTICE if watcher.manifest_fault else None
                ),
            }
        )

    async def serve_document(request: Request):
        # 9.4: no path from the caller reaches the filesystem — the
        # loaded index is the allowlist, and the filename is rebuilt from
        # the record's own fields under Decision 2's grammar.
        watcher.check()
        view = watcher.view
        source_id = request.path_params["source_id"]
        record = view.sources_by_id.get(source_id) if view is not None else None
        if record is None or record.get("kind") != VENDOR_MANUAL:
            return _not_found("document", source_id=source_id)
        # doc_version is stored without its leading v (manual-corpus 2.7):
        # one reconstruction rule, no `_vv1.0_`.
        filename = (
            f"{record['vendor']}_{record['product']}_{record['doctype']}"
            f"_v{record['doc_version']}_{record['lang']}.pdf"
        )
        target = (manuals_root / filename).resolve()
        if not target.is_relative_to(manuals_root.resolve()):
            return _not_found("document", source_id=source_id)
        if not target.is_file() or not os.access(target, os.R_OK):
            # The caller degrades the citation to its string form (UI
            # 5.11), never to a broken action.
            return _not_found("document", source_id=source_id)
        # Inline — no Content-Disposition filename, which would download
        # the file and silently defeat #page=N. FileResponse streams
        # bytes and honours Range; nothing parses the PDF.
        return FileResponse(target, media_type="application/pdf")

    # -- submit-question (9.14, 9.15): SSE over the POST response -------

    async def submit_turn(request: Request):
        body = await _json_body(request)
        question = body.get("question")
        if not isinstance(question, str) or not question.strip():
            # A request rejection, not a turn: no outcome field (9.12).
            return JSONResponse({"rejected": "question-missing"}, status_code=422)
        if len(question) > QUESTION_LIMIT:
            # 9.12: rejected before a turn exists — never truncated, never
            # an envelope, never a §6 outcome.
            return JSONResponse(
                {
                    "rejected": "question-too-long",
                    "limit": QUESTION_LIMIT,
                    "received": len(question),
                },
                status_code=422,
            )
        sources = body.get("sources")
        if sources is not None and not (
            isinstance(sources, list)
            and all(isinstance(member, str) for member in sources)
        ):
            return JSONResponse({"rejected": "sources-invalid"}, status_code=422)
        logger.debug("turn question: %s", question)  # 9.11: DEBUG only
        # Resolving the conversation here also mints the id the caller
        # needs for a follow-up; pipeline.turn() sends the 9.13 supersede
        # signal at call time, before the stream is first read.
        conversation = pipeline.conversations.get(body.get("conversation_id"))
        events = pipeline.turn(
            question, sources=sources, conversation_id=conversation.id
        )
        return _TurnStreamResponse(
            _sse(events),
            media_type="text/event-stream",
            headers={
                # 9.15: readable before the first body byte.
                "dawmans-turn-stream": TURN_STREAM_VERSION,
                "dawmans-conversation-id": conversation.id,
                "cache-control": "no-store",
            },
        )

    # -- the provider operations (9.4): masked-only throughout (9.8) ----

    async def get_provider(request: Request) -> JSONResponse:
        return JSONResponse(registry.status_payload())

    async def put_provider(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            kind = ProviderKind(body.get("kind"))
        except ValueError:
            return JSONResponse(
                {"rejected": "unknown-provider-kind", "kind": body.get("kind")},
                status_code=422,
            )
        recorded = registry.select(
            kind, body.get("model"), disclosure_ack=bool(body.get("disclosure_ack"))
        )
        if not recorded:
            # 6.15: the disclosure precedes the selection — nothing is
            # recorded until the caller acknowledges it.
            return JSONResponse({"requires_disclosure_ack": True, "recorded": False})
        return JSONResponse({**registry.status_payload(), "recorded": True})

    async def put_credential(request: Request) -> JSONResponse:
        body = await _json_body(request)
        key = body.get("key")
        if not isinstance(key, str) or not key:
            return JSONResponse({"rejected": "credential-missing"}, status_code=422)
        credentials.store_key(ProviderKind.KEYED_HOSTED, key)
        registry.refresh()
        return JSONResponse({"masked": mask(key)})

    async def delete_credential(request: Request) -> JSONResponse:
        credentials.clear_key(ProviderKind.KEYED_HOSTED)
        registry.refresh()
        return JSONResponse({"masked": None})

    async def test_provider(request: Request) -> JSONResponse:
        # Reachability only, never a synthesised turn (9.4); the detail
        # runs the same drop-not-redact predicate as every §4 detail.
        if registry.provider is None:
            return JSONResponse({"reachable": False, "detail": "no provider selected"})
        probe = await registry.provider.probe()
        return JSONResponse(
            {"reachable": probe.reachable, "detail": scrub_detail(probe.detail, secrets)}
        )

    routes = [
        Route("/sources", list_sources),
        Route("/passages/{passage_id:path}", get_passage),
    ]
    if pipeline is not None:
        routes.append(Route("/turn", submit_turn, methods=["POST"]))
    if manuals_root is not None:
        routes.append(Route("/sources/{source_id:path}/document", serve_document))
    if registry is not None:
        routes += [
            Route("/provider", get_provider, methods=["GET"]),
            Route("/provider", put_provider, methods=["PUT"]),
            Route("/provider/credential", put_credential, methods=["PUT"]),
            Route("/provider/credential", delete_credential, methods=["DELETE"]),
            Route("/provider/test", test_provider, methods=["POST"]),
        ]
    if static_dir is not None:
        # Mounted last so the API routes match first: the built surface at
        # / is what makes the page same-origin (design §Binding and headers).
        routes.append(Mount("/", app=StaticFiles(directory=static_dir, html=True)))
    return Starlette(routes=routes, middleware=[Middleware(HostOriginGuard, port=port)])


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
