"""The provider configuration routes (9.4, 9.8, 9.11, 6.3, 6.15).

Five operations: GET /provider, PUT /provider, PUT and DELETE
/provider/credential, POST /provider/test. Every response carries at
most the masked form — the raw key appears in no response body and no
log record from any of them. Selecting the shared backend without the
disclosure acknowledgement records nothing (6.15), and test-provider
reports reachability without synthesising a turn.

keyring is stubbed as in test_credentials.py: the live Keychain path
never runs in CI.
"""

import logging

import pytest
from http_fixtures import StubWatcher, default_view, get, make_app, request

from dawmans.answer.provider import credentials
from dawmans.answer.provider.base import (
    ProbeResult,
    ProviderKind,
    ProviderStatus,
    mask,
)

KEY = "sk-ant-secret-8765"


class KeyringStub:
    def __init__(self):
        self.passwords = {}

    def set_password(self, service, account, password):
        self.passwords[(service, account)] = password

    def get_password(self, service, account):
        return self.passwords.get((service, account))

    def delete_password(self, service, account):
        self.passwords.pop((service, account), None)


@pytest.fixture
def keychain(monkeypatch):
    stub = KeyringStub()
    monkeypatch.setattr(credentials, "keyring", stub)
    return stub


class StubProvider:
    def __init__(self, kind, model=None, *, masked=None, reachable=True, detail=None):
        self.kind = kind
        self.model = model
        self.masked = masked
        self.reachable = reachable
        self.detail = detail
        self.probes = 0
        self.streams = 0
        self.acknowledged = False

    def acknowledge(self):
        self.acknowledged = True

    def status(self):
        return ProviderStatus(
            kind=self.kind,
            configured=True,
            masked=self.masked,
            model=self.model,
            requires_disclosure_ack=(
                self.kind is ProviderKind.SHARED_BACKEND and not self.acknowledged
            ),
        )

    async def probe(self):
        self.probes += 1
        return ProbeResult(reachable=self.reachable, detail=self.detail)

    async def stream(self, req):
        self.streams += 1
        yield "never"


def provider_app(*, probe_detail=None):
    """The guarded app with a registry whose factory records what it
    constructs — a keyed kind with no stored key is unconstructable."""
    from dawmans.answer.http.app import ProviderRegistry

    created = []

    def factory(kind, model):
        if kind is ProviderKind.KEYED_HOSTED:
            key = credentials.read_key(kind)
            if key is None:
                return None
            provider = StubProvider(kind, model, masked=mask(key), detail=probe_detail)
        else:
            provider = StubProvider(kind, model, detail=probe_detail)
        created.append(provider)
        return provider

    registry = ProviderRegistry(factory)
    app = make_app(StubWatcher(default_view()), registry=registry, secrets=lambda: [KEY])
    return app, registry, created


class TestGetProvider:
    def test_nothing_selected_reports_unconfigured(self, keychain):
        app, _, _ = provider_app()
        body = get(app, "/provider").json()
        assert body["kind"] is None
        assert body["configured"] is False
        assert body["masked"] is None

    def test_a_selected_keyed_provider_reports_the_masked_form_only(self, keychain):
        keychain.set_password("dawmans", "anthropic", KEY)
        app, _, _ = provider_app()
        request(app, "PUT", "/provider", json_body={"kind": "keyed-hosted"})
        response = get(app, "/provider")
        assert response.json()["masked"] == "…8765"
        assert KEY not in response.text


class TestSetProvider:
    def test_selecting_a_kind_records_it(self, keychain):
        app, registry, created = provider_app()
        response = request(app, "PUT", "/provider", json_body={"kind": "local", "model": "llama-3"})
        assert response.status_code == 200
        assert registry.kind is ProviderKind.LOCAL
        assert registry.model == "llama-3"
        assert len(created) == 1
        body = get(app, "/provider").json()
        assert body["kind"] == "local"
        assert body["configured"] is True

    def test_an_unknown_kind_is_422(self, keychain):
        app, registry, _ = provider_app()
        response = request(app, "PUT", "/provider", json_body={"kind": "telepathy"})
        assert response.status_code == 422
        assert response.json()["rejected"] == "unknown-provider-kind"
        assert registry.kind is None

    def test_shared_backend_without_ack_returns_the_gate_and_records_nothing(self, keychain):
        # 6.15: the disclosure comes before the selection, so an unacked
        # PUT changes nothing — not the kind, not the provider.
        app, registry, created = provider_app()
        request(app, "PUT", "/provider", json_body={"kind": "local"})
        response = request(app, "PUT", "/provider", json_body={"kind": "shared-backend"})
        assert response.status_code == 200
        body = response.json()
        assert body["requires_disclosure_ack"] is True
        assert body["recorded"] is False
        assert registry.kind is ProviderKind.LOCAL
        assert len(created) == 1

    def test_shared_backend_with_ack_records_and_acknowledges(self, keychain):
        app, registry, created = provider_app()
        response = request(
            app,
            "PUT",
            "/provider",
            json_body={"kind": "shared-backend", "disclosure_ack": True},
        )
        assert response.status_code == 200
        assert registry.kind is ProviderKind.SHARED_BACKEND
        assert registry.acknowledged is True
        assert created[-1].acknowledged is True


