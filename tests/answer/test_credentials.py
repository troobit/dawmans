"""Credential storage and masking (6.11–6.13, Decision 6).

keyring is stubbed here: CI never exercises the live Keychain path, and
these tests state that limitation rather than pretending it runs — the
real read is exercised on a developer machine only (prerequisites.md).

Masking is structural: ProviderStatus carries `masked: str | None` and
no field that can hold a full key, every read path returns the last-4
form or None, and the full value has exactly one reader — the provider's
client constructor.
"""

import dataclasses
import logging
import os

import pytest

from dawmans.answer.provider import credentials
from dawmans.answer.provider.anthropic import AnthropicProvider
from dawmans.answer.provider.base import ProviderKind, ProviderStatus, mask
from dawmans.answer.provider.credentials import (
    SERVICE,
    SecretFilter,
    account_for,
    clear_key,
    masked_key,
    read_key,
    scrub_detail,
    store_key,
)

KEY = "sk-ant-secret-8765"


class KeyringStub:
    """Stands in for the macOS Keychain — the live path never runs in CI."""

    def __init__(self):
        self.passwords = {}
        self.calls = []

    def set_password(self, service, account, password):
        self.calls.append(("set", service, account))
        self.passwords[(service, account)] = password

    def get_password(self, service, account):
        self.calls.append(("get", service, account))
        return self.passwords.get((service, account))

    def delete_password(self, service, account):
        self.calls.append(("delete", service, account))
        self.passwords.pop((service, account), None)


@pytest.fixture
def keychain(monkeypatch):
    stub = KeyringStub()
    monkeypatch.setattr(credentials, "keyring", stub)
    return stub


# --- storage (Decision 6) ----------------------------------------------------


def test_stored_under_service_dawmans_one_account_per_kind(keychain):
    assert SERVICE == "dawmans"
    assert account_for(ProviderKind.KEYED_HOSTED) == "anthropic"
    store_key(ProviderKind.KEYED_HOSTED, KEY)
    assert keychain.passwords == {("dawmans", "anthropic"): KEY}


def test_no_key_reaches_a_file_or_the_environment(keychain, tmp_path, monkeypatch):
    # 6.11 / Decision 6: the Keychain is the only container. The store
    # call must not touch the process environment, and writes no file —
    # the stub is the sole channel the key passes through.
    monkeypatch.chdir(tmp_path)
    environ_before = dict(os.environ)
    store_key(ProviderKind.KEYED_HOSTED, KEY)
    assert dict(os.environ) == environ_before
    assert list(tmp_path.iterdir()) == []


def test_keyless_kinds_hold_no_account(keychain):
    for kind in (ProviderKind.LOCAL, ProviderKind.SHARED_BACKEND):
        assert account_for(kind) is None
        assert read_key(kind) is None
        assert masked_key(kind) is None


def test_clear_key_deletes_the_stored_secret(keychain):
    store_key(ProviderKind.KEYED_HOSTED, KEY)
    clear_key(ProviderKind.KEYED_HOSTED)
    assert read_key(ProviderKind.KEYED_HOSTED) is None


# --- masking is structural (6.13) --------------------------------------------


def test_masked_key_is_the_last_four_form_or_none(keychain):
    assert masked_key(ProviderKind.KEYED_HOSTED) is None
    store_key(ProviderKind.KEYED_HOSTED, KEY)
    assert masked_key(ProviderKind.KEYED_HOSTED) == "…8765" == mask(KEY)


def test_provider_status_has_no_field_that_can_hold_a_full_key():
    fields = {field.name for field in dataclasses.fields(ProviderStatus)}
    assert fields == {
        "kind", "configured", "masked", "model", "prompt_cache",
        "requires_disclosure_ack",
    }
    # The masked field is the only credential-shaped one, and a status
    # built from a stored key renders only the last-4 form.
    status = AnthropicProvider(api_key=KEY).status()
    assert status.masked == "…8765"
    assert KEY not in repr(status)


def test_the_full_value_has_exactly_one_reader():
    # 6.12: each provider constructs its own client against its own base
    # URL. The Anthropic constructor takes the key but no URL, and the
    # local constructor takes a URL but no key — no shared
    # send-the-key-to-the-configured-URL path exists to redirect.
    import inspect

    from dawmans.answer.provider.local import LocalProvider

    anthropic_params = inspect.signature(AnthropicProvider.__init__).parameters
    local_params = inspect.signature(LocalProvider.__init__).parameters
    assert "api_key" in anthropic_params and "base_url" not in anthropic_params
    assert "base_url" in local_params and not any("key" in p for p in local_params)


# --- the logging backstop (6.11) ---------------------------------------------


def emitted(records_with, secrets):
    logger = logging.getLogger("dawmans.test.secretfilter")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.filters.clear()
    captured = []

    class Capture(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    logger.addHandler(Capture())
    logger.addFilter(SecretFilter(lambda: secrets))
    for level, message, args in records_with:
        logger.log(level, message, *args)
    return captured


def test_filter_drops_any_record_whose_formatted_output_carries_the_secret():
    records = [
        (logging.DEBUG, f"request sent with {KEY}", ()),
        (logging.INFO, "key is %s", (KEY,)),  # via formatting args too
        (logging.ERROR, f"traceback: auth {KEY} rejected", ()),
    ]
    assert emitted(records, [KEY]) == []


def test_filter_passes_records_without_credential_material():
    records = [
        (logging.INFO, "turn complete in 1200 ms", ()),
        (logging.DEBUG, "masked credential …8765 configured", ()),
    ]
    assert emitted(records, [KEY]) == ["turn complete in 1200 ms",
                                       "masked credential …8765 configured"]


def test_the_same_predicate_filters_detail():
    # detail carries engine wording only — never credential material, and
    # the same predicate that drops a log record drops a tainted detail.
    assert scrub_detail(f"auth failed for {KEY}", [KEY]) is None
    assert scrub_detail("authentication failed (401)", [KEY]) == (
        "authentication failed (401)"
    )
    assert scrub_detail(None, [KEY]) is None
