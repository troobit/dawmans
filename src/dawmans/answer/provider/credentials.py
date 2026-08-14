"""Keychain-backed credential store via keyring; masked reads.

Keys live in the macOS Keychain under service `dawmans`, one account per
provider kind (Decision 6) — never in a configuration file, environment
variable or log (6.11). Every read path returns the last-4 masked form
or None; the full value's one reader is a provider's client constructor,
which calls read_key() exactly once at construction (6.13).

The logging filter is a backstop, not the mechanism: 6.11 is held by
never placing a key in a record, and the filter additionally drops any
record whose formatted output carries a stored secret. The same
predicate filters `detail` (CONTRACTS §4) — engine wording only, no
credential material.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

import keyring

from dawmans.answer.provider.base import ProviderKind, mask

SERVICE = "dawmans"

# One account per kind that requires a key. Keyless kinds hold none —
# a configured keyless provider is already fully configured (6.4).
_ACCOUNTS = {ProviderKind.KEYED_HOSTED: "anthropic"}


def account_for(kind: ProviderKind) -> str | None:
    return _ACCOUNTS.get(kind)


def store_key(kind: ProviderKind, key: str) -> None:
    account = _ACCOUNTS[kind]
    keyring.set_password(SERVICE, account, key)


def read_key(kind: ProviderKind) -> str | None:
    """The full value. One caller: the provider's client constructor."""
    account = account_for(kind)
    if account is None:
        return None
    return keyring.get_password(SERVICE, account)


def masked_key(kind: ProviderKind) -> str | None:
    """6.13: the read form for every path that is not the constructor."""
    key = read_key(kind)
    return None if key is None else mask(key)


def clear_key(kind: ProviderKind) -> None:
    account = account_for(kind)
    if account is not None:
        keyring.delete_password(SERVICE, account)


Secrets = Callable[[], Iterable[str]] | Iterable[str]


def _resolve(secrets: Secrets) -> tuple[str, ...]:
    resolved = secrets() if callable(secrets) else secrets
    return tuple(secret for secret in resolved if secret)


def _tainted(text: str, secrets: Secrets) -> bool:
    return any(secret in text for secret in _resolve(secrets))


class SecretFilter(logging.Filter):
    """Drops any record whose formatted output contains a stored secret.

    Attached alongside 9.11's level policy: question, answer and passage
    text log at DEBUG only, credentials at no level — this filter is the
    no-level guarantee's backstop.
    """

    def __init__(self, secrets: Secrets) -> None:
        super().__init__()
        self._secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        return not _tainted(record.getMessage(), self._secrets)


def scrub_detail(detail: str | None, secrets: Secrets) -> str | None:
    """The same predicate applied to CONTRACTS §4 `detail`: a detail that
    would carry credential material is dropped, never redacted-in-place —
    partial redaction still leaks length and shape."""
    if detail is None or _tainted(detail, secrets):
        return None
    return detail
