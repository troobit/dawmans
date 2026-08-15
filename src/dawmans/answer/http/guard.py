"""Loopback binding check and the Host/Origin middleware.

Two guards, one property (9.1): the engine is reachable from the owner's
own browser tab and from nothing else.

- `ensure_loopback_bind` runs before `uvicorn.run` (9.2): a non-loopback
  address is refused by exiting non-zero, naming the address and the
  constraint. There is no fallback bind.
- `HostOriginGuard` (9.3) rejects any request whose `Host` is not the
  loopback service, and any request carrying an `Origin` outside the same
  set. The Host check is the one that closes DNS rebinding: an attacker's
  hostname resolving to 127.0.0.1 reaches the socket but arrives carrying
  the attacker's Host. Rejection is 403 with a machine-readable reason
  and no outcome — a request rejection, not a turn (CONTRACTS §6).
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# 9.2: addresses, not names — "localhost" is resolvable to anything.
LOOPBACK_BINDS = frozenset({"127.0.0.1", "::1"})


def ensure_loopback_bind(host: str) -> None:
    """Refuse a non-loopback bind before the server exists (9.2)."""
    if host not in LOOPBACK_BINDS:
        raise SystemExit(
            f"refusing to bind {host}: dawmans serves on loopback only "
            f"(127.0.0.1 or ::1); there is no fallback bind"
        )


class HostOriginGuard:
    """Pure ASGI middleware enforcing 9.3 on every request."""

    def __init__(self, app: ASGIApp, *, port: int) -> None:
        self._app = app
        hosts = (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")
        self._hosts = frozenset(hosts)
        # A browser only sends a loopback Origin over http; there is no
        # https on this surface, so the scheme set is closed too.
        self._origins = frozenset(f"http://{host}" for host in hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope["headers"]
        }
        host = headers.get("host")
        if host not in self._hosts:
            await self._reject(
                scope, receive, send, {"rejected": "host-not-loopback", "host": host}
            )
            return
        origin = headers.get("origin")
        # Absent is fine (curl, same-origin GET); "null" — a file:// page —
        # and every cross-port loopback origin are not.
        if origin is not None and origin not in self._origins:
            await self._reject(
                scope, receive, send, {"rejected": "origin-not-loopback", "origin": origin}
            )
            return
        await self._app(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, reason: dict) -> None:
        await JSONResponse(reason, status_code=403)(scope, receive, send)
