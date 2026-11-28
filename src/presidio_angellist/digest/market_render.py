"""
LaTeX for the Market Comparison digest (portfolio against VC market benchmarks).

Same rule as :mod:`render`: every string from the CSV, the market file, the gate
config or the brand reaches the document only through :func:`tex` / :func:`tex_url`
or a numeric formatter. Every number taken from the market file is followed by a
source line citing the file's source ids; the numbered list closes the document.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from presidio_angellist.digest.gate import bucket_of
from presidio_angellist.digest.latex import (
    diverging_hbar,
    grouped_columns,
    money,
    multiple,
    stacked_rows,
    strip_chart,
    tex,
    tex_url,
)
from presidio_angellist.digest.market import (
    ENTRY_STAGES,
    UNKNOWN_REGION,
    Market,
    benchmark_stage,
    entry_ratios,
    is_us,
    market_shares,
    median_or_none,
    normalise_stage,
    weighted_market_tvpi,
)
from presidio_angellist.digest.metrics import Group
from presidio_angellist.digest.render import (
    Segment,
    _table,
    _union,
    bucket_colours,
    bucket_order,
    kpi_row,
    method_block,
    preamble,
    title_block,
    with_glossary,
)

if TYPE_CHECKING:
    from presidio_angellist.digest.config import Brand
    from presidio_angellist.digest.csvload import Position
    from presidio_angellist.digest.estimates import Estimates
    from presidio_angellist.digest.gate import GateConfig
    from presidio_angellist.digest.render import DocMeta

_REGION_PALETTE = ("dgnavy", "dgblue", "dgaccent", "dgteal", "dgsteel", "dgamber", "dgnavy!50")
_STAGE_COLOR = {
    "pre-seed": "dgteal",
    "seed": "dgaccent",
    "seed+": "dgblue",
    "series a": "dgnavy",
    "later": "dgsteel",
    "fund": "dgamber",
    "other": "dggray!70",
}
_AI_RE = re.compile(r"\bAI\b")
CAVEAT = (
    "Caveat: market figures are fund-level, net-of-fees benchmarks for pooled venture "
    "funds; this portfolio is a deal-by-deal angel book through SPVs. Read the comparison "
    "as context, not as a like-for-like ranking."
)


def _pct(v: float | None) -> str:
    """Plain-text percentage (escaped later by tex())."""
    return "--" if v is None else f"{v * 100:.0f}%"


def _usd(v: float | None) -> str:
    if v is None:
        return "--"
    return f"${v / 1e6:,.1f}M".replace(".0M", "M") if v >= 1e6 else f"${v / 1e3:,.0f}k"


def source_line(m: Market, ids, note: str = "") -> str:  # noqa: ANN001
    cited = m.cite(ids)
    text = (note + " " if note else "") + (f"Source: {cited}." if cited else "")
    return (r"{\tiny\color{dggray}" + tex(text.strip()) + r"}\par") if text.strip() else ""


def _span(positions: list[Position]) -> tuple[int, int]:
    years = [p.year for p in positions]
    return min(years), max(years)


def _seg_span(seg: Segment) -> tuple[int, int]:
    """The segment's requested years (its label), else the positions' years."""
    m = re.fullmatch(r"(\d{4})(?:-(\d{4}))?", seg.label)
    if m:
        return int(m.group(1)), int(m.group(2) or m.group(1))
    return _span(seg.positions)


def _shares(values: dict[str, float]) -> dict[str, float]:
    tot = sum(values.values()) or 1.0
    return {k: v / tot for k, v in values.items()}


def _capital_by(positions: list[Position], key) -> dict[str, float]:  # noqa: ANN001
    out: dict[str, float] = {}
    for p in positions:
        k = key(p)
        out[k] = out.get(k, 0.0) + p.invested
    return out


def _compare_rows(
    segs: list[tuple[str, list[Position], tuple[int, int]]],
    key,  # noqa: ANN001
    order: list[str],
    colours: dict[str, str],
    market_rows,  # noqa: ANN001
    skip: set[str] = frozenset(),  # type: ignore[assignment]
) -> tuple[list, list[str]]:
    """Portfolio 100% bars per segment, each followed by the matching market row."""
    rows: list = []
    ids: list[str] = []
    for lab, ps, (a, b) in segs:
        sh = _shares(_capital_by(ps, key))
        rows.append((lab, [(sh.get(k, 0.0), colours[k], _pct(sh.get(k))) for k in order]))
        period, mk = market_shares(market_rows, a, b)
        if period:
            parts = []
            for k in order:
                r = mk.get(k)
                v = r.share_dollars if r and r.share_dollars is not None else 0.0
                parts.append((v, colours[k].split("!")[0] + "!45", _pct(v) if v else ""))
            known = sum(r.share_dollars or 0.0 for k2, r in mk.items() if k2 not in skip)
            if known < 0.999:
                parts.append((1.0 - known, "dglight", ""))
            rows.append((f"market {period}", parts))
            ids += [r.source for k2, r in mk.items() if k2 not in skip]
    return rows, ids


def build_market_tex(
    segments: list[Segment],
    all_positions: list[Position],
    cfg: GateConfig,
    market: Market,
    brand: Brand,
    meta: DocMeta,
    logo_ext: str | None = None,
    estimates: Estimates | None = None,
) -> str:
    m = market
    union = _union(segments)
    segs = [(s.label, s.positions, _seg_span(s)) for s in segments]
    segs_t = [*segs, ("Total", union, _span(union))]
    total = Group()
    for p in union:
        total.add(p, estimates)
    labels = ", ".join(s.label for s in segments)

    o = [preamble(brand, meta, logo_ext)]
    o.append(
        title_block(
            f"{brand.header_text} · {meta.quarter} · as of {meta.as_of}",
            f"Market Comparison {meta.quarter}",
            f"AngelList syndicate positions ({labels}) compared with published venture market "
            f"benchmarks{' as of ' + m.as_of if m.as_of else ''}.",
            m.headline,
        )
    )

    # ---- KPI tiles
    kpi_ids: list[str] = []
    mk_tvpi, ids = weighted_market_tvpi(m, union)
    kpi_ids += ids
    known = [p for p in union if m.geo_for(p) is not None]
    inv_known = sum(p.invested for p in known)
    non_us = sum(p.invested for p in known if not is_us(m.geo_for(p)))
    unknown_share = 1 - inv_known / total.invested if total.invested else None
    ua, ub = _span(union)
    gperiod, gmk = market_shares(m.geo, ua, ub)
    us_row = next((r for k, r in gmk.items() if k.strip().upper() in ("US", "USA")), None)
    mk_non_us = 1 - us_row.share_dollars if us_row and us_row.share_dollars is not None else None
    if us_row:
        kpi_ids.append(us_row.source)
    on_thesis = sum(p.invested for p in union if bucket_of(p, cfg) in cfg.on_thesis)
    speriod, smk = market_shares(m.sectors, ua, ub)
    mk_on = [r for k, r in smk.items() if k in cfg.on_thesis and r.share_dollars is not None]
    mk_on_share = sum(r.share_dollars for r in mk_on) if mk_on else None  # type: ignore[misc]
    kpi_ids += [r.source for r in mk_on]
    ratios, excluded = entry_ratios(m, union)
    kpi_ids += [r.benchmark.source for r in ratios]
    med_ratio = median_or_none([r.ratio for r in ratios])
    med_post = median_or_none([r.position.post_cap for r in ratios])  # type: ignore[misc]
    tiles = [
        (
            multiple(total.tvpi),
            f"TVPI at cost; market median {multiple(mk_tvpi)} for this vintage mix",
        ),
        (
            tex(_pct(non_us / inv_known if inv_known else None)),
            f"of capital outside the US ({_pct(unknown_share)} unknown); market "
            f"{_pct(mk_non_us)} of dollars{' (' + gperiod + ')' if gperiod else ''}",
        ),
        (
            tex(_pct(on_thesis / total.invested if total.invested else None)),
            f"of capital in on-thesis buckets; market {_pct(mk_on_share)} of dollars"
            f"{' (' + speriod + ')' if speriod else ''}",
        ),
        (
            multiple(med_ratio),
            f"median entry post-money / market median, same stage and year "
            f"(portfolio median {_usd(med_post)}; {len(ratios)} positions)",
        ),
    ]
    o.append(kpi_row(tiles, columns=4))
    o.append(source_line(m, kpi_ids, "Market medians are capital-weighted by invest year."))

    # ---- overall
    o.append(r"\Needspace{0.35\textheight}\dsec{Overall: returns by vintage year}")
    years: dict[int, Group] = {}
    for p in union:
        years.setdefault(p.year, Group()).add(p, estimates)
    yrs = sorted(years)
    vids = [m.vintages[y].source for y in yrs if y in m.vintages]
    groups = [(str(y), [[(years[y].tvpi or 0.0, "dgblue")]]) for y in yrs]
    band = [(m.vintages[y].p25, m.vintages[y].p75) if y in m.vintages else None for y in yrs]
    line = [m.vintages[y].median if y in m.vintages else None for y in yrs]
    o.append(
        r"\begin{panel}{TVPI at cost by invest year against the market p25--p75 band and median}"
        r"\centering"
        + grouped_columns(
            groups,
            [
                ("portfolio TVPI at cost", "dgblue"),
                ("market p25-p75", "dgamber!18"),
                ("market median", "dgamber"),
            ],  # fmt: skip
            height_cm=3.6,
            fmt=multiple,
            band=band,
            line=line,
            vmax_cap=max([b[1] for b in band if b] + [1.0]) * 2.5,
        )
        + r"\end{panel}"
    )
    dgroups = [(str(y), [[(years[y].dpi or 0.0, "dgnavy")]]) for y in yrs]
    dline = [
        m.vintages[y].dpi_median if y in m.vintages and m.vintages[y].dpi_median is not None
        else None
        for y in yrs
    ]  # fmt: skip
    o.append(
        r"\begin{panel}{DPI by invest year against the market median DPI}\centering"
        + grouped_columns(
            dgroups,
            [("portfolio DPI", "dgnavy"), ("market median DPI", "dgamber")],
            height_cm=2.6,
            fmt=multiple,
            line=dline,
        )
        + r"\end{panel}"
    )
    basis = f"Benchmark basis: {m.vintage_basis.rstrip('. ')}. " if m.vintage_basis else ""
    o.append(source_line(m, vids, basis + CAVEAT))

    # ---- geographic
    o.append(r"\Needspace{0.35\textheight}\dsec{Geographic}")
    reg_cap = _capital_by(union, m.region_of)
    regions = sorted(reg_cap, key=lambda r: (r == UNKNOWN_REGION, -reg_cap[r]))
    regions += sorted({r.key for r in m.geo} - set(regions))
    rcol = {
        r: ("dggray!60" if r == UNKNOWN_REGION else _REGION_PALETTE[i % len(_REGION_PALETTE)])
        for i, r in enumerate(regions)
    }
    grows, gids = _compare_rows(segs_t, m.region_of, regions, rcol, m.geo)
    o.append(
        r"\begin{panel}{Capital by region per segment, against the market share of dollars}"
        r"\centering"
        + stacked_rows(grows, [(r, rcol[r]) for r in regions], 11.5, bar_h=0.34)
        + r"\end{panel}"
    )
    o.append(
        source_line(
            m,
            gids,
            "Lighter bars: market share of dollars for the matching period; pale "
            "remainder: regions the file does not list.",  # fmt: skip
        )
    )
    reg_groups: dict[str, Group] = {}
    for p in union:
        reg_groups.setdefault(m.region_of(p), Group()).add(p, estimates)
    o.append(
        _table(
            ["Region", "Positions", "Capital", "Share", "TVPI at cost"],
            "X r r r r",
            [
                [
                    tex(r),
                    str(g.n),
                    money(g.invested),
                    tex(_pct(g.invested / total.invested if total.invested else None)),
                    multiple(g.tvpi),
                ]
                for r, g in sorted(reg_groups.items(), key=lambda kv: -kv[1].invested)
            ],
        )
    )
    o.append(
        r"{\tiny\color{dggray}"
        + tex(
            "Region from the market file's company_geo map; positions without an entry are "
            "Unknown."
        )
        + "}"
    )

    # ---- sectoral
    o.append(r"\Needspace{0.35\textheight}\dsec{Sectoral}")
    ai_keys = {r.key for r in m.sectors if r.key.strip().lower() == "ai"}
    bucket_fn = lambda p: bucket_of(p, cfg)  # noqa: E731
    buckets = bucket_order(
        cfg, {bucket_fn(p) for p in union} | ({r.key for r in m.sectors} - ai_keys)
    )
    bcol = bucket_colours(cfg, buckets)
    srows, sids = _compare_rows(segs_t, bucket_fn, buckets, bcol, m.sectors, ai_keys)
    o.append(
        r"\begin{panel}{Capital by thesis bucket per segment, against the market share of "
        r"dollars}\centering"
        + stacked_rows(srows, [(cfg.bucket_label(b), bcol[b]) for b in buckets], 11.5, bar_h=0.34)
        + r"\end{panel}"
    )
    o.append(
        source_line(m, sids, "Lighter bars: market share of dollars for the matching period.")
    )
    port = _shares(_capital_by(union, bucket_fn))
    ow = [
        (cfg.bucket_label(b), port.get(b, 0.0) - smk[b].share_dollars)  # type: ignore[operator]
        for b in buckets
        if b in smk and smk[b].share_dollars is not None
    ]
    if ow:
        o.append(
            r"\begin{panel}{Over- and under-weight against the market"
            + tex(f" ({speriod})" if speriod else "")
            + r": portfolio share minus market share of dollars}\centering"
            + diverging_hbar(ow)
            + r"\end{panel}"
        )
        o.append(source_line(m, [smk[b].source for b in buckets if b in smk]))
    ai_rows = [r for r in m.sectors if r.key in ai_keys]
    if ai_rows:
        ai_cap = sum(p.invested for p in union if _AI_RE.search(p.market))
        o.append(r"\dsub{AI across sectors}")
        o.append(
            _table(
                ["Market row", "Period", "Scope", "Share of dollars", "Share of deals", "Source"],
                "X l l r r l",
                [
                    [
                        tex(r.key),
                        tex(r.period),
                        tex(r.scope),
                        tex(_pct(r.share_dollars)),
                        tex(_pct(r.share_deals)),
                        tex(m.cite([r.source])),
                    ]
                    for r in ai_rows
                ],
            )
        )
        o.append(
            r"{\tiny\color{dggray}"
            + tex(
                f"AI cuts across the thesis buckets, so it is shown separately. Portfolio: "
                f"{_pct(ai_cap / total.invested if total.invested else None)} of capital in "
                "positions whose AngelList market label names AI."
            )
            + r"}\par"
        )

    # ---- stage
    o.append(r"\Needspace{0.35\textheight}\dsec{Stage}")
    st_order = [s for s in ENTRY_STAGES if any(normalise_stage(p) == s for p in union)]
    strows = []
    for lab, ps, _years in segs_t:
        sh = _shares(_capital_by(ps, normalise_stage))
        strows.append(
            (lab, [(sh.get(s, 0.0), _STAGE_COLOR[s], _pct(sh.get(s))) for s in st_order])
        )
    o.append(
        r"\begin{panel}{Capital by entry stage (CSV round label, normalised)}\centering"
        + stacked_rows(strows, [(s, _STAGE_COLOR[s]) for s in st_order], 11.5, bar_h=0.34)
        + r"\end{panel}"
    )
    if ratios:
        by_stage: dict[str, list[tuple[float, str]]] = {}
        for r in ratios:
            by_stage.setdefault(r.stage, []).append((r.ratio, _STAGE_COLOR[r.stage]))
        vals = [r.ratio for r in ratios]
        o.append(
            r"\begin{panel}{Entry post-money / market median post-money, same stage and year "
            r"(log scale)}\centering"
            + strip_chart(
                [(s, by_stage[s]) for s in ENTRY_STAGES if s in by_stage],
                10.0,
                vmin=min(0.25, min(vals) / 1.5),
                vmax=max(4.0, max(vals) * 1.5),
            )
            + r"\par\vspace{2pt}{\tiny\color{dggray}"
            + tex(
                f"{len(ratios)} positions shown; {excluded} excluded (no cap, non-USD cap, or no "
                "benchmark for the stage and year). Pre-money caps count as pre + round; seed+ "
                "compares with seed. Right of the line: entry above the market median."
            )
            + r"}\end{panel}"
        )
        o.append(source_line(m, [r.benchmark.source for r in ratios]))
    if m.graduation:
        grow = [
            [
                tex(g.cohort),
                tex(f"{g.from_stage} to {g.to_stage}"),
                tex(f"{g.window_months} mo" if g.window_months else "--"),
                tex(_pct(g.rate)),
                tex(m.cite([g.source])),
            ]
            for g in m.graduation
        ]
        if estimates is not None:
            seed_ps = [p for p in union if benchmark_stage(normalise_stage(p)) == "seed"]
            priced = 0
            for p in seed_ps:
                e = estimates.for_position(p)
                priced += int(bool(e and e.evidence == "priced_round"))
            grow.append(
                [
                    r"\textbf{" + tex("Portfolio (locked estimates)") + "}",
                    tex("seed to a later priced round"),
                    "--",
                    tex(_pct(priced / len(seed_ps) if seed_ps else None)),
                    tex(f"{priced} of {len(seed_ps)} seed positions"),
                ]
            )
        o.append(r"\dsub{Graduation rates}")
        o.append(_table(["Cohort", "Step", "Window", "Rate", "Source"], "X l r r l", grow))
        if estimates is not None:
            o.append(
                r"{\tiny\color{dggray}"
                + tex(
                    "Portfolio row: seed-stage positions whose locked estimate cites a later "
                    "priced round, as a share of all seed-stage positions. Marked positions are "
                    "not counted, so this is a lower bound."
                )
                + "}"
            )

    # ---- commentary
    if any(m.commentary.values()):
        o.append(r"\Needspace{0.2\textheight}\dsec{Commentary}")
        for key, title in (
            ("overall", "Overall"),
            ("geographic", "Geographic"),
            ("sectoral", "Sectoral"),
            ("stage", "Stage"),
            ("implications", "Implications"),
        ):
            items = m.commentary.get(key) or []
            if items:
                o.append(r"\dsub{" + tex(title) + r"}\begin{itemize}")
                o += [r"\item " + tex(x) for x in items]
                o.append(r"\end{itemize}")

    # ---- sources
    o.append(r"\Needspace{0.2\textheight}\dsec{Sources}")
    o.append(r"{\scriptsize\begin{enumerate}[leftmargin=1.6em,itemsep=1pt]")
    for s in m.sources:
        u = tex_url(s.url) if s.url else None
        # Show only the host as link text: full URLs overflow the margin.
        link = rf" \href{{{u}}}{{{tex(urlsplit(s.url).netloc or s.url)}}}" if u else ""
        period = f", {s.period}" if s.period else ""
        o.append(r"\item " + tex(f"{s.label} ({s.id}{period}).") + link)
    o.append(r"\end{enumerate}}")
    o.append(
        method_block(
            brand,
            meta.as_of,
            "Market comparison: benchmarks from the operator's market file, each cited by "
            "source id. A segment is compared with the market period sharing the most calendar "
            "years with it (ties: closest span, then earlier). The market median TVPI for the "
            "vintage mix weights each vintage median by the capital invested in that year. Stage "
            "benchmarks match stage and year, preferring the company's region, then global, then "
            "US. Shares use global scope where both global and US rows exist. ",
        )
    )
    o.append(r"\end{document}")
    return with_glossary("\n".join(x for x in o if x))
