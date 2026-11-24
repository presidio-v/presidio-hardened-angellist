"""Locked-value estimates and the Portfolio Digest (synthetic fixtures only)."""

from __future__ import annotations

import json
import shutil

import pytest
from digest_helpers import (
    AGG_CONTENT,
    BRAND,
    CSV,
    FIXTURES,
    GATE,
    VINTAGE_CONTENT,
    fake_xelatex,
)

from presidio_angellist.cli import main as angeltriage
from presidio_angellist.digest.build import check_tex_source, compile_pdf, find_xelatex
from presidio_angellist.digest.config import load_brand, load_content, normalise_content
from presidio_angellist.digest.csvload import in_years, load_positions
from presidio_angellist.digest.estimates import (
    EstimatesError,
    carry_rate,
    est_gross,
    est_net,
    load_estimates,
    parse_estimates,
    value_incl_estimates,
)
from presidio_angellist.digest.gate import gate_retro, load_gate_config
from presidio_angellist.digest.metrics import aggregate
from presidio_angellist.digest.render import (
    DocMeta,
    Segment,
    build_aggregate_tex,
    build_portfolio_tex,
    build_vintage_tex,
)
from presidio_angellist.digest.runner import (
    Inputs,
    build_portfolio,
    estimate_warnings,
    load_run_config,
    portfolio_output_name,
    run,
)

ESTIMATES = FIXTURES / "locked-estimates.json"
PORTFOLIO = FIXTURES / "portfolio.json"
needs_xelatex = pytest.mark.skipif(find_xelatex() is None, reason="xelatex not installed")


def _ps():
    return {p.name: p for p in load_positions(CSV)}


def _est():
    return load_estimates(ESTIMATES)


def _entry(**kw):
    base = {"evidence": "priced_round", "est_multiple": 2.0, "range": [1, 3], "confidence": "low"}
    base.update(kw)
    return {"positions": {"X": base}}


# ---------------------------------------------------------------- estimates file


@pytest.mark.parametrize(
    "bad",
    [
        _entry(evidence="rumour"),
        _entry(est_multiple=-0.1),
        _entry(est_multiple=True),
        _entry(est_multiple="2"),
        _entry(range=[3, 1]),
        _entry(range=[-1, 1]),
        _entry(range=[1]),
        _entry(confidence="certain"),
        _entry(post_money_usd=-5),
        {"positions": {"X": "junk"}},
        {"positions": []},
        [],
    ],
)
def test_estimates_validation_fails_closed(bad):
    with pytest.raises(EstimatesError):
        parse_estimates(bad)


def test_estimates_load_and_sources_filtered():
    est = _est()
    assert est.method.startswith("Last priced round") and est.as_of == "2026-11-01"
    assert set(est.positions) >= {"Kestrel Nuclear", "Fable Foods"}
    assert est.positions["Orchid Health"].sources == []  # javascript: link dropped
    assert est.positions["Northwind Defense"].post_money is None
    assert load_estimates(None) is None
    # A missing range defaults to the point estimate.
    pt = parse_estimates({"positions": {"X": {"evidence": "none", "est_multiple": 2}}})
    assert (pt.positions["X"].low, pt.positions["X"].high) == (2.0, 2.0)
    assert pt.positions["X"].confidence == "low"


def test_carry_and_value_formulas():
    ps = _ps()
    est = _est()
    k = ps["Kestrel Nuclear"]  # $5k, carry 20%, est 2.0x
    e = est.for_position(k)
    assert carry_rate(k) == pytest.approx(0.20)
    assert est_gross(k, e) == pytest.approx(10_000)
    assert est_net(k, e) == pytest.approx(5_000 * (1 + 1.0 * 0.8))
    o = ps["Orchid Health"]  # 0.3x: no carry below cost
    assert est_net(o, est.for_position(o)) == pytest.approx(2_500 * 0.3)
    k.carry = ""
    assert carry_rate(k) == pytest.approx(0.20)
    k.carry = "15%"
    assert carry_rate(k) == pytest.approx(0.15)
    k.carry = "0.1"
    assert carry_rate(k) == pytest.approx(0.10)
    k.carry = "n/a"
    assert carry_rate(k) == pytest.approx(0.20)


