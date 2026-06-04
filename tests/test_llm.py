"""Tests for the optional Claude layer, with the SDK call mocked out."""

from __future__ import annotations

import json

import pytest

from presidio_angellist.llm import LLMClient, LLMUnavailableError, _deal_from_dict, _first_text


class _Block:
    def __init__(self, block_type: str, text: str = "") -> None:
        self.type = block_type
        self.text = text


class _Usage:
    input_tokens = 10
    output_tokens = 5
    cache_read_input_tokens = 0


class _Resp:
    def __init__(self, blocks: list[_Block]) -> None:
        self.content = blocks
        self.usage = _Usage()


class _Messages:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.last_kwargs: dict | None = None

    def create(self, **kwargs: object) -> _Resp:
        self.last_kwargs = kwargs
        return self._resp


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self.messages = _Messages(resp)


class TestHelpers:
    def test_first_text_returns_text_block(self) -> None:
        resp = _Resp([_Block("thinking"), _Block("text", "hello")])
        assert _first_text(resp) == "hello"

    def test_first_text_raises_without_text(self) -> None:
        with pytest.raises(LLMUnavailableError):
            _first_text(_Resp([_Block("thinking")]))

    def test_deal_from_dict_maps_fields(self) -> None:
        data = {
            "company": "Acme",
            "valuation_cap": 5_000_000,
            "founders": [{"name": "A B", "role": "CEO"}, {"name": ""}],
            "links": ["https://acme.example.com"],
        }
        deal = _deal_from_dict(data, text="raw", source="src")
        assert deal.company == "Acme"
        assert deal.valuation_cap == 5_000_000
        assert [f.name for f in deal.founders] == ["A B"]
        assert deal.extraction_method == "llm"
        assert deal.raw_text == "raw"


class TestAvailability:
    def test_unavailable_without_sdk_or_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert LLMClient().available() is False

    def test_ensure_client_raises_when_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(LLMUnavailableError):
            LLMClient()._ensure_client()


class TestExtractDeal:
    def test_extract_deal_parses_structured_output(self) -> None:
        payload = json.dumps(
            {
                "company": "Nimbus",
                "stage": "pre-seed",
                "valuation_cap": 10_000_000,
                "founders": [{"name": "Marcus Lee", "role": None}],
                "links": [],
            }
        )
        client = LLMClient(api_key="x")
        client._client = _FakeClient(_Resp([_Block("text", payload)]))
        deal = client.extract_deal("some email text", source="deal.eml")
        assert deal.company == "Nimbus"
        assert deal.valuation_cap == 10_000_000
        assert deal.extraction_method == "llm"
        # structured-output schema is passed through
        kwargs = client._client.messages.last_kwargs
        assert kwargs["output_config"]["format"]["type"] == "json_schema"

    def test_write_memo_returns_text(self) -> None:
        client = LLMClient(api_key="x")
        client._client = _FakeClient(_Resp([_Block("text", "  the memo  ")]))
        from presidio_angellist.models import Scorecard

        memo = client.write_memo(
            _deal_from_dict({"company": "X"}, text="t", source=None),
            Scorecard(dimensions=[]),
        )
        assert memo == "the memo"
