"""VC market comparison: benchmark file, derived figures, PDF assembly and CLI."""

from __future__ import annotations

import copy
import json
import shutil

import pytest
from digest_helpers import BRAND, CSV, FIXTURES, GATE, fake_xelatex

from presidio_angellist.cli import main as angeltriage
from presidio_angellist.digest.build import check_tex_source, compile_pdf, find_xelatex
from presidio_angellist.digest.config import load_brand, normalise_content
from presidio_angellist.digest.csvload import in_years, load_positions
from presidio_angellist.digest.estimates import load_estimates
from presidio_angellist.digest.gate import load_gate_config
from presidio_angellist.digest.latex import diverging_hbar, grouped_columns, strip_chart
from presidio_angellist.digest.market import (
    MarketError,
    best_period,
    entry_ratios,
    is_us,
    load_market,
    market_warnings,
    normalise_stage,
    parse_market,
    weighted_market_tvpi,
)
from presidio_angellist.digest.market_render import build_market_tex
from presidio_angellist.digest.render import DocMeta, Segment, build_portfolio_tex
from presidio_angellist.digest.runner import (
    Inputs,
    build_market,
    load_run_config,
    market_output_name,
    run,
)

MARKET = FIXTURES / "market.json"
ESTIMATES = FIXTURES / "locked-estimates.json"
needs_xelatex = pytest.mark.skipif(find_xelatex() is None, reason="xelatex not installed")


def _raw():
    return json.loads(MARKET.read_text())


def _m():
    return load_market(MARKET)


def _ps():
    return {p.name: p for p in load_positions(CSV)}


# ---------------------------------------------------------------- file validation


def test_fixture_parses():
    m = _m()
    assert [s.id for s in m.sources] == ["EX-FUNDS", "EX-ROUNDS", "EX-GRAD", "EX-SECTORS"]
    assert m.vintages[2017].median == 1.9 and m.vintages[2026].dpi_median is None
    assert m.cite(["EX-SECTORS", "EX-FUNDS", "EX-FUNDS"]) == "[1] EX-FUNDS; [4] EX-SECTORS"
    assert m.headline.startswith("The early band")
    assert load_market(None) is None


def _mut(fn):
    d = _raw()
    fn(d)
    return d


@pytest.mark.parametrize(
    "bad",
    [
        _mut(lambda d: d["vintage_benchmarks"]["rows"][0].update(source="NOPE")),
        _mut(lambda d: d["vintage_benchmarks"]["rows"][0].update(tvpi_p25=5.0)),
        _mut(lambda d: d["vintage_benchmarks"]["rows"][0].update(tvpi_p75=0.5)),
        _mut(lambda d: d["vintage_benchmarks"]["rows"][0].update(vintage="x")),
        _mut(lambda d: d["vintage_benchmarks"]["rows"][0].update(dpi_median=-1)),
        _mut(lambda d: d["vintage_benchmarks"]["rows"][0].update(tvpi_median=True)),
        _mut(lambda d: d["sector_market"][0].update(share_dollars=1.2)),
        _mut(lambda d: d["sector_market"][0].update(share_deals=-0.1)),
        _mut(lambda d: d["sector_market"][0].update(scope="EU")),
        _mut(lambda d: d["sector_market"][0].update(period="recent")),
        _mut(lambda d: d["sector_market"][0].update(bucket="")),
        _mut(lambda d: d["geo_market"][0].update(source="MISSING")),
        _mut(lambda d: d["stage_benchmarks"][0].update(stage="series c")),
        _mut(lambda d: d["stage_benchmarks"][0].update(year=None)),
        _mut(lambda d: d["stage_benchmarks"][0].update(median_post_money_usd=0)),
        _mut(lambda d: d["graduation"][0].update(rate=1.5)),
        _mut(lambda d: d["graduation"][0].update(rate=None)),
        _mut(lambda d: d["sources"].append(dict(d["sources"][0]))),
        _mut(lambda d: d.update(sources=[{"label": "no id"}])),
        _mut(lambda d: d.update(company_geo={"X": "US"})),
        _mut(lambda d: d.update(commentary=[])),
        _mut(lambda d: d.update(vintage_benchmarks=[])),
        _mut(lambda d: d.update(geo_market={})),
        [],
    ],
)
def test_validation_fails_closed(bad):
    with pytest.raises(MarketError):
        parse_market(bad)