def test_estimates_apply_only_to_locked_positions():
    ps = _ps()
    est = parse_estimates({"positions": {"Lumen Shield": {"evidence": "acquisition",
                                                          "est_multiple": 9.0,
                                                          "range": [8, 10],
                                                          "confidence": "high"}}})  # fmt: skip
    lumen = ps["Lumen Shield"]  # marked
    assert est.for_position(lumen) is None
    assert value_incl_estimates(lumen, est) == lumen.net
    mosaic = ps["Mosaic Freight"]  # locked, no estimate -> cost
    assert value_incl_estimates(mosaic, _est()) == mosaic.invested


def test_unknown_names_and_batch_suffix_match():
    ps = load_positions(CSV)
    est = parse_estimates(
        {
            "positions": {
                "Ghost Co": {"evidence": "none", "est_multiple": 1, "range": [1, 1]},
                "Kestrel Nuclear (YC W24)": {
                    "evidence": "none",
                    "est_multiple": 1.5,
                    "range": [1, 2],
                },  # fmt: skip
            }
        }
    )
    assert est.unknown_names(ps) == ["Ghost Co"]
    assert est.for_position(_ps()["Kestrel Nuclear"]).est_multiple == 1.5
    assert estimate_warnings(est, ps) == [
        "locked estimate for a company not in the export: Ghost Co"
    ]
    assert estimate_warnings(None, ps) == []


def test_metrics_with_estimates():
    ps = in_years(load_positions(CSV), 2026)
    m = aggregate(ps, gate_retro(ps, load_gate_config(GATE)), estimates=_est())
    t = m.total
    # Kestrel 9k, Northwind 5k*(1+0.2*0.8)=5.8k, Orchid 0.75k, Mosaic/Pylon at cost, Lumen mark
    expected = 9_000 + 5_800 + 750 + 5_000 + 5_000 + 4_850
    assert t.net_est == pytest.approx(expected)
    assert t.tvpi_est == pytest.approx(expected / t.invested)
    assert t.net_est_gross == pytest.approx(10_000 + 6_000 + 750 + 10_000 + 4_850)
    assert t.n_estimated == 3
    assert m.total.tvpi_est != m.total.tvpi


# ---------------------------------------------------------------- rendering


def _cfg():
    return load_gate_config(GATE)


def _meta(label="x"):
    return DocMeta("2026-Q4", "2026-11-01", label)


def test_vintage_with_estimates():
    ps = in_years(load_positions(CSV), 2026)
    out = build_vintage_tex(ps, _cfg(), load_content(VINTAGE_CONTENT), load_brand(BRAND),
                            _meta(), 2026, estimates=_est())  # fmt: skip
    assert "TVPI incl. locked estimates, net" in out
    assert "Locked positions: estimated value" in out
    assert "Est. locked value" in out and "none: at cost" in out
    assert "not marks" in out and "Last priced round" in out
    check_tex_source(out)
    plain = build_vintage_tex(ps, _cfg(), load_content(VINTAGE_CONTENT), load_brand(BRAND),
                              _meta(), 2026)  # fmt: skip
    assert "Locked positions: estimated value" not in plain and "Est. locked value" not in plain


def test_aggregate_with_estimates():
    ps = in_years(load_positions(CSV), 2017, 2020)
    out = build_aggregate_tex(ps, _cfg(), load_content(AGG_CONTENT), load_brand(BRAND),
                              _meta(), (2017, 2020), estimates=_est())  # fmt: skip
    assert "Locked positions: estimated value" in out and "acquisition" in out


