"""Tests for IMAP intake, using an injected fake IMAP client (no network)."""

from __future__ import annotations

import imaplib
from pathlib import Path

import pytest

from presidio_angellist.intake.imap import (
    ImapConfig,
    ImapError,
    _first_rfc822,
    fetch_imap,
    imap_config_from_env,
)
from presidio_angellist.pipeline import triage_imap

FIXTURES = Path(__file__).parent / "fixtures"
RAW = (FIXTURES / "deal_complete.eml").read_bytes()


class FakeIMAP:
    """Minimal stand-in for imaplib.IMAP4_SSL."""

    def __init__(
        self,
        messages: list[bytes],
        *,
        fail_login: bool = False,
        select_ok: bool = True,
        search_ok: bool = True,
    ) -> None:
        self.messages = messages
        self.fail_login = fail_login
        self.select_ok = select_ok
        self.search_ok = search_ok
        self.search_args: tuple = ()
        self.selected: tuple | None = None
        self.closed = False
        self.logged_out = False

    def login(self, user: str, password: str):
        if self.fail_login:
            raise imaplib.IMAP4.error("authentication failed")
        return ("OK", [b""])

    def select(self, folder: str, readonly: bool = False):
        self.selected = (folder, readonly)
        return ("OK" if self.select_ok else "NO", [b"1"])

    def search(self, charset, *criteria):
        self.search_args = criteria
        if not self.search_ok:
            return ("NO", [b""])
        ids = " ".join(str(i + 1) for i in range(len(self.messages))).encode()
        return ("OK", [ids])

    def fetch(self, num, spec):
        idx = int(num) - 1
        body = self.messages[idx]
        header = f"{int(num)} (RFC822 {{{len(body)}}}".encode()
        return ("OK", [(header, body), b")"])

    def close(self):
        self.closed = True

    def logout(self):
        self.logged_out = True
        return ("BYE", [b""])


def _cfg(**kw) -> ImapConfig:
    base = {"host": "imap.example.com", "user": "u", "password": "p"}
    base.update(kw)
    return ImapConfig(**base)


class TestFetch:
    def test_returns_raw_messages(self) -> None:
        fake = FakeIMAP([RAW])
        msgs = fetch_imap(_cfg(), connection_factory=lambda: fake)
        assert len(msgs) == 1
        assert msgs[0].raw == RAW
        assert msgs[0].uid == "1"

    def test_select_is_readonly(self) -> None:
        fake = FakeIMAP([RAW])
        fetch_imap(_cfg(folder="Deals"), connection_factory=lambda: fake)
        assert fake.selected == ("Deals", True)

    def test_closes_and_logs_out(self) -> None:
        fake = FakeIMAP([RAW])
        fetch_imap(_cfg(), connection_factory=lambda: fake)
        assert fake.closed and fake.logged_out

    def test_unseen_is_default_criteria(self) -> None:
        fake = FakeIMAP([RAW])
        fetch_imap(_cfg(), connection_factory=lambda: fake)
        assert fake.search_args == ("UNSEEN",)

    def test_all_and_from_criteria(self) -> None:
        fake = FakeIMAP([RAW])
        fetch_imap(_cfg(unseen=False, from_addr="deals@vc.com"), connection_factory=lambda: fake)
        assert fake.search_args == ("ALL", "FROM", "deals@vc.com")

    def test_since_criteria(self) -> None:
        fake = FakeIMAP([RAW])
        fetch_imap(_cfg(since="01-Jun-2026"), connection_factory=lambda: fake)
        assert "SINCE" in fake.search_args and "01-Jun-2026" in fake.search_args

    def test_limit_takes_most_recent(self) -> None:
        fake = FakeIMAP([RAW, RAW, RAW])
        msgs = fetch_imap(_cfg(limit=1), connection_factory=lambda: fake)
        assert [m.uid for m in msgs] == ["3"]

    def test_empty_mailbox(self) -> None:
        fake = FakeIMAP([])
        assert fetch_imap(_cfg(), connection_factory=lambda: fake) == []