class TestCredentialRoutes:
    def test_set_credential_stores_and_returns_masked_only(self, keychain):
        app, _, _ = provider_app()
        response = request(app, "PUT", "/provider/credential", json_body={"key": KEY})
        assert response.status_code == 200
        assert response.json()["masked"] == "…8765"
        assert KEY not in response.text
        assert keychain.passwords[("dawmans", "anthropic")] == KEY

    def test_a_missing_key_is_422(self, keychain):
        response = request(provider_app()[0], "PUT", "/provider/credential", json_body={})
        assert response.status_code == 422

    def test_clear_credential_removes_the_stored_key(self, keychain):
        keychain.set_password("dawmans", "anthropic", KEY)
        app, _, _ = provider_app()
        response = request(app, "DELETE", "/provider/credential")
        assert response.status_code == 200
        assert response.json()["masked"] is None
        assert ("dawmans", "anthropic") not in keychain.passwords

    def test_a_credential_change_rebuilds_the_keyed_provider_for_the_next_turn(self, keychain):
        # 6.3: the change applies from the next turn without restart —
        # the registry re-constructs, and binding() reads the new state.
        keychain.set_password("dawmans", "anthropic", KEY)
        app, registry, created = provider_app()
        request(app, "PUT", "/provider", json_body={"kind": "keyed-hosted"})
        assert len(created) == 1
        request(app, "PUT", "/provider/credential", json_body={"key": "sk-ant-other-4321"})
        assert len(created) == 2
        assert created[-1].masked == "…4321"
        assert registry.binding().credential_stored is True

    def test_a_keyed_kind_with_no_stored_key_is_selectable_but_unconfigured(self, keychain):
        # The pre-flight gate turns this into provider-unconfigured /
        # missing-credential; selection itself is not refused.
        app, registry, created = provider_app()
        response = request(app, "PUT", "/provider", json_body={"kind": "keyed-hosted"})
        assert response.status_code == 200
        assert created == []
        binding = registry.binding()
        assert binding.requires_key is True
        assert binding.credential_stored is False
        assert binding.provider is None


class TestTestProvider:
    def test_reports_reachability_without_synthesising_a_turn(self, keychain):
        app, _, created = provider_app()
        request(app, "PUT", "/provider", json_body={"kind": "local"})
        response = request(app, "POST", "/provider/test")
        assert response.json()["reachable"] is True
        assert created[0].probes == 1
        assert created[0].streams == 0

    def test_no_provider_selected_reports_unreachable(self, keychain):
        app, _, _ = provider_app()
        body = request(app, "POST", "/provider/test").json()
        assert body["reachable"] is False

    def test_a_probe_detail_carrying_the_key_is_dropped_not_redacted(self, keychain):
        app, _, _ = provider_app(probe_detail=f"http 401 for {KEY}")
        request(app, "PUT", "/provider", json_body={"kind": "local"})
        response = request(app, "POST", "/provider/test")
        assert response.json()["detail"] is None
        assert KEY not in response.text


class TestNoCredentialAnywhere:
    def test_the_raw_key_reaches_no_response_and_no_log_record(self, keychain, caplog):
        # 9.11 / 6.11: credentials at no level — captured at DEBUG, so a
        # record at any level would be seen here.
        keychain.set_password("dawmans", "anthropic", KEY)
        app, _, _ = provider_app()
        with caplog.at_level(logging.DEBUG):
            responses = [
                request(app, "PUT", "/provider", json_body={"kind": "keyed-hosted"}),
                get(app, "/provider"),
                request(app, "PUT", "/provider/credential", json_body={"key": KEY}),
                request(app, "POST", "/provider/test"),
                request(app, "DELETE", "/provider/credential"),
            ]
        for response in responses:
            assert KEY not in response.text
        for record in caplog.records:
            assert KEY not in record.getMessage()
