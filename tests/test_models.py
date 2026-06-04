"""Tests for the dataclass models."""

from __future__ import annotations

from presidio_angellist.models import Deal, DimensionScore, Founder, Scorecard, TriageResult


class TestDeal:
    def test_to_dict_drops_raw_text(self) -> None:
        deal = Deal(company="X", raw_text="lots of text")
        data = deal.to_dict()
        assert "raw_text" not in data
        assert data["company"] == "X"


class TestScorecard:
    def test_composite_zero_weight(self) -> None:
        sc = Scorecard(dimensions=[DimensionScore("a", 5, 0, "n")])
        assert sc.composite == 0.0

    def test_composite_and_tier(self) -> None:
        sc = Scorecard(dimensions=[DimensionScore("a", 5, 1, "n")])
        assert sc.composite == 100.0
        assert sc.tier == "Strong lead"

    def test_low_score_is_pass(self) -> None:
        sc = Scorecard(dimensions=[DimensionScore("a", 1, 1, "n")])
        assert sc.tier == "Pass"


class TestTriageResult:
    def test_to_dict_nests_everything(self) -> None:
        deal = Deal(company="X", founders=[Founder("A B", role="CEO")])
        sc = Scorecard(dimensions=[DimensionScore("a", 3, 1, "n")], risk_flags=["flag"])
        result = TriageResult(deal=deal, scorecard=sc, memo="memo text")
        data = result.to_dict()
        assert data["deal"]["company"] == "X"
        assert data["scorecard"]["risk_flags"] == ["flag"]
        assert data["memo"] == "memo text"