class TestErrors:
    def test_login_failure(self) -> None:
        fake = FakeIMAP([RAW], fail_login=True)
        with pytest.raises(ImapError, match="IMAP error"):
            fetch_imap(_cfg(), connection_factory=lambda: fake)

    def test_select_not_ok(self) -> None:
        fake = FakeIMAP([RAW], select_ok=False)
        with pytest.raises(ImapError, match="could not open folder"):
            fetch_imap(_cfg(folder="Nope"), connection_factory=lambda: fake)

    def test_search_not_ok(self) -> None:
        fake = FakeIMAP([RAW], search_ok=False)
        with pytest.raises(ImapError, match="search failed"):
            fetch_imap(_cfg(), connection_factory=lambda: fake)

    def test_connect_failure(self) -> None:
        def boom():
            raise OSError("connection refused")

        with pytest.raises(ImapError, match="could not connect"):
            fetch_imap(_cfg(), connection_factory=boom)


class TestTeardownAndFetch:
    def test_teardown_errors_are_swallowed(self) -> None:
        fake = FakeIMAP([RAW])
        fake.close = lambda: (_ for _ in ()).throw(OSError("boom"))  # type: ignore[assignment]
        # best-effort teardown must not mask a successful fetch
        msgs = fetch_imap(_cfg(), connection_factory=lambda: fake)
        assert len(msgs) == 1

    def test_fetch_not_ok_is_skipped(self) -> None:
        fake = FakeIMAP([RAW])
        fake.fetch = lambda num, spec: ("NO", [b""])  # type: ignore[assignment]
        assert fetch_imap(_cfg(), connection_factory=lambda: fake) == []


class TestFirstRfc822:
    def test_extracts_bytes_from_tuple(self) -> None:
        data = [(b"1 (RFC822 {3}", b"abc"), b")"]
        assert _first_rfc822(data) == b"abc"

    def test_none_when_no_bytes(self) -> None:
        assert _first_rfc822([b")"]) is None
        assert _first_rfc822(None) is None


class TestConfigFromEnv:
    def test_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAP_HOST", "imap.mail.me.com")
        monkeypatch.setenv("IMAP_USER", "me@icloud.com")
        monkeypatch.setenv("IMAP_PASSWORD", "app-specific")
        monkeypatch.setenv("IMAP_PORT", "993")
        cfg = imap_config_from_env(folder="Deals", unseen=False, limit=5)
        assert cfg.host == "imap.mail.me.com"
        assert cfg.port == 993
        assert cfg.folder == "Deals"
        assert cfg.unseen is False
        assert cfg.limit == 5
        assert cfg.use_ssl is True

    def test_missing_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(ImapError, match="missing IMAP credentials"):
            imap_config_from_env()

    def test_bad_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAP_HOST", "h")
        monkeypatch.setenv("IMAP_USER", "u")
        monkeypatch.setenv("IMAP_PASSWORD", "p")
        monkeypatch.setenv("IMAP_PORT", "notaport")
        with pytest.raises(ImapError, match="IMAP_PORT must be an integer"):
            imap_config_from_env()

    def test_ssl_disabled_and_default_folder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAP_HOST", "h")
        monkeypatch.setenv("IMAP_USER", "u")
        monkeypatch.setenv("IMAP_PASSWORD", "p")
        monkeypatch.setenv("IMAP_SSL", "false")
        monkeypatch.delenv("IMAP_FOLDER", raising=False)
        cfg = imap_config_from_env()
        assert cfg.use_ssl is False
        assert cfg.folder == "INBOX"


class TestTriageImap:
    def test_fetches_and_triages(self) -> None:
        results = triage_imap(_cfg(), connection_factory=lambda: FakeIMAP([RAW]))
        assert len(results) == 1
        assert results[0].deal.company == "Nimbus Robotics"
        assert results[0].deal.source == "imap:1"
