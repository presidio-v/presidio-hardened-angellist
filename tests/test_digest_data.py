"""CSV loading, gate retro-check and aggregate metrics for the digest."""

from __future__ import annotations

import json
from datetime import date

import pytest
from digest_helpers import CSV, GATE, csv_text

from presidio_angellist.digest.csvload import (
    DigestDataError,
    in_years,
    load_positions,
    newest_export,
    parse_money,
    parse_positions,
)
from presidio_angellist.digest.gate import (
    GateConfigError,
    gate_retro,
    load_gate_config,
    parse_gate_config,
)
from presidio_angellist.digest.metrics import (
    Group,
    aggregate,
    gate_verdict_sentence,
    multiple_bucket,
)

# ---------------------------------------------------------------- CSV


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("$1,000", 1000.0),
        ('"$2,965.68"', None),  # quotes are stripped by the csv module, not here
        ("$2,965.68", 2965.68),
        ("€30,000,000", 30_000_000.0),
        ("Locked", None),
        ("", None),
        (None, None),
        ("-$5", -5.0),
        ("n/a", None),
    ],
)
def test_parse_money(raw, want):
    assert parse_money(raw) == want


def test_load_fixture_tolerates_disclaimer_locked_and_empty_caps():
    ps = load_positions(CSV)
    assert len(ps) == 16
    assert [p.invest_date for p in ps] == sorted(p.invest_date for p in ps)
    fable = next(p for p in ps if p.name == "Fable Foods")
    assert fable.locked and fable.net is None and fable.multiple is None
    assert fable.cap is None and fable.post_cap is None
    assert fable.net_at_cost == fable.invested
    blue = next(p for p in ps if p.name == "Blue Harbor Energy")
    assert blue.post_cap == 9_000_000 + 3_000_000  # pre-money cap counts as pre + round
    assert blue.net == pytest.approx(2700.0)
    assert blue.multiple == pytest.approx(2.7)
    harbor = next(p for p in ps if p.name == "Harbor Keys")
    assert harbor.cap_currency == "EUR"


def test_parse_positions_skips_undated_and_nameless_rows():
    text = csv_text(
        "Alpha,Live,01/02/2020,$1000,$900,$0,$900,0.9,E,L,Syndicate,Direct,Seed,SaaS,F,,safe,,,,,,",
        "Beta,Live,not-a-date,$1000,$900,$0,$900,0.9,E,L,Syndicate,Direct,Seed,SaaS,F,,safe,,,,,,",
        ",Live,01/02/2020,$1000,$900,$0,$900,0.9,E,L,Syndicate,Direct,Seed,SaaS,F,,safe,,,,,,",
        "Gamma,Live,2021-03-04,$500,$0,$0,$0,0,E,L,Syndicate,Direct,Seed,SaaS,F,,safe,,,,,,",
    )
    ps = parse_positions(text)
    assert [p.name for p in ps] == ["Alpha", "Gamma"]
    assert ps[1].multiple == 0.0


def test_missing_header_raises():
    with pytest.raises(DigestDataError):
        parse_positions("just,some,csv\n1,2,3\n")


def test_load_positions_missing_file(tmp_path):
    with pytest.raises(DigestDataError):
        load_positions(tmp_path / "nope.csv")


def test_newest_export_by_name(tmp_path):
    for d in ("2026_11_10", "2026_11_24", "2025_01_01"):
        (tmp_path / f"someone_angellist_investments_{d}.csv").write_text("x")
    assert newest_export(tmp_path).name.endswith("2026_11_24.csv")
    with pytest.raises(DigestDataError):
        newest_export(tmp_path / "empty-does-not-exist")


def test_in_years():
    ps = load_positions(CSV)
    assert {p.year for p in in_years(ps, 2017, 2020)} == {2017, 2018, 2019, 2020}
    assert {p.year for p in in_years(ps, 2026)} == {2026}


# ---------------------------------------------------------------- gate


def _cfg():
    return load_gate_config(GATE)


def test_gate_config_fails_closed_on_missing_fields():
    data = json.loads(GATE.read_text())
    for path in (("limits",), ("valuation", "cap_no_above_usd"), ("sectors", "avoid")):
        broken = json.loads(json.dumps(data))
        node = broken
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
        with pytest.raises(GateConfigError):
            parse_gate_config(broken)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("valuation", {"cap_yes_max_usd": 30, "cap_no_above_usd": 20}),
        lambda d: d["limits"].__setitem__("per_lead_per_year_usd", True),
        lambda d: d["limits"].__setitem__("per_lead_per_year_usd", -1),
        lambda d: d["stage"].__setitem__("allowed", "seed"),
        lambda d: d["stage"].__setitem__("max_round_size_usd", []),
        lambda d: d["stage"].__setitem__("aliases", []),
        lambda d: d.__setitem__("top_three_leads", {"X": 1}),
        lambda d: d.__setitem__("market_sectors", {"X": 1}),
        lambda d: d["sectors"].__setitem__("labels", []),
    ],
)
def test_gate_config_rejects_bad_values(mutate):
    data = json.loads(GATE.read_text())
    mutate(data)
    with pytest.raises(GateConfigError):
        parse_gate_config(data)


