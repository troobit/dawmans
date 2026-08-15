"""`dawmans serve`: the four-step startup order and the wiring (9.1, 9.2).

Design §What the engine reads fixes the order — manifest read and view
load, model loaded and warmed with one throwaway encode, bind last. A
listener that accepts before the warm promises a budget it cannot meet,
and the 7.2 s cold load must not be paid on the user's first question.

`run_serve` takes the model loader and the server runner as seams, so the
order is observable without loading the real model or opening a socket;
`ViewWatcher` is wrapped in place to record the view step.
"""

import json

import numpy as np
import pytest
from http_fixtures import request
from test_end_to_end import LIVE, default_index

import dawmans.answer.view as view_module
from dawmans.answer.provider import credentials
from dawmans.cli import main, run_serve


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


class FakeEmbedder:
    def __init__(self, events):
        self._events = events

    def embed(self, texts):
        self._events.append("warm")
        return [np.zeros(4, dtype=np.float32) for _ in texts]


class Harness:
    """run_serve with every external effect recorded instead of performed."""

    def __init__(self, monkeypatch):
        self.events = []
        self.bound = {}
        real_watcher = view_module.ViewWatcher

        def recording_watcher(index_dir):
            self.events.append("view")
            return real_watcher(index_dir)

        monkeypatch.setattr(view_module, "ViewWatcher", recording_watcher)

    def load_model(self):
        self.events.append("model")
        return FakeEmbedder(self.events), lambda text: len(text.split())

    def run_server(self, app, host, port):
        self.events.append("bind")
        self.bound.update(app=app, host=host, port=port)


class TestStartupOrder:
    def test_view_then_model_then_warm_then_bind(self, tmp_path, monkeypatch, keychain):
        harness = Harness(monkeypatch)
        run_serve(
            index_dir=default_index(tmp_path),
            manuals_root=tmp_path / "manuals",
            port=8901,
            load_model=harness.load_model,
            run_server=harness.run_server,
        )
        # The 7.2 s cold load is paid here, before the listener exists —
        # never on the first question.
        assert harness.events == ["view", "model", "warm", "bind"]
        assert harness.bound["host"] == "127.0.0.1"
        assert harness.bound["port"] == 8901

    def test_a_present_but_unreadable_manifest_refuses_to_serve(
        self, tmp_path, monkeypatch, keychain
    ):
        harness = Harness(monkeypatch)
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        (index_dir / "manifest.json").write_text("not json at all")
        with pytest.raises(view_module.ViewLoadError):
            run_serve(
                index_dir=index_dir,
                manuals_root=tmp_path / "manuals",
                load_model=harness.load_model,
                run_server=harness.run_server,
            )
        assert "bind" not in harness.events

    def test_a_missing_manifest_starts_and_serves_an_empty_corpus(
        self, tmp_path, monkeypatch, keychain
    ):
        # No manifest is the corpus honestly holding nothing — the turn's
        # corpus-empty gate, not a startup refusal.
        harness = Harness(monkeypatch)
        run_serve(
            index_dir=tmp_path / "index",
            manuals_root=tmp_path / "manuals",
            load_model=harness.load_model,
            run_server=harness.run_server,
        )
        assert harness.events[-1] == "bind"
        response = request(harness.bound["app"], "GET", "/sources", base_url="http://127.0.0.1:8722")
        assert response.status_code == 200
        assert response.json()["sources"] == []

    def test_a_non_loopback_bind_exits_naming_the_address(
        self, tmp_path, monkeypatch, keychain
    ):
        harness = Harness(monkeypatch)
        with pytest.raises(SystemExit) as fault:
            run_serve(
                index_dir=default_index(tmp_path),
                manuals_root=tmp_path / "manuals",
                host="192.168.1.10",
                load_model=harness.load_model,
                run_server=harness.run_server,
            )
        assert "192.168.1.10" in str(fault.value)
        # There is no fallback bind — and no model load was paid for a
        # configuration that can never serve.
        assert "bind" not in harness.events


