"""Tests for the IMAP watch loop (no real clock or network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from presidio_angellist.intake.imap import ImapConfig
from presidio_angellist.store import DealStore
from presidio_angellist.watch import PollResult, message_identity, poll_once, watch

FIXTURES = Path(__file__).parent / "fixtures"
RAW_A = (FIXTURES / "deal_complete.eml").read_bytes()
RAW_B = (FIXTURES / "deal_sparse.eml").read_bytes()


class FakeIMAP:
    def __init__(self, messages: list[bytes], *, search_ok: bool = True) -> None:
        self.messages = messages
        self.search_ok = search_ok

    def login(self, u, p):
        return ("OK", [b""])

    def select(self, folder, readonly=False):
        return ("OK", [b"1"])

    def search(self, charset, *criteria):
        if not self.search_ok:
            return ("NO", [b""])
        ids = " ".join(str(i + 1) for i in range(len(self.messages))).encode()
        return ("OK", [ids])

    def fetch(self, num, spec):
        return ("OK", [(b"hdr", self.messages[int(num) - 1]), b")"])

    def close(self):
        pass

    def logout(self):
        return ("BYE", [b""])


def _cfg() -> ImapConfig:
    return ImapConfig(host="h", user="u", password="p")  # noqa: S106 - test stub


class TestMessageIdentity:
    def test_uses_message_id_header(self) -> None:
        raw = b"Message-ID: <abc@example.com>\r\nSubject: t\r\n\r\nbody"
        assert message_identity(raw) == "<abc@example.com>"

    def test_falls_back_to_content_hash(self) -> None:
        ident = message_identity(b"Subject: no id\r\n\r\nbody")
        assert ident.startswith("sha256:")

    def test_hash_is_stable(self) -> None:
        raw = b"Subject: x\r\n\r\nsame"
        assert message_identity(raw) == message_identity(raw)


class TestPollOnce:
    def test_processes_and_saves_new(self, tmp_path: Path) -> None:
        seen: set[str] = set()
        with DealStore(tmp_path / "d.db") as store:
            res = poll_once(_cfg(), store, seen=seen, connection_factory=lambda: FakeIMAP([RAW_A]))
        assert res.fetched == 1
        assert res.processed == 1
        assert res.new_saved == 1
        assert res.results[0].deal.company == "Nimbus Robotics"

    def test_skips_already_seen(self, tmp_path: Path) -> None:
        seen = {message_identity(RAW_A)}
        with DealStore(tmp_path / "d.db") as store:
            res = poll_once(_cfg(), store, seen=seen, connection_factory=lambda: FakeIMAP([RAW_A]))
        assert res.fetched == 1
        assert res.processed == 0


class TestWatchLoop:
    def test_dedups_across_cycles(self, tmp_path: Path) -> None:
        cycles: list[PollResult] = []
        with DealStore(tmp_path / "d.db") as store:
            total = watch(
                _cfg(),
                store,
                interval=0,
                max_cycles=3,
                sleeper=lambda s: None,
                connection_factory=lambda: FakeIMAP([RAW_A]),
                on_cycle=lambda n, res: cycles.append(res),
            )
            assert total == 1
            assert [c.processed for c in cycles] == [1, 0, 0]
            assert len(store.list()) == 1

    def test_sleeper_called_between_not_after(self, tmp_path: Path) -> None:
        sleeps: list[float] = []
        with DealStore(tmp_path / "d.db") as store:
            watch(
                _cfg(),
                store,
                interval=42.0,
                max_cycles=3,
                sleeper=sleeps.append,
                connection_factory=lambda: FakeIMAP([RAW_A]),
            )
        # 3 cycles -> sleeps after cycles 1 and 2 only
        assert sleeps == [42.0, 42.0]

    def test_first_cycle_error_propagates(self, tmp_path: Path) -> None:
        from presidio_angellist.intake.imap import ImapError

        with DealStore(tmp_path / "d.db") as store, pytest.raises(ImapError):
            watch(
                _cfg(),
                store,
                max_cycles=2,
                sleeper=lambda s: None,
                connection_factory=lambda: FakeIMAP([RAW_A], search_ok=False),
            )

    def test_later_cycle_error_tolerated(self, tmp_path: Path) -> None:
        errors: list[Exception] = []
        state = {"n": 0}

        def factory() -> FakeIMAP:
            state["n"] += 1
            if state["n"] == 1:
                return FakeIMAP([RAW_A])
            if state["n"] == 2:
                return FakeIMAP([RAW_A], search_ok=False)  # raises mid-loop
            return FakeIMAP([RAW_B])

        with DealStore(tmp_path / "d.db") as store:
            total = watch(
                _cfg(),
                store,
                interval=0,
                max_cycles=3,
                sleeper=lambda s: None,
                connection_factory=factory,
                on_error=errors.append,
            )
            assert len(store.list()) == 2
        assert len(errors) == 1  # cycle 2 error reported, loop continued
        assert total == 2  # cycle 1 (A) + cycle 3 (B) saved


class TestPersistProcessed:
    def test_skips_processed_across_runs(self, tmp_path: Path) -> None:
        path = tmp_path / "d.db"
        with DealStore(path) as store:
            r1 = poll_once(
                _cfg(),
                store,
                seen=set(),
                persist_processed=True,
                connection_factory=lambda: FakeIMAP([RAW_A]),
            )
        assert r1.processed == 1 and r1.new_saved == 1 and len(r1.new_results) == 1
        # Fresh session (new seen set); the message must be skipped via the store.
        with DealStore(path) as store:
            r2 = poll_once(
                _cfg(),
                store,
                seen=set(),
                persist_processed=True,
                connection_factory=lambda: FakeIMAP([RAW_A]),
            )
        assert r2.fetched == 1 and r2.processed == 0 and r2.new_results == []

    def test_new_results_track_new_saved(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            res = poll_once(
                _cfg(),
                store,
                seen=set(),
                persist_processed=True,
                connection_factory=lambda: FakeIMAP([RAW_A, RAW_B]),
            )
        assert len(res.results) == 2
        assert len(res.new_results) == res.new_saved
