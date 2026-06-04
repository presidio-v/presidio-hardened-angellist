"""Tests for the end-to-end triage pipeline."""

from __future__ import annotations

from pathlib import Path

from presidio_angellist.models import Deal, TriageResult
from presidio_angellist.pipeline import triage_email

FIXTURES = Path(__file__).parent / "fixtures"


class _StubLLM:
    def __init__(self, available: bool = True, raises: bool = False) -> None:
        self._available = available
        self._raises = raises
        self.extract_called = False

    def available(self) -> bool:
        return self._available

    def extract_deal(self, text: str, source: str | None = None) -> Deal:
        self.extract_called = True
        if self._raises:
            raise RuntimeError("boom")
        return Deal(
            company="LLM Extracted",
            valuation_cap=1,
            instrument="SAFE",
            extraction_method="llm",
            raw_text=text,
            source=source,
        )


class TestPipelineDeterministic:
    def test_returns_triage_result(self) -> None:
        result = triage_email(FIXTURES / "deal_complete.eml")
        assert isinstance(result, TriageResult)
        assert result.deal.company == "Nimbus Robotics"
        assert result.memo is None

    def test_memo_flag_produces_memo(self) -> None:
        result = triage_email(FIXTURES / "deal_complete.eml", memo=True)
        assert result.memo and "Nimbus Robotics" in result.memo

    def test_to_dict_serializable(self) -> None:
        import json

        result = triage_email(FIXTURES / "deal_complete.eml", memo=True)
        # should not raise
        json.dumps(result.to_dict())


class TestPipelineLLMFallback:
    def test_fallback_invoked_on_incomplete_parse(self) -> None:
        llm = _StubLLM(available=True)
        result = triage_email(FIXTURES / "deal_sparse.eml", llm=llm)
        assert llm.extract_called
        assert result.deal.company == "LLM Extracted"

    def test_no_fallback_when_parse_complete(self) -> None:
        llm = _StubLLM(available=True)
        result = triage_email(FIXTURES / "deal_complete.eml", llm=llm)
        assert llm.extract_called is False
        assert result.deal.company == "Nimbus Robotics"

    def test_no_fallback_when_llm_unavailable(self) -> None:
        llm = _StubLLM(available=False)
        triage_email(FIXTURES / "deal_sparse.eml", llm=llm)
        assert llm.extract_called is False

    def test_fallback_error_keeps_deterministic_deal(self) -> None:
        llm = _StubLLM(available=True, raises=True)
        result = triage_email(FIXTURES / "deal_sparse.eml", llm=llm)
        # deterministic (sparse) deal retained, not the LLM one
        assert result.deal.company != "LLM Extracted"