class TestWiredSurface:
    def base(self, port):
        return f"http://127.0.0.1:{port}"

    @pytest.fixture
    def surface(self, tmp_path, monkeypatch, keychain):
        harness = Harness(monkeypatch)
        manuals = tmp_path / "manuals"
        manuals.mkdir()
        run_serve(
            index_dir=default_index(tmp_path),
            manuals_root=manuals,
            port=8901,
            load_model=harness.load_model,
            run_server=harness.run_server,
        )
        return harness.bound["app"], self.base(8901)

    def test_every_operation_group_is_routed(self, surface):
        app, base = surface
        assert request(app, "GET", "/sources", base_url=base).status_code == 200
        assert (
            request(app, "GET", f"/passages/{LIVE}%23p1", base_url=base).status_code == 200
        )
        assert request(app, "GET", "/provider", base_url=base).status_code == 200
        # The document route is wired: a JSON not-found body, not a
        # route-less plain 404 — the file itself is absent here.
        response = request(app, "GET", f"/sources/{LIVE}/document", base_url=base)
        assert response.status_code == 404
        assert response.json()["not_found"] == "document"

    def test_a_turn_with_no_provider_selected_is_provider_unconfigured(self, surface):
        app, base = surface
        response = request(
            app,
            "POST",
            "/turn",
            json_body={"question": "why is track 3 silent", "sources": [LIVE]},
            base_url=base,
        )
        assert response.status_code == 200
        assert '"outcome": "provider-unconfigured"' in response.text
        assert '"reason": "no-provider-kind"' in response.text

    def test_selecting_the_local_provider_applies_without_restart(self, surface):
        app, base = surface
        response = request(
            app, "PUT", "/provider", json_body={"kind": "local"}, base_url=base
        )
        assert response.status_code == 200
        body = response.json()
        assert body["recorded"] is True
        assert body["configured"] is True
        assert body["masked"] is None

    def test_a_keyed_kind_without_a_stored_key_gates_as_missing_credential(self, surface):
        app, base = surface
        put = request(
            app, "PUT", "/provider", json_body={"kind": "keyed-hosted"}, base_url=base
        )
        assert put.status_code == 200
        response = request(
            app,
            "POST",
            "/turn",
            json_body={"question": "why", "sources": [LIVE]},
            base_url=base,
        )
        assert '"outcome": "provider-unconfigured"' in response.text
        assert '"reason": "missing-credential"' in response.text

    def test_a_stored_key_constructs_the_keyed_provider(self, surface, keychain):
        app, base = surface
        request(
            app,
            "PUT",
            "/provider/credential",
            json_body={"key": "sk-ant-e2e-1234"},
            base_url=base,
        )
        put = request(
            app, "PUT", "/provider", json_body={"kind": "keyed-hosted"}, base_url=base
        )
        body = put.json()
        assert body["configured"] is True
        assert body["masked"] == "…1234"
        assert keychain.passwords[("dawmans", "anthropic")] == "sk-ant-e2e-1234"


class TestCli:
    def test_serve_arguments_reach_the_wiring(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr("dawmans.cli.run_serve", lambda **kwargs: captured.update(kwargs))
        main(
            [
                "serve",
                "--index-dir",
                str(tmp_path / "index"),
                "--manuals-root",
                str(tmp_path / "manuals"),
                "--port",
                "9001",
            ]
        )
        assert captured["index_dir"] == tmp_path / "index"
        assert captured["manuals_root"] == tmp_path / "manuals"
        assert captured["port"] == 9001

    def test_serve_defaults(self, monkeypatch):
        captured = {}
        monkeypatch.setattr("dawmans.cli.run_serve", lambda **kwargs: captured.update(kwargs))
        main(["serve"])
        assert str(captured["index_dir"]) == "index"
        assert str(captured["manuals_root"]) == "manuals"


def test_the_startup_test_fixture_round_trips_through_json(tmp_path):
    # Guard on the fixture itself: the manifest the tests write is the
    # shape `ViewWatcher` loads, so a fixture drift fails here first.
    index_dir = default_index(tmp_path)
    manifest = json.loads((index_dir / "manifest.json").read_text())
    assert manifest["index_version"] == 1
