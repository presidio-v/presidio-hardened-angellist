"""Tests for memo generation (templated fallback + LLM delegation)."""

from __future__ import annotations

from presidio_angellist.models import Deal, Founder, Scorecard
from presidio_angellist.triage.memo import write_memo
from presidio_angellist.triage.rubric import score_deal


def _deal() -> Deal:
    return Deal(
        company="Nimbus",
        one_liner="Robots for 3PLs.",
        stage="pre-seed",
        instrument="SAFE",
        valuation_cap=10_000_000,
        lead="Jane Okafor",
        website="https://nimbus.example.com",
        founders=[Founder("Marcus Lee")],
        raw_text="paying customers MRR",
    )


class _FakeLLM:
    def __init__(self, available: bool = True, raises: bool = False) -> None:
        self._available = available
        self._raises = raises
        self.called = False

    def available(self) -> bool:
        return self._available

    def write_memo(self, deal: Deal, scorecard: Scorecard) -> str:
        self.called = True
        if self._raises:
            raise RuntimeError("boom")
        return "LLM MEMO"


class TestTemplatedMemo:
    def test_contains_company_and_tier(self) -> None:
        deal = _deal()
        sc = score_deal(deal)
        memo = write_memo(deal, sc, llm=None)
        assert "Nimbus" in memo
        assert sc.tier in memo

    def test_contains_diligence_checklist(self) -> None:
        deal = _deal()
        memo = write_memo(deal, score_deal(deal), llm=None)
        assert "Diligence Checklist" in memo
        assert "- [ ]" in memo

    def test_missing_cap_adds_terms_item(self) -> None:
        deal = _deal()
        deal.valuation_cap = None
        memo = write_memo(deal, score_deal(deal), llm=None)
        assert "round terms" in memo


class TestLLMDelegation:
    def test_uses_llm_when_available(self) -> None:
        deal = _deal()
        fake = _FakeLLM(available=True)
        memo = write_memo(deal, score_deal(deal), llm=fake)
        assert memo == "LLM MEMO"
        assert fake.called

    def test_falls_back_when_unavailable(self) -> None:
        deal = _deal()
        memo = write_memo(deal, score_deal(deal), llm=_FakeLLM(available=False))
        assert "Triage Memo" in memo

    def test_falls_back_on_llm_error(self) -> None:
        deal = _deal()
        memo = write_memo(deal, score_deal(deal), llm=_FakeLLM(available=True, raises=True))
        assert "Triage Memo" in memo
