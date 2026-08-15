"""Binding and the loopback guard (9.1–9.3, design §Binding and headers).

The bind check runs before uvicorn: a non-loopback address is refused by
raising, never rebound to a fallback. The Host/Origin middleware is what
closes DNS rebinding — an attacker's hostname resolving to 127.0.0.1
reaches the socket but arrives carrying its own Host — and the cross-port
Origin case is what the dev proxy's Origin rewrite exists to avoid, which
a same-port-only test would miss.
"""

import asyncio

import httpx
import pytest
from starlette.responses import JSONResponse

from dawmans.answer.http.guard import HostOriginGuard, ensure_loopback_bind

PORT = 8722


async def _ok(scope, receive, send):
    await JSONResponse({"ok": True})(scope, receive, send)


def request(headers, *, app=None):
    guarded = HostOriginGuard(app or _ok, port=PORT)

    async def go():
        transport = httpx.ASGITransport(app=guarded)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get("/", headers=headers)

    return asyncio.run(go())


class TestBindCheck:
    def test_a_non_loopback_bind_is_refused_naming_address_and_constraint(self):
        with pytest.raises(SystemExit) as refusal:
            ensure_loopback_bind("0.0.0.0")
        # A string code exits with status 1 — non-zero, and the message
        # names both the configured address and the constraint (9.2).
        assert isinstance(refusal.value.code, str)
        assert "0.0.0.0" in refusal.value.code
        assert "loopback" in refusal.value.code

    def test_a_lan_address_is_refused_not_rebound(self):
        # There is no fallback bind: the check raises, it never substitutes.
        with pytest.raises(SystemExit) as refusal:
            ensure_loopback_bind("192.168.1.10")
        assert "192.168.1.10" in refusal.value.code

    def test_loopback_addresses_pass(self):
        assert ensure_loopback_bind("127.0.0.1") is None
        assert ensure_loopback_bind("::1") is None

    def test_a_hostname_is_refused_even_when_it_would_resolve_to_loopback(self):
        # 9.2 checks the configured address against {127.0.0.1, ::1};
        # "localhost" is a name, and a name is resolvable to anything.
        with pytest.raises(SystemExit):
            ensure_loopback_bind("localhost")


class TestHostCheck:
    def test_loopback_hosts_with_the_port_pass(self):
        for host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"):
            response = request({"host": host})
            assert response.status_code == 200, host

    def test_a_foreign_host_is_403(self):
        # DNS rebinding: evil.example resolves to 127.0.0.1, reaches the
        # socket, and arrives carrying the attacker's Host.
        response = request({"host": f"evil.example:{PORT}"})
        assert response.status_code == 403

    def test_a_bare_foreign_host_is_403(self):
        response = request({"host": "evil.example"})
        assert response.status_code == 403

    def test_a_loopback_host_on_another_port_is_403(self):
        response = request({"host": f"127.0.0.1:{PORT + 1}"})
        assert response.status_code == 403


class TestOriginCheck:
    def test_loopback_origins_with_the_port_pass(self):
        for origin in (
            f"http://127.0.0.1:{PORT}",
            f"http://localhost:{PORT}",
            f"http://[::1]:{PORT}",
        ):
            response = request({"host": f"127.0.0.1:{PORT}", "origin": origin})
            assert response.status_code == 200, origin

    def test_no_origin_header_passes(self):
        # curl and same-origin GETs carry no Origin at all.
        response = request({"host": f"127.0.0.1:{PORT}"})
        assert response.status_code == 200

    def test_origin_null_is_403(self):
        # What a file:// page sends.
        response = request({"host": f"127.0.0.1:{PORT}", "origin": "null"})
        assert response.status_code == 403

    def test_a_cross_port_loopback_origin_is_403(self):
        # The dev server's own origin: loopback, wrong port. This is what
        # the Vite proxy's Origin rewrite exists to avoid, and what a
        # same-port-only test would never see fail.
        response = request(
            {"host": f"127.0.0.1:{PORT}", "origin": "http://localhost:5173"}
        )
        assert response.status_code == 403

    def test_a_foreign_origin_is_403(self):
        response = request(
            {"host": f"127.0.0.1:{PORT}", "origin": "https://evil.example"}
        )
        assert response.status_code == 403


class TestRejectionShape:
    def test_the_403_is_machine_readable_with_no_outcome(self):
        # A request rejection, not a turn: CONTRACTS §6 describes turns,
        # so no outcome field may appear.
        for headers in (
            {"host": "evil.example"},
            {"host": f"127.0.0.1:{PORT}", "origin": "null"},
        ):
            response = request(headers)
            body = response.json()
            assert body["rejected"]
            assert "outcome" not in body

    def test_the_rejection_names_the_offending_header(self):
        assert request({"host": "evil.example"}).json()["host"] == "evil.example"
        assert (
            request({"host": f"127.0.0.1:{PORT}", "origin": "null"}).json()["origin"]
            == "null"
        )

    def test_a_rejected_request_never_reaches_the_app(self):
        reached = []

        async def marker_app(scope, receive, send):
            reached.append(scope["path"])
            await JSONResponse({"ok": True})(scope, receive, send)

        request({"host": "evil.example"}, app=marker_app)
        assert reached == []