def test_hostile_estimates_are_escaped():
    hostile = r"\input{/etc/passwd}\write18{id}^^5c"
    est = parse_estimates(
        {
            "method": hostile,
            "positions": {
                "Kestrel Nuclear": {"evidence": "priced_round", "event": hostile,
                                    "est_multiple": 2, "range": [1, 3], "confidence": "low",
                                    "sources": [{"label": hostile, "url": "file:///etc"}]},
            },
        }
    )  # fmt: skip
    ps = in_years(load_positions(CSV), 2026)
    out = build_vintage_tex(ps, _cfg(), normalise_content({}), load_brand(BRAND), _meta(),
                            2026, estimates=est)  # fmt: skip
    for needle in (r"\input{", r"\write18", "^^5c"):
        assert needle not in out
    check_tex_source(out)


def _segments():
    all_ps = load_positions(CSV)
    return all_ps, [
        Segment("2026", in_years(all_ps, 2026)),
        Segment("2015-2020", in_years(all_ps, 2015, 2020)),
    ]


def test_portfolio_tex():
    all_ps, segs = _segments()
    out = build_portfolio_tex(segs, all_ps, _cfg(), load_content(PORTFOLIO), load_brand(BRAND),
                              _meta("portfolio"), estimates=_est())  # fmt: skip
    for needle in (
        "Portfolio Digest 2026-Q4",
        "Segments compared",
        r"\textbf{Total}",
        "2015-2020",
        "One outlier carries the band",
        "TVPI by vintage year",
        "DPI by segment",
        "Gate retro-check by segment",
        "Top value drivers across the portfolio",
        "Biggest locked estimates",
        "TVPI incl. est.",
        "not marks",
    ):
        assert needle in out, needle
    assert "2017-2020" not in out  # the requested band label is used
    check_tex_source(out)
    plain = build_portfolio_tex(segs, all_ps, _cfg(), normalise_content({}), load_brand(BRAND),
                                _meta("portfolio"))  # fmt: skip
    assert "TVPI incl. est." not in plain and "Biggest locked estimates" not in plain


def test_portfolio_total_counts_overlap_once():
    all_ps = load_positions(CSV)
    segs = [
        Segment("2026", in_years(all_ps, 2026)),
        Segment("2021-2026", in_years(all_ps, 2021, 2026)),
    ]
    out = build_portfolio_tex(segs, all_ps, _cfg(), normalise_content({}), load_brand(BRAND),
                              _meta("portfolio"))  # fmt: skip
    assert r"\textbf{Total} & 6 (5)" in out
    assert "2026, 2021-2026" in out  # a position in both segments lists both


# ---------------------------------------------------------------- runner / CLI


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy(CSV, tmp_path / "data" / CSV.name)
    for f in (VINTAGE_CONTENT, AGG_CONTENT, PORTFOLIO, ESTIMATES):
        shutil.copy(f, tmp_path / f.name)
    shutil.copy(GATE, tmp_path / "gate.json")
    shutil.copy(BRAND, tmp_path / "brand.toml")
    return tmp_path, fake_xelatex(tmp_path)


def test_build_portfolio_runner(ws):
    root, exe = ws
    inp = Inputs(positions=load_positions(CSV), gate=_cfg(), brand=load_brand(BRAND),
                 content_dir=root, out_dir=root / "out", quarter="2026-Q4",
                 as_of="2026-11-01", xelatex=exe, estimates=_est())  # fmt: skip
    out = build_portfolio(inp, [2026], ["2015-2020"])
    assert out.name == "Example-Ventures-Portfolio-Digest-2026-Q4.pdf"
    assert portfolio_output_name(load_brand(BRAND), "2026-Q4") == out.name
    with pytest.raises(Exception, match="no positions"):
        build_portfolio(inp, [1999], [])


def test_cli_build_four_pdfs_with_estimates(ws, capsys):
    root, exe = ws
    est = json.loads(ESTIMATES.read_text())
    est["positions"]["Ghost Co"] = {"evidence": "none", "est_multiple": 1, "range": [1, 1]}
    (root / "est.json").write_text(json.dumps(est))
    args = ["digest", "build", "--csv-dir", str(root / "data"),
            "--gate-config", str(root / "gate.json"), "--brand", str(root / "brand.toml"),
            "--content-dir", str(root), "--out-dir", str(root / "out"), "--quarter", "2026-Q4",
            "--vintage", "2026", "--band", "2015-2020", "--band", "2017-2020",
            "--locked-estimates", str(root / "est.json"), "--portfolio",
            "--xelatex", exe]  # fmt: skip
    assert angeltriage(args) == 0
    out = capsys.readouterr()
    assert len(list((root / "out").glob("*.pdf"))) == 4
    assert "Portfolio-Digest-2026-Q4.pdf" in out.out
    assert "not in the export: Ghost Co" in out.err