def test_gate_config_not_object_and_bad_file(tmp_path):
    with pytest.raises(GateConfigError):
        parse_gate_config([])
    with pytest.raises(GateConfigError):
        load_gate_config(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(GateConfigError):
        load_gate_config(bad)


def test_gate_retro_2026_vintage():
    ps = in_years(load_positions(CSV), 2026)
    res = {p.name: g for p, g in zip(ps, gate_retro(ps, _cfg()), strict=True)}
    assert res["Lumen Shield"].verdict == "Pass"
    # $18M post is above the $12M norm but under the $25M ceiling: open.
    assert res["Kestrel Nuclear"].checks["cap"][0] == "open"
    assert res["Kestrel Nuclear"].verdict == "Borderline"
    # Pre-money $26M + $4M round = $30M post; off-thesis logistics.
    assert res["Mosaic Freight"].checks["cap"] == ("no", "$30M post")
    assert set(res["Mosaic Freight"].fails) == {"sector", "cap", "size"}
    # Third and fourth Example Syndicate tickets of the year exceed the $12k limit.
    assert res["Northwind Defense"].checks["size"][0] == "no"
    assert "lead total $20k" in res["Northwind Defense"].reasons
    # No cap on record counts as no.
    assert res["Orchid Health"].checks["cap"][0] == "no"
    # A qualified top lead is "open", never a hard fail.
    assert res["Pylon Grid"].checks["lead"] == ("open", "qualified")


def test_gate_retro_per_lead_limit_resets_each_year_and_uses_date_order():
    ps = load_positions(CSV)
    band = in_years(ps, 2017, 2020)
    res = gate_retro(list(reversed(band)), _cfg())
    assert all(g.checks["size"][0] == "yes" for g in res)


def test_gate_retro_stage_and_currency_cases():
    ps = {p.name: p for p in load_positions(CSV)}
    cfg = _cfg()
    juniper, harbor, cinder = ps["Juniper Labs"], ps["Harbor Keys"], ps["Cinder Loop"]
    g = gate_retro([juniper, harbor, cinder], cfg)
    assert g[0].checks["stage"] == ("no", "Series A")
    assert g[1].checks["cap"][0] == "open" and "EUR" in g[1].checks["cap"][1]
    assert g[1].checks["sector"] == ("no", "avoid-list")
    assert g[2].checks["stage"] == ("yes", "")  # "Seed+" alias -> seed
    juniper.stage, juniper.round_size = "seed", 50_000_000
    assert gate_retro([juniper], cfg)[0].checks["stage"] == ("no", "round too big for label")


def test_bucket_labels():
    cfg = _cfg()
    assert cfg.bucket_label("energy") == "Energy"
    assert cfg.bucket_label("crypto") == "Avoid: crypto"
    assert cfg.bucket_label("other") == "Off-thesis (other)"
    cfg.sector_labels.clear()
    assert cfg.bucket_label("security_software") == "Security software"


# ---------------------------------------------------------------- metrics


def test_aggregate_metrics_on_band():
    ps = in_years(load_positions(CSV), 2017, 2020)
    m = aggregate(ps, gate_retro(ps, _cfg()))
    t = m.total
    assert t.n == 10 and m.locked == 2
    assert t.invested == pytest.approx(15_500)
    assert t.realized == pytest.approx(5_650)
    assert m.dpi == pytest.approx(5_650 / 15_500)
    # locked at cost: net of marked + cost of locked
    marked_net = sum(p.net for p in ps if p.net is not None)
    assert t.tvpi == pytest.approx((marked_net + 2_000) / 15_500)
    assert t.tvpi_marked == pytest.approx(marked_net / 13_500)
    assert m.zeros == 1 and m.zero_share == pytest.approx(1 / 8)
    assert m.top_positions[0].name == "Acme Robotics"
    assert 0 < m.top3_share <= 1 and m.top1_share < m.top3_share
    assert sum(g.n for g in m.by_bucket_multiple.values()) == 10
    assert sum(g.n for g in m.by_verdict.values()) == 10
    assert list(m.by_year) == [2017, 2018, 2019, 2020]
    assert "would have helped" in gate_verdict_sentence(m)


def test_multiple_buckets():
    ps = {p.name: p for p in load_positions(CSV)}
    assert multiple_bucket(ps["Cinder Loop"]) == "0x"
    assert multiple_bucket(ps["Granite Ledger"]) == "0-1x"
    assert multiple_bucket(ps["Blue Harbor Energy"]) == "1-3x"
    assert multiple_bucket(ps["Iris Orbit"]) == "3-10x"
    assert multiple_bucket(ps["Acme Robotics"]) == ">10x"
    assert multiple_bucket(ps["Fable Foods"]) == "locked"


def test_verdict_sentence_edge_cases():
    ps = in_years(load_positions(CSV), 2026)
    cfg = _cfg()
    m = aggregate(ps, gate_retro(ps, cfg))
    # Only locked positions on one side -> still a numeric comparison (at cost).
    assert "return" in gate_verdict_sentence(m) or "Too few" in gate_verdict_sentence(m)
    m.by_verdict["Fail"] = Group()
    assert "no comparison" in gate_verdict_sentence(m)
    assert Group().tvpi is None and Group().tvpi_marked is None


def test_position_year_property():
    p = load_positions(CSV)[0]
    assert p.year == p.invest_date.year == 2017
    assert isinstance(p.invest_date, date)


def test_nul_bytes_in_export_are_dropped():
    from presidio_angellist.digest.csvload import _rows_from_text

    text = 'Disclaimer\nCompany/Fund,Invested\nAcme\x00 Robotics,"$1,000"\n'
    rows = _rows_from_text(text)
    assert rows[0]["Company/Fund"] == "Acme Robotics"
