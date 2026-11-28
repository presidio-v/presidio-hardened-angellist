"""Advisor refresh: payload minimisation and draft handling (model mocked, no network)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from digest_helpers import AGG_CONTENT, CSV, VINTAGE_CONTENT

from presidio_angellist.digest.csvload import in_years, load_positions
from presidio_angellist.digest.refresh import (
    DEFAULT_REFRESH_MODEL,
    PayloadLeakError,
    RefreshError,
    assert_minimised,
    build_payload,
    call_model,
    protected_amounts,
    protected_terms,
    refresh_content,
    resolve_model,
    scrub,
    select_companies,
)

INVESTOR = "Example Holdings LLC"

GOOD_REPLY = {
    "one_liner": "Does a thing.",
    "status": "On track",
    "signals": ["2026-10: pilot announced."],
    "forecast": "Seed extension likely.",
    "key_risk": "Competition.",
    "watch": "Customer count.",
    "p_up_round": 0.3,
    "sources": [{"label": "Site", "url": "https://example.com/news"}],
}


def _block(kind, text=""):
    return SimpleNamespace(type=kind, text=text)


class FakeClient:
    """Records every request; replies with canned responses."""

    def __init__(self, replies=None):
        self.calls: list[dict] = []
        self.replies = list(replies or [])
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs, default=str)))
        if self.replies:
            r = self.replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[_block("server_tool_use"), _block("text", json.dumps(GOOD_REPLY))],
        )


def _positions():
    return load_positions(CSV)


def _leaky_prior(tmp_path, positions):
    """Approved content whose editorial text mentions amounts, leads and the investor."""
    data = json.loads(VINTAGE_CONTENT.read_text())
    for name, entry in data["companies"].items():
        entry["signals"] = [
            f"Our $5,000 ticket via Example Syndicate at a $18,000,000 cap; {INVESTOR} holds it.",
            "Marked at 0.97x after fees; Sample Capital passed; 5000 USD in.",
        ]
        entry["forecast"] = (
            f"Placeholder Partners expects 2.5x; round of $6M on EX-26-Fund, {name}."
        )
    path = tmp_path / "content.json"
    path.write_text(json.dumps(data))
    return path


# ---------------------------------------------------------------- minimisation


def test_scrub_removes_amounts_multiples_and_names():
    terms = protected_terms(_positions(), [INVESTOR])
    out = scrub(
        "Example Syndicate put $5,000 at a $18M cap, 25k more, 12,500 later, 0.97x.", terms
    )
    for bad in ("Example Syndicate", "5,000", "18M", "25k", "12,500", "0.97x"):
        assert bad not in out
    assert "[redacted]" in out and "[amount]" in out


def test_payload_from_fixture_csv_contains_no_amounts_or_lead_names(tmp_path):
    """The requirement test: build every request from the fixture CSV and inspect it."""
    positions = _positions()
    vintage = in_years(positions, 2026)
    approved = _leaky_prior(tmp_path, vintage)
    client = FakeClient()
    rep = refresh_content(
        approved,
        vintage,
        mode="vintage",
        client=client,
        all_positions=positions,
        extra_terms=[INVESTOR, "Example Ventures"],
    )
    assert len(client.calls) == len({p.name for p in vintage}) == len(rep.updated)
    sent = json.dumps(client.calls)
    leads = {p.lead for p in positions if p.lead}
    funds = {p.fund_name for p in positions if p.fund_name}
    for name in leads | funds | {INVESTOR, "Example Ventures"}:
        assert name.lower() not in sent.lower(), name
    for p in positions:
        for v in (p.invested, p.unrealized, p.realized, p.round_size, p.cap, p.post_cap):
            if v and v >= 1000:
                for form in (f"{int(v):,}", f"${int(v):,}", f"{int(v) // 1000}k"):
                    assert form not in sent, form
    for multiple in ("0.97x", "2.5x", "24.5"):
        assert multiple not in sent
    # The only per-company facts sent: name, market label, stage label.
    user = client.calls[0]["messages"][0]["content"]
    assert "Kestrel Nuclear" in user and '"sector": "Energy"' in user and '"stage": "Seed"' in user


def test_build_payload_allowlist_only():
    ps = [p for p in _positions() if p.name == "Kestrel Nuclear"]
    prior = {"signals": ["x"], "forecast": "y", "p_up_round": 0.9, "sources": [{"url": "u"}]}
    payload = build_payload("Kestrel Nuclear", ps, prior, [])
    d = json.loads(payload.to_json())
    assert set(d) == {"company", "sector", "stage", "prior_editorial"}
    assert set(d["prior_editorial"]) == {"signals", "forecast"}
    assert build_payload("Unknown", [], None, []).sector == ""


def test_assert_minimised_fails_closed():
    with pytest.raises(PayloadLeakError):
        assert_minimised('{"company": "x via Example Syndicate"}', ["Example Syndicate"], [])
    with pytest.raises(PayloadLeakError):
        assert_minimised('{"note": "ticket 5,000"}', [], ["5,000"])
    assert_minimised('{"note": "15,000 and 2026"}', [], ["5,000", "2026.5"])
    amounts = protected_amounts(_positions())
    assert "5,000" in amounts and "5k" in amounts and "18M" in amounts


def test_company_whose_name_contains_a_lead_is_skipped(tmp_path):
    positions = _positions()
    victim = positions[-1]
    victim.name = "Sample Capital Robotics"
    client = FakeClient()
    rep = refresh_content(
        tmp_path / "content.json", [victim], mode="vintage", client=client, all_positions=positions
    )
    assert client.calls == [] and "Sample Capital Robotics" in rep.skipped


# ---------------------------------------------------------------- model call


def test_call_model_request_shape_and_pause_turn():
    paused = SimpleNamespace(stop_reason="pause_turn", content=[_block("server_tool_use")])
    client = FakeClient([paused])
    payload = build_payload("Kestrel Nuclear", [], None, [])
    out = call_model(client, payload, model="claude-fable-5-2", max_searches=3)
    assert out["status"] == "On track"
    first, second = client.calls
    assert first["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
    assert first["fallbacks"] == "default" and first["betas"] == [
        "server-side-fallback-2026-07-01"
    ]
    assert len(second["messages"]) == 2 and second["messages"][1]["role"] == "assistant"
    assert "<untrusted_deal_content>" in first["messages"][0]["content"]


def test_call_model_other_model_has_no_fallback_param():
    client = FakeClient()
    call_model(client, build_payload("A", [], None, []), model="claude-opus-4-8")
    assert "fallbacks" not in client.calls[0] and "betas" not in client.calls[0]


@pytest.mark.parametrize(
    ("reply", "match"),
    [
        (SimpleNamespace(stop_reason="refusal", content=[]), "declined"),
        (SimpleNamespace(stop_reason="end_turn", content=[_block("text", "no json")]), "JSON"),
        (SimpleNamespace(stop_reason="end_turn", content=[]), "no text"),
    ],
)
def test_call_model_errors(reply, match):
    with pytest.raises(RefreshError, match=match):
        call_model(FakeClient([reply]), build_payload("A", [], None, []), model="m")


def test_call_model_pause_budget_exhausted():
    paused = SimpleNamespace(stop_reason="pause_turn", content=[])
    with pytest.raises(RefreshError, match="resume budget"):
        call_model(FakeClient([paused] * 10), build_payload("A", [], None, []), model="m")


def test_resolve_model(monkeypatch):
    monkeypatch.delenv("ANGELTRIAGE_DIGEST_MODEL", raising=False)
    assert resolve_model(None) == DEFAULT_REFRESH_MODEL
    monkeypatch.setenv("ANGELTRIAGE_DIGEST_MODEL", "claude-opus-5-5")
    assert resolve_model(None) == "claude-opus-5-5"
    assert resolve_model("x") == "x"


# ---------------------------------------------------------------- drafts


def test_refresh_writes_draft_never_approved(tmp_path):
    approved = tmp_path / "agg-2017-2020.json"
    original = AGG_CONTENT.read_text()
    approved.write_text(original)
    positions = _positions()
    band = in_years(positions, 2017, 2020)
    bad = SimpleNamespace(stop_reason="refusal", content=[])
    client = FakeClient([bad])
    rep = refresh_content(approved, band, mode="aggregate", client=client, all_positions=positions)
    assert approved.read_text() == original
    assert rep.draft.name == "agg-2017-2020.draft.json"
    assert (rep.draft.stat().st_mode & 0o777) == 0o600
    draft = json.loads(rep.draft.read_text())
    assert draft["_draft"]["skipped"] == ["Acme Robotics"]
    assert draft["holdings"]["Granite Ledger"]["status"] == "On track"
    assert "p_up_round" not in draft["holdings"]["Granite Ledger"]
    assert draft["holdings"]["Acme Robotics"]["status"] == "Ahead"  # prior kept
    assert draft["numbers_used"] == {}


def test_refresh_sdk_error_skips_company(tmp_path):
    anthropic = pytest.importorskip("anthropic")
    # Built without __init__ so the test does not depend on the SDK's HTTP library.
    err = anthropic.APIConnectionError.__new__(anthropic.APIConnectionError)
    positions = in_years(_positions(), 2026)
    rep = refresh_content(
        tmp_path / "content.json", positions[:1], mode="vintage", client=FakeClient([err])
    )
    assert list(rep.skipped.values()) == ["APIConnectionError"]


def test_select_companies_and_bad_mode(tmp_path):
    band = in_years(_positions(), 2017, 2020)
    assert select_companies("aggregate", band, {}, top_n=2) == ["Acme Robotics", "Iris Orbit"]
    assert select_companies("aggregate", band, {"holdings": {"X": {}}}) == ["X"]
    with pytest.raises(RefreshError):
        refresh_content(tmp_path / "c.json", band, mode="weird", client=FakeClient())
    bad = tmp_path / "broken.json"
    bad.write_text("{nope")
    with pytest.raises(RefreshError):
        refresh_content(bad, band, mode="aggregate", client=FakeClient())