def test_cli_bad_estimates_file(ws, capsys):
    root, exe = ws
    (root / "bad.json").write_text(json.dumps(_entry(range=[3, 1])))
    args = ["digest", "build", "--csv-dir", str(root / "data"),
            "--gate-config", str(root / "gate.json"), "--out-dir", str(root / "out"),
            "--vintage", "2026", "--locked-estimates", str(root / "bad.json"),
            "--xelatex", exe]  # fmt: skip
    assert angeltriage(args) == 2
    assert "range" in capsys.readouterr().err


def test_run_config_portfolio_and_estimates(ws, capsys):
    root, exe = ws
    cfg = {"csv_dir": "data", "gate_config": "gate.json", "brand": "brand.toml",
           "content_dir": ".", "out_dir": "out", "vintages": [2026], "bands": ["2015-2020"],
           "xelatex": exe, "portfolio": True,
           "locked_estimates": "locked-estimates.json"}  # fmt: skip
    path = root / "digest.json"
    path.write_text(json.dumps(cfg))
    rc = load_run_config(path, "2026-Q4")
    assert rc.portfolio is True and rc.locked_estimates == root / "locked-estimates.json"
    result = run(rc, "2026-Q4")
    assert result.errors == [] and len(result.pdfs) == 3
    assert any("Portfolio-Digest" in p.name for p in result.pdfs)
    assert angeltriage(["digest", "run", "--config", str(path), "--dry-run"]) == 0
    assert "portfolio: True" in capsys.readouterr().out
    cfg["portfolio"] = "yes"
    path.write_text(json.dumps(cfg))
    assert angeltriage(["digest", "run", "--config", str(path)]) == 2


def test_run_portfolio_failure_collected(ws):
    root, exe = ws
    cfg = {"csv_dir": "data", "gate_config": "gate.json", "content_dir": ".",
           "out_dir": "out", "vintages": [1999], "xelatex": exe,
           "portfolio": True}  # fmt: skip
    path = root / "digest.json"
    path.write_text(json.dumps(cfg))
    result = run(load_run_config(path, "2026-Q4"), "2026-Q4")
    assert any(e.startswith("portfolio:") for e in result.errors)


@needs_xelatex
def test_real_render_portfolio_and_estimates(tmp_path):
    all_ps, segs = _segments()
    out = build_portfolio_tex(segs, all_ps, _cfg(), load_content(PORTFOLIO), load_brand(BRAND),
                              _meta("portfolio"), estimates=_est())  # fmt: skip
    assert compile_pdf(out, tmp_path / "p.pdf").stat().st_size > 1000
    v = build_vintage_tex(in_years(all_ps, 2026), _cfg(), load_content(VINTAGE_CONTENT),
                          load_brand(BRAND), _meta(), 2026, estimates=_est())  # fmt: skip
    assert compile_pdf(v, tmp_path / "v.pdf").stat().st_size > 1000


def test_contrib_example_estimates_parse():
    root = FIXTURES.parent.parent.parent
    est = load_estimates(root / "contrib" / "digest" / "locked-estimates.example.json")
    assert est.positions["Example Shutdown Co"].evidence == "shutdown"


def test_locked_position_keeps_cash_already_paid_out():
    from datetime import date

    from presidio_angellist.digest.csvload import Position
    from presidio_angellist.digest.estimates import value_incl_estimates

    p = Position(
        name="Acme Partial",
        invest_date=date(2019, 1, 1),
        invested=1000.0,
        unrealized=None,
        realized=250.0,
    )
    assert p.net_at_cost == 1250.0
    assert value_incl_estimates(p, None) == 1250.0
