"""Tests for the SQLite-backed deal queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from presidio_angellist.models import Deal, DimensionScore, Scorecard, TriageResult
from presidio_angellist.store import (
    DealStore,
    DealStoreError,
    dedup_key,
    default_db_path,
)

if TYPE_CHECKING:
    from pathlib import Path


def _result(
    company: str, score: float, website: str | None = None, memo: str | None = None
) -> TriageResult:
    deal = Deal(company=company, website=website, raw_text="x")
    sc = Scorecard(dimensions=[DimensionScore("team", score / 20.0, 1.0, "n")])
    return TriageResult(deal=deal, scorecard=sc, memo=memo)


class TestDedupKey:
    def test_domain_strips_www(self) -> None:
        assert dedup_key("Acme", "https://www.acme.com/about") == "domain:acme.com"

    def test_domain_without_scheme(self) -> None:
        assert dedup_key("Acme", "acme.com") == "domain:acme.com"

    def test_falls_back_to_company_name(self) -> None:
        assert dedup_key("Acme, Inc.", None) == "name:acme inc"


class TestDefaultDbPath:
    def test_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom.db"
        monkeypatch.setenv("ANGELTRIAGE_DB", str(custom))
        assert default_db_path() == custom

    def test_default_under_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANGELTRIAGE_DB", raising=False)
        assert default_db_path().name == "deals.db"


class TestSaveAndDedup:
    def test_insert_new(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            saved, is_new = store.save(_result("Acme", 80, "https://acme.com"))
            assert is_new is True
            assert saved.id == 1
            assert saved.status == "new"
            assert saved.times_seen == 1

    def test_resave_same_domain_dedups(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            store.save(_result("Acme", 80, "https://acme.com"))
            saved, is_new = store.save(_result("Acme Inc", 82, "https://www.acme.com"))
            assert is_new is False
            assert saved.times_seen == 2
            assert len(store.list()) == 1

    def test_status_preserved_across_resave(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            saved, _ = store.save(_result("Acme", 80, "https://acme.com"))
            store.set_status(saved.id, "passed")
            saved2, _ = store.save(_result("Acme", 90, "https://acme.com"))
            assert saved2.status == "passed"

    def test_different_domains_are_separate(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            store.save(_result("Acme", 80, "https://acme.com"))
            store.save(_result("Acme", 80, "https://acme.io"))
            assert len(store.list()) == 2

    def test_dedup_by_company_when_no_website(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            store.save(_result("Stealth Co", 50))
            store.save(_result("Stealth Co", 55))
            assert len(store.list()) == 1


class TestListAndFilters:
    def test_ranked_by_composite_desc(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            store.save(_result("Low", 40, "https://low.com"))
            store.save(_result("High", 90, "https://high.com"))
            rows = store.list()
            assert [r.company for r in rows] == ["High", "Low"]

    def test_filter_by_status(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            a, _ = store.save(_result("A", 80, "https://a.com"))
            store.save(_result("B", 70, "https://b.com"))
            store.set_status(a.id, "tracking")
            assert [r.company for r in store.list(status="tracking")] == ["A"]
            assert [r.company for r in store.list(status="new")] == ["B"]

    def test_filter_by_tier(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            store.save(_result("A", 90, "https://a.com"))  # Strong lead
            store.save(_result("B", 10, "https://b.com"))  # Pass
            rows = store.list(tier="Pass")
            assert [r.company for r in rows] == ["B"]

    def test_limit(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            for i in range(5):
                store.save(_result(f"C{i}", 50 + i, f"https://c{i}.com"))
            assert len(store.list(limit=2)) == 2

    def test_invalid_status_filter_raises(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:  # noqa: SIM117 - 3.9-safe nesting
            with pytest.raises(DealStoreError, match="unknown status"):
                store.list(status="bogus")


class TestStatusOps:
    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            assert store.get(999) is None

    def test_set_status_invalid_value(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            saved, _ = store.save(_result("A", 80, "https://a.com"))
            with pytest.raises(DealStoreError, match="unknown status"):
                store.set_status(saved.id, "bogus")

    def test_set_status_missing_id(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:  # noqa: SIM117 - 3.9-safe nesting
            with pytest.raises(DealStoreError, match="no deal with id"):
                store.set_status(123, "passed")

    def test_persists_across_connections(self, tmp_path: Path) -> None:
        db = tmp_path / "d.db"
        with DealStore(db) as store:
            store.save(_result("A", 80, "https://a.com"))
        with DealStore(db) as store2:
            assert len(store2.list()) == 1

    def test_saved_deal_to_dict(self, tmp_path: Path) -> None:
        with DealStore(tmp_path / "d.db") as store:
            saved, _ = store.save(_result("A", 80, "https://a.com", memo="m"))
            data = saved.to_dict()
            assert data["company"] == "A"
            assert data["status"] == "new"
            assert "times_seen" in data