def test_company_geo_unknown_name_warns_and_bad_url_dropped():
    d = _raw()
    d["company_geo"]["Ghost Co"] = {"country": "US", "region": "US"}
    d["sources"][0]["url"] = "javascript:alert(1)"
    m = parse_market(d)
    assert m.sources[0].url is None
    assert market_warnings(m, load_positions(CSV)) == [
        "market company_geo names a company not in the export: Ghost Co"
    ]
    assert market_warnings(None, []) == []


# ---------------------------------------------------------------- derived figures


def test_best_period_overlap_rule():
    periods = ["2017-2020", "2021-2025", "2026"]
    assert best_period(periods, 2015, 2020) == "2017-2020"
    assert best_period(periods, 2026, 2026) == "2026"
    assert best_period(periods, 2017, 2026) == "2021-2025"  # 5 overlapping years beat 4
    assert best_period(periods, 2010, 2012) is None
    # tie on overlap -> closest span, then earlier
    assert best_period(["2018-2019", "2020-2023"], 2019, 2020) == "2018-2019"


def test_normalise_stage():
    p = _ps()["Kestrel Nuclear"]
    for raw, want in (
        ("Pre-Seed", "pre-seed"),
        ("Seed", "seed"),
        ("Seed+", "seed+"),
        ("Series A", "series a"),
        ("Series A+", "series a"),
        ("Series B", "later"),
        ("", "other"),
    ):
        p.stage = raw
        assert normalise_stage(p) == want, raw
    p.investment_type = "Fund"
    assert normalise_stage(p) == "fund"


def test_entry_ratios_region_preference_and_exclusions():
    m = _m()
    ratios, excluded = entry_ratios(m, load_positions(CSV))
    by = {r.position.name: r for r in ratios}
    # US seed company uses the US seed row; 2026 factor 1 + 0.08 * 9
    kestrel = by["Kestrel Nuclear"]
    assert kestrel.benchmark.region == "US"
    assert kestrel.ratio == pytest.approx(18e6 / round(14e6 * 1.72))
    # European pre-seed company falls back to the global row
    assert by["Lumen Shield"].benchmark.region == "global"
    # no cap (Fable Foods, Orchid Health) and a non-USD cap (Harbor Keys) are excluded
    assert {"Fable Foods", "Orchid Health", "Harbor Keys"}.isdisjoint(by)
    assert excluded == 3


def test_weighted_market_tvpi_and_is_us():
    m = _m()
    ps = in_years(load_positions(CSV), 2017, 2018)
    w, ids = weighted_market_tvpi(m, ps)
    inv17 = sum(p.invested for p in ps if p.year == 2017)
    inv18 = sum(p.invested for p in ps if p.year == 2018)
    assert w == pytest.approx((1.9 * inv17 + 1.7 * inv18) / (inv17 + inv18))
    assert set(ids) == {"EX-FUNDS"}
    assert weighted_market_tvpi(m, in_years(load_positions(CSV), 1999)) == (None, [])
    assert is_us(None) is None
    assert is_us(m.geo_for(_ps()["Acme Robotics"])) is True
    assert is_us(m.geo_for(_ps()["Lumen Shield"])) is False
    assert m.region_of(_ps()["Pylon Grid"]) == "Unknown"


# ---------------------------------------------------------------- charts


def test_chart_helpers():
    out = grouped_columns(
        [("2017", [[(14.0, "dgblue")]]), ("2018", [[(1.5, "dgblue")]])],
        [("x", "dgblue")],
        band=[(1.0, 2.0), None],
        line=[1.5, None],
        vmax_cap=4.0,
        fmt=str,
    )
    assert "dgamber!18" in out and "dashed" in out and "fill[white]" in out
    out = diverging_hbar([(r"\input{x}", 0.1), ("b", -0.2)])
    assert r"\input{x}" not in out and "-20 pp" in out
    out = strip_chart([("seed}", [(0.5, "dgblue"), (20.0, "dgred")])])
    assert r"seed\}" in out and "1x" in out


