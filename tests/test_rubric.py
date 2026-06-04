"""Tests for the deterministic triage rubric and scorecard model."""

from __future__ import annotations

from presidio_angellist.models import Deal, Founder
from presidio_angellist.triage.rubric import DEFAULT_WEIGHTS, score_deal


def _strong_deal() -> Deal:
    return Deal(
        company="Nimbus",
        one_liner="Warehouse automation robots for SMB 3PLs.",
        stage="pre-seed",
        instrument="SAFE",
        valuation_cap=10_000_000,
        round_size=1_200_000,
        allocation=250_000,
        lead="Jane Okafor",
        website="https://nimbus.example.com",
        traction="$30k MRR across 4 paying customers, 22% month-over-month",
        founders=[Founder("Marcus Lee"), Founder("Priya Nair")],
        raw_text="ex-Amazon MIT $30k MRR paying customers month-over-month",
    )


class TestComposite:
    def test_strong_deal_scores_high(self) -> None:
        sc = score_deal(_strong_deal())
        assert sc.composite >= 75
        assert sc.tier == "Strong lead"

    def test_empty_deal_has_no_flags_crash(self) -> None:
        sc = score_deal(Deal(company="X"))
        assert 0 <= sc.composite <= 100
        assert sc.tier in {"Pass", "Track", "Dig deeper", "Strong lead"}

    def test_all_dimensions_present(self) -> None:
        sc = score_deal(_strong_deal())
        names = {d.name for d in sc.dimensions}
        assert names == set(DEFAULT_WEIGHTS)


class TestRiskFlags:
    def test_solo_founder_flagged(self) -> None:
        deal = _strong_deal()
        deal.founders = [Founder("Solo Person")]
        sc = score_deal(deal)
        assert any("Solo founder" in f for f in sc.risk_flags)

    def test_missing_cap_flagged(self) -> None:
        deal = _strong_deal()
        deal.valuation_cap = None
        sc = score_deal(deal)
        assert any("valuation cap" in f for f in sc.risk_flags)

    def test_high_cap_for_stage_flagged(self) -> None:
        deal = _strong_deal()
        deal.valuation_cap = 50_000_000  # very high for pre-seed
        sc = score_deal(deal)
        assert any("high" in f for f in sc.risk_flags)

    def test_no_traction_flagged(self) -> None:
        deal = Deal(company="X", raw_text="no numbers here")
        sc = score_deal(deal)
        assert any("traction" in f.lower() for f in sc.risk_flags)

    def test_no_website_flagged(self) -> None:
        deal = _strong_deal()
        deal.website = None
        sc = score_deal(deal)
        assert any("website" in f.lower() for f in sc.risk_flags)


class TestWeights:
    def test_custom_weights_change_score(self) -> None:
        deal = _strong_deal()
        base = score_deal(deal).composite
        skewed = score_deal(
            deal,
            weights={"team": 1.0, "market": 0.0, "traction": 0.0, "terms": 0.0, "syndicate": 0.0},
        ).composite
        assert skewed != base


class TestScorecardSerialization:
    def test_to_dict_round_trip(self) -> None:
        sc = score_deal(_strong_deal())
        data = sc.to_dict()
        assert data["tier"] == sc.tier
        assert data["composite"] == sc.composite
        assert len(data["dimensions"]) == len(sc.dimensions)


class TestRubricConfig:
    def test_config_takes_precedence_over_weights(self) -> None:
        from presidio_angellist.rubric_config import RubricConfig

        deal = _strong_deal()
        cfg = RubricConfig.default()
        cfg.weights = {"team": 1.0, "market": 0.0, "traction": 0.0, "terms": 0.0, "syndicate": 0.0}
        # weights arg should be ignored when config is given
        sc = score_deal(
            deal,
            config=cfg,
            weights={"team": 0.0, "market": 1.0, "traction": 0.0, "terms": 0.0, "syndicate": 0.0},
        )
        team = next(d for d in sc.dimensions if d.name == "team")
        assert team.weight == 1.0

    def test_risk_penalty_lowers_composite(self) -> None:
        from presidio_angellist.rubric_config import RubricConfig

        deal = _strong_deal()
        deal.website = None  # guarantees at least one risk flag
        base = score_deal(deal).composite
        cfg = RubricConfig.default()
        cfg.risk_penalty = 10.0
        penalized = score_deal(deal, config=cfg).composite
        assert penalized < base

    def test_custom_cap_ceiling_triggers_flag(self) -> None:
        from presidio_angellist.rubric_config import RubricConfig

        deal = _strong_deal()  # $10M cap, pre-seed
        cfg = RubricConfig.default()
        cfg.cap_ceilings = {"pre-seed": 8_000_000, "seed": 30_000_000}
        sc = score_deal(deal, config=cfg)
        assert any("high" in f for f in sc.risk_flags)

    def test_custom_tier_thresholds(self) -> None:
        from presidio_angellist.rubric_config import RubricConfig

        deal = _strong_deal()
        cfg = RubricConfig.default()
        cfg.tier_thresholds = [(95.0, "Strong lead"), (0.0, "Pass")]
        sc = score_deal(deal, config=cfg)
        # strong deal scores ~83, below the raised 95 bar -> Pass
        assert sc.tier == "Pass"