# ---------------------------------------------------------------- document


def _cfg():
    return load_gate_config(GATE)


def _meta():
    return DocMeta("2026-Q4", "2026-11-01", "market")


def _segs():
    all_ps = load_positions(CSV)
    return all_ps, [
        Segment("2026", in_years(all_ps, 2026)),
        Segment("2015-2020", in_years(all_ps, 2015, 2020)),
    ]


def test_market_tex_structure():
    all_ps, segs = _segs()
    out = build_market_tex(segs, all_ps, _cfg(), _m(), load_brand(BRAND), _meta(),
                           estimates=load_estimates(ESTIMATES))  # fmt: skip
    for needle in (
        "Market Comparison 2026-Q4",
        "Overall: returns by vintage year",
        "Geographic",
        "Sectoral",
        "Stage",
        "Commentary",
        "Sources",
        "Glossary",
        "Method",
        "{[}1{]} EX-FUNDS",
        "{[}4{]} EX-SECTORS",
        "Unknown",
        "market 2017-2020",  # the 2015-2020 segment maps to the 2017-2020 market period
        "deal-by-deal angel book",
        "AI across sectors",
        "Portfolio (locked estimates)",
        "Graduation rate",
        "p25 / p75",
        r"\href{https://example.org/fund-benchmarks}",
    ):
        assert needle in out, needle
    check_tex_source(out)
    plain = build_market_tex(segs, all_ps, _cfg(), _m(), load_brand(BRAND), _meta())
    assert "Portfolio (locked estimates)" not in plain


def test_market_tex_minimal_file():
    all_ps, segs = _segs()
    m = parse_market({"sources": [], "commentary": {}})
    out = build_market_tex(segs, all_ps, _cfg(), m, load_brand(BRAND), _meta())
    assert "Commentary" not in out and "Graduation rates" not in out
    check_tex_source(out)


def test_market_hostile_text_is_escaped():
    d = _raw()
    hostile = r"\input{/etc/passwd}\write18{id}^^5c"
    d["commentary"]["headline"] = hostile
    d["commentary"]["overall"] = [hostile]
    d["sources"][0]["label"] = hostile
    d["sources"][0]["url"] = "https://example.org/a}\\input{x}"
    d["vintage_benchmarks"]["basis"] = hostile
    d["company_geo"]["Acme Robotics"]["region"] = hostile
    d["sector_market"][0]["bucket"] = hostile
    all_ps, segs = _segs()
    out = build_market_tex(segs, all_ps, _cfg(), parse_market(d), load_brand(BRAND), _meta())
    for needle in (r"\input{", r"\write18", "^^5c"):
        assert needle not in out
    check_tex_source(out)


def test_portfolio_jcurve_market_line():
    all_ps, segs = _segs()
    args = (segs, all_ps, _cfg(), normalise_content({}), load_brand(BRAND), _meta())
    with_m = build_portfolio_tex(*args, market=_m())
    assert "market median" in with_m and "Market median TVPI: {[}1{]} EX-FUNDS" in with_m
    assert "Market median TVPI" not in build_portfolio_tex(*args)
    empty = parse_market({"sources": []})
    assert "Market median TVPI" not in build_portfolio_tex(*args, market=empty)


# ---------------------------------------------------------------- runner / CLI


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy(CSV, tmp_path / "data" / CSV.name)
    for f in (MARKET, ESTIMATES, FIXTURES / "portfolio.json"):
        shutil.copy(f, tmp_path / f.name)
    shutil.copy(GATE, tmp_path / "gate.json")
    shutil.copy(BRAND, tmp_path / "brand.toml")
    return tmp_path, fake_xelatex(tmp_path)


def test_build_market_runner(ws):
    root, exe = ws
    inp = Inputs(positions=load_positions(CSV), gate=_cfg(), brand=load_brand(BRAND),
                 content_dir=root, out_dir=root / "out", quarter="2026-Q4",
                 as_of="2026-11-01", xelatex=exe)  # fmt: skip
    with pytest.raises(Exception, match="needs a market file"):
        build_market(inp, [2026], [])
    inp.market = _m()
    out = build_market(inp, [2026], ["2015-2020"])
    assert out.name == market_output_name(load_brand(BRAND), "2026-Q4")
    assert out.name == "Example-Ventures-Market-Comparison-2026-Q4.pdf"
    with pytest.raises(Exception, match="no positions"):
        build_market(inp, [1999], [])


def test_cli_market_flag(ws, capsys):
    root, exe = ws
    d = _raw()
    d["company_geo"]["Ghost Co"] = {"country": "US", "region": "US"}
    (root / "m.json").write_text(json.dumps(d))
    args = ["digest", "build", "--csv-dir", str(root / "data"),
            "--gate-config", str(root / "gate.json"), "--brand", str(root / "brand.toml"),
            "--content-dir", str(root), "--out-dir", str(root / "out"), "--quarter", "2026-Q4",
            "--vintage", "2026", "--band", "2015-2020", "--portfolio",
            "--locked-estimates", str(root / ESTIMATES.name), "--market", str(root / "m.json"),
            "--xelatex", exe]  # fmt: skip
    assert angeltriage(args) == 0
    out = capsys.readouterr()
    assert "Market-Comparison-2026-Q4.pdf" in out.out
    assert "not in the export: Ghost Co" in out.err
    assert len(list((root / "out").glob("*.pdf"))) == 4


def test_cli_bad_market_file(ws, capsys):
    root, exe = ws
    bad = copy.deepcopy(_raw())
    bad["sector_market"][0]["share_dollars"] = 2
    (root / "bad.json").write_text(json.dumps(bad))
    args = ["digest", "build", "--csv-dir", str(root / "data"),
            "--gate-config", str(root / "gate.json"), "--out-dir", str(root / "out"),
            "--vintage", "2026", "--market", str(root / "bad.json"), "--xelatex", exe]  # fmt: skip
    assert angeltriage(args) == 2
    assert "between 0 and 1" in capsys.readouterr().err


def test_run_config_market(ws, capsys):
    root, exe = ws
    cfg = {"csv_dir": "data", "gate_config": "gate.json", "brand": "brand.toml",
           "content_dir": ".", "out_dir": "out", "vintages": [2026], "bands": ["2015-2020"],
           "xelatex": exe, "market": "market.json"}  # fmt: skip
    path = root / "digest.json"
    path.write_text(json.dumps(cfg))
    rc = load_run_config(path, "2026-Q4")
    assert rc.market == root / "market.json"
    result = run(rc, "2026-Q4")
    assert result.errors == []
    assert any("Market-Comparison" in p.name for p in result.pdfs)
    assert angeltriage(["digest", "run", "--config", str(path), "--dry-run"]) == 0
    assert "market:   " in capsys.readouterr().out


def test_run_market_failure_collected(ws):
    root, exe = ws
    cfg = {"csv_dir": "data", "gate_config": "gate.json", "content_dir": ".",
           "out_dir": "out", "vintages": [1999], "xelatex": exe,
           "market": "market.json"}  # fmt: skip
    path = root / "digest.json"
    path.write_text(json.dumps(cfg))
    result = run(load_run_config(path, "2026-Q4"), "2026-Q4")
    assert any(e.startswith("market:") for e in result.errors)


def test_contrib_example_market_parses():
    root = FIXTURES.parent.parent.parent
    m = load_market(root / "contrib" / "digest" / "market.example.json")
    assert m.sources and m.vintages


@needs_xelatex
def test_real_render_market(tmp_path):
    all_ps, segs = _segs()
    out = build_market_tex(segs, all_ps, _cfg(), _m(), load_brand(BRAND), _meta(),
                           estimates=load_estimates(ESTIMATES))  # fmt: skip
    assert compile_pdf(out, tmp_path / "m.pdf").stat().st_size > 1000


def test_axis_tick_labels_are_short():
    from presidio_angellist.digest.latex import _tick

    assert _tick(0.0401606) == "0.04"
    assert _tick(1.0) == "1"
    assert _tick(2.5) == "2.5"
    assert _tick(12.3239) == "12"
