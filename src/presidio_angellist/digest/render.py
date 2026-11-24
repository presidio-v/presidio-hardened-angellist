"""
Build the LaTeX source for a vintage or aggregate digest.

Rule for this module: a value that came from the CSV, the content JSON, the gate
config or the brand config reaches the output only through :func:`tex`,
:func:`tex_url`, or one of the numeric formatters in :mod:`latex` (which emit
digits and fixed markup only). Literal LaTeX in this file is the only markup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from presidio_angellist.digest.gate import GateConfig, GateResult, gate_retro
from presidio_angellist.digest.latex import (
    grouped_columns,
    hbar_chart,
    money,
    multiple,
    pct,
    short_name,
    stacked_bar,
    tex,
    tex_url,
)
from presidio_angellist.digest.metrics import (
    MULTIPLE_BUCKETS,
    AggregateMetrics,
    aggregate,
    gate_verdict_sentence,
)

if TYPE_CHECKING:
    from presidio_angellist.digest.config import Brand
    from presidio_angellist.digest.csvload import Position

STATUS_COLOR = {
    "Ahead": "dgaccent",
    "On track": "dgblue",
    "Behind": "dgred",
    "No signal": "dggray",
}
VERDICT_COLOR = {"Pass": "dgaccent", "Borderline": "dgamber", "Fail": "dgred"}
DOT_COLOR = {"yes": "dgaccent", "open": "dgamber", "no": "dgred"}
_THESIS_PALETTE = ("dgnavy", "dgaccent", "dgblue", "dgsteel", "dgteal", "dgnavy!60")
_AVOID_PALETTE = ("dgred", "dgred!65", "dgred!45", "dgred!30")

LOGO_NAME = "logo"


@dataclass
class DocMeta:
    """Identity of one generated document."""

    quarter: str
    as_of: str
    label: str  # "2026 vintage" / "2017-2020"
    version: str = "1.0"
    state: str = "draft"


def the(label: str) -> str:
    """Prefix a gate label with an article for running text ("the LP decision gate")."""
    return label if label.lower().startswith(("the ", "our ", "my ")) else f"the {label}"


def doc_id(brand: Brand, meta: DocMeta) -> str:
    return (
        f"{brand.doc_id_prefix}-{meta.quarter} · {meta.label} · v{meta.version} · "
        f"{meta.state} {meta.as_of}"
    )


# ---------------------------------------------------------------------------
# Preamble and shared blocks
# ---------------------------------------------------------------------------


def preamble(brand: Brand, meta: DocMeta, logo_ext: str | None) -> str:
    c = brand.colors
    colours = "".join(
        rf"\definecolor{{dg{name}}}{{HTML}}{{{c[key]}}}"
        for name, key in (
            ("navy", "navy"),
            ("accent", "accent"),
            ("light", "light"),
            ("gray", "gray"),
            ("blue", "blue"),
            ("red", "red"),
            ("amber", "amber"),
            ("pale", "pale"),
            ("classbg", "class_bg"),
            ("classfg", "class_fg"),
        )
    )
    logo = (
        rf"\raisebox{{-0.35\height}}{{\includegraphics[height=0.75cm]{{{LOGO_NAME}{logo_ext}}}}}"
        r"\hspace{0.5em}"
        if logo_ext
        else ""
    )
    tagline = (
        rf"\hspace{{0.4em}}{{\small\color{{gray}}{tex(brand.tagline)}}}" if brand.tagline else ""
    )
    return "\n".join(
        [
            r"\documentclass[10pt,a4paper]{article}",
            r"\usepackage[margin=2cm,top=2.6cm,bottom=2.4cm]{geometry}",
            r"\usepackage{fontspec}",
            rf"\IfFontExistsTF{{{brand.font}}}{{\setmainfont{{{brand.font}}}}}"
            rf"{{\setmainfont{{{brand.fallback_font}}}}}",
            r"\usepackage{xcolor,graphicx,fancyhdr,lastpage,tikz,tabularx,array,enumitem,"
            r"booktabs,multicol,needspace}",
            r"\usepackage[most]{tcolorbox}",
            r"\usepackage[colorlinks=true,linkcolor=dgaccent,urlcolor=dgaccent]{hyperref}",
            colours,
            r"\colorlet{dgsteel}{dgblue!60!dggray}\colorlet{dgteal}{dgaccent!55!dgblue}",
            r"\setlength{\parindent}{0pt}\setlength{\parskip}{4pt}",
            r"\pagestyle{fancy}\fancyhf{}",
            rf"\fancyhead[L]{{{logo}\textbf{{\color{{dgnavy}}{tex(brand.name)}}}{tagline}}}",
            rf"\fancyhead[R]{{\small\color{{gray}}"
            rf"{tex(brand.header_text)} · {tex(meta.quarter)}}}",
            rf"\fancyfoot[L]{{\footnotesize\color{{gray}}{tex(doc_id(brand, meta))}}}",
            r"\fancyfoot[C]{\footnotesize\color{gray}\thepage\,/\,\pageref{LastPage}}",
            (
                rf"\fancyfoot[R]{{\colorbox{{dgclassbg}}{{\footnotesize\bfseries"
                rf"\color{{dgclassfg}}{tex(brand.classification)}}}}}"
                if brand.classification
                else ""
            ),
            r"\renewcommand{\headrulewidth}{0.4pt}\renewcommand{\footrulewidth}{0.4pt}"
            r"\setlength{\headheight}{28pt}",
            r"\fancypagestyle{plain}{}",
            r"\newcommand{\dsec}[1]{\par\Needspace{10\baselineskip}\vspace{6pt}"
            r"{\Large\bfseries\color{dgnavy}#1}\par\vspace{2pt}"
            r"{\color{dgaccent}\rule{2.2cm}{1.6pt}}\par\vspace{4pt}}",
            r"\newcommand{\dsub}[1]{\par\vspace{3pt}{\normalsize\bfseries\color{dgnavy}#1}\par}",
            r"\newcommand{\pill}[2]{\tcbox[on line,colback=#1,colframe=#1,coltext=white,"
            r"boxsep=1pt,left=3pt,right=3pt,top=0pt,bottom=0pt,arc=5pt,"
            r"fontupper=\scriptsize\bfseries]{#2}}",
            r"\newcommand{\gdot}[1]{\tikz[baseline=-0.6ex]\fill[#1] (0,0) circle (3.2pt);}",
            r"\newtcolorbox{kpi}{colback=dgpale,colframe=dgpale,arc=2pt,boxsep=2pt,left=5pt,"
            r"right=5pt,top=4pt,bottom=4pt,valign=top}",
            r"\newtcolorbox{card}[1]{enhanced,breakable=false,colback=white,colframe=dglight,"
            r"boxrule=0.8pt,arc=3pt,borderline west={3pt}{0pt}{#1},left=8pt,right=8pt,top=6pt,"
            r"bottom=6pt,before skip=6pt,after skip=6pt}",
            r"\newtcolorbox{panel}[1]{colback=white,colframe=dglight,arc=3pt,left=4pt,right=4pt,"
            r"title={\bfseries #1},colbacktitle=dgpale,coltitle=dgnavy,fonttitle=\small}",
            r"\setlist[itemize]{leftmargin=1.1em,itemsep=1pt,topsep=2pt,parsep=0pt,"
            r"label={\color{dgaccent}\textbullet}}",
            r"\begin{document}",
        ]
    )


def kpi(value: str, label: str) -> str:
    """``value`` is fixed markup from a numeric formatter; ``label`` is raw text."""
    return (
        r"\begin{kpi}{\LARGE\bfseries\color{dgnavy}" + value + r"}\\[1pt]"
        r"{\scriptsize\color{dggray}" + tex(label) + r"}\end{kpi}"
    )


def kpi_row(tiles: list[tuple[str, str]], columns: int | None = None) -> str:
    cols = columns or len(tiles)
    return "\n".join(
        [rf"\begin{{tcbraster}}[raster columns={cols},raster equal height,raster column skip=4pt]"]
        + [kpi(v, lab) for v, lab in tiles]
        + [r"\end{tcbraster}"]
    )


def title_block(kicker: str, title: str, subtitle: str, headline: str) -> str:
    o = [
        r"{\color{dggray}\small " + tex(kicker.upper()) + r"}\par\vspace{2pt}",
        r"{\fontsize{24}{28}\selectfont\bfseries\color{dgnavy}"
        + tex(title)
        + r"}\par\vspace{2pt}",
        r"{\color{dggray}" + tex(subtitle) + r"}\par\vspace{8pt}",
    ]
    if headline:
        o.append(
            r"\begin{tcolorbox}[colback=dgnavy,colframe=dgnavy,coltext=white,arc=3pt,left=10pt,"
            r"right=10pt,top=8pt,bottom=8pt]{\large " + tex(headline) + r"}\end{tcolorbox}"
        )
    return "\n".join(o)


def boxed_lists(boxes: list[tuple[str, list[str], str]], env: str = "itemize") -> str:
    boxes = [b for b in boxes if b[1]]
    if not boxes:
        return ""
    o = [
        rf"\begin{{tcbraster}}[raster columns={len(boxes)},raster equal height,"
        r"raster column skip=8pt]"
    ]
    opts = "[leftmargin=1.3em,itemsep=2pt]" if env == "enumerate" else ""
    for title, items, col in boxes:
        o.append(
            rf"\begin{{tcolorbox}}[colback=white,colframe={col},boxrule=0.8pt,arc=3pt,"
            rf"title={{\bfseries {tex(title)}}},colbacktitle={col},coltitle=white,"
            rf"fonttitle=\small,left=6pt,right=6pt]\small\begin{{{env}}}{opts}"
        )
        o += [r"\item " + tex(i) for i in items]
        o.append(rf"\end{{{env}}}\end{{tcolorbox}}")
    o.append(r"\end{tcbraster}")
    return "\n".join(o)


def summary_block(content: dict[str, Any], with_extremes: bool = True) -> str:
    s = content.get("summary", {})
    paras = s.get("paragraphs", [])
    if not paras and not (with_extremes and (s.get("strongest") or s.get("weakest"))):
        return ""
    o = [r"\dsec{Summary}"]
    o += [tex(p) + r"\par" for p in paras]
    if with_extremes:
        o.append(
            boxed_lists(
                [
                    ("Strongest", s.get("strongest", []), "dgaccent"),
                    ("Weakest", s.get("weakest", []), "dgred"),
                ]
            )
        )
    return "\n".join(o)


def actions_block(content: dict[str, Any]) -> str:
    s = content.get("summary", {})
    if not (s.get("actions") or s.get("lessons_for_gate")):
        return ""
    return "\n".join(
        [
            r"\dsec{Actions and lessons}",
            boxed_lists(
                [
                    ("Actions", s.get("actions", []), "dgnavy"),
                    ("Lessons for the gate", s.get("lessons_for_gate", []), "dgaccent"),
                ],
                env="enumerate",
            ),
        ]
    )


def gate_check_items(cfg: GateConfig, content: dict[str, Any]) -> list[str]:
    """Gate wording: from content if given, else derived from the config's own numbers."""
    given = content.get("thesis", {}).get("gate_checks") or []
    if given:
        return list(given)
    stages = ", ".join(cfg.stage_allowed)
    sizes = "; ".join(
        f"{st} round at most ${v / 1e6:,.0f}M" for st, v in cfg.max_round_size.items()
    )
    sizing = f"at most ${cfg.per_lead_per_year / 1e3:,.0f}k per lead per year"
    if cfg.per_company_max is not None:
        sizing += f", ${cfg.per_company_max / 1e3:,.0f}k per company"
    if cfg.standard_ticket is not None:
        sizing = f"${cfg.standard_ticket / 1e3:,.0f}k standard ticket; " + sizing
    return [
        f"Stage: {stages} ({sizes}).",
        "Sector: on-thesis buckets ("
        + ", ".join(cfg.bucket_label(b) for b in cfg.on_thesis)
        + "); the avoid-list ("
        + ", ".join(cfg.bucket_label(b).removeprefix("Avoid: ") for b in cfg.avoid)
        + ") is a hard no.",
        f"Valuation: norm up to ${cfg.cap_yes_max / 1e6:,.0f}M; hard ceiling "
        f"${cfg.cap_no_above / 1e6:,.0f}M post-money (a pre-money cap counts as pre + round).",
        "Lead: a listed top lead stands in for the investor's own judgement of core risk.",
        f"Sizing: {sizing}.",
    ]


def thesis_block(cfg: GateConfig, content: dict[str, Any], as_of: str, note_title: str) -> str:
    th = content.get("thesis", {})
    label = content.get("gate_label") or cfg.label
    o = [r"\dsec{Investment thesis}"]
    if th.get("statement"):
        o.append(r"{\large\color{dgnavy}" + tex(th["statement"]) + r"}\par\vspace{4pt}")
    pillars = th.get("pillars") or []
    if pillars:
        o.append(
            rf"\begin{{tcbraster}}[raster columns={min(4, len(pillars))},raster equal height,"
            r"raster column skip=5pt]"
        )
        for pl in pillars:
            o.append(
                r"\begin{tcolorbox}[colback=dgpale,colframe=dgpale,"
                r"borderline north={2pt}{0pt}{dgaccent},arc=2pt,left=5pt,right=5pt]"
                r"{\small\bfseries\color{dgnavy}" + tex(pl.get("title")) + r"}\\[2pt]"
                r"{\scriptsize " + tex(pl.get("text")) + r"}\end{tcolorbox}"
            )
        o.append(r"\end{tcbraster}")
    o.append(r"\dsub{" + tex(f"{label} ({as_of})") + "}")
    o.append(
        r"{\small "
        + tex("The checks an investments export can answer; an unknown fact counts as no.")
        + "}"
    )
    o.append(r"\begin{multicols}{2}\scriptsize\begin{enumerate}[leftmargin=1.4em,itemsep=0pt]")
    o += [r"\item " + tex(item) for item in gate_check_items(cfg, content)]
    o.append(r"\end{enumerate}\end{multicols}")
    if th.get("vintage_note"):
        o.append(
            r"\begin{tcolorbox}[colback=white,colframe=dgamber,boxrule=0.8pt,arc=3pt,left=8pt,"
            r"right=8pt]\small\textbf{\color{dgamber}"
            + tex(note_title)
            + r"} "
            + tex(th["vintage_note"])
            + r"\end{tcolorbox}"
        )
    return "\n".join(o)


def bucket_colours(cfg: GateConfig, buckets: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, b in enumerate(cfg.on_thesis):
        out[b] = _THESIS_PALETTE[i % len(_THESIS_PALETTE)]
    for i, b in enumerate(cfg.avoid):
        out[b] = _AVOID_PALETTE[i % len(_AVOID_PALETTE)]
    for b in buckets:
        out.setdefault(b, "dggray!70")
    return out


def bucket_order(cfg: GateConfig, buckets: set[str]) -> list[str]:
    known = cfg.on_thesis + ["other"] + cfg.avoid
    return [b for b in known if b in buckets] + sorted(buckets - set(known))


def capital_by_bucket(cfg: GateConfig, positions: list[Position], gate: list[GateResult]) -> str:
    by_b: dict[str, float] = {}
    for p, g in zip(positions, gate, strict=True):
        by_b[g.bucket] = by_b.get(g.bucket, 0.0) + p.invested
    cols = bucket_colours(cfg, list(by_b))
    parts = [(cfg.bucket_label(b), by_b[b], cols[b]) for b in bucket_order(cfg, set(by_b))]
    return r"\dsub{Capital by thesis bucket}" + "\n" + stacked_bar(parts) + r"\par\vspace{6pt}"


def method_block(brand: Brand, as_of: str, extra: str = "") -> str:
    text = (
        f"Positions, tickets, caps, leads and marks: AngelList investment export of {as_of}. "
        "Marks below 1.0x on young positions mostly reflect SPV fee drag, not company news; "
        "locked positions have no mark yet. Status, signals and forecasts: advisor review of "
        "public sources, searched by company name only; many figures are company claims or "
        "aggregator estimates. Probabilities are judgement. Gate retro-check: computed from "
        "the AngelList record against the gate configuration. " + extra + "Not investment "
        "advice; for the investor's own use."
    )
    return (
        r"\dsec{Method}"
        + "\n"
        + r"{\scriptsize\color{dgnavy}"
        + tex(text)
        + (
            r" \textbf{" + tex(brand.classification_note) + "}"
            if brand.classification_note
            else ""
        )
        + "}"
    )


def sources_line(entry: dict[str, Any]) -> str:
    links = []
    for s in entry.get("sources", []):
        u = tex_url(s.get("url"))
        if u:
            links.append(rf"\href{{{u}}}{{{tex(s.get('label'))}}}")
    return (r"{\tiny\color{dggray}Sources: " + ", ".join(links) + "}") if links else ""


def card(
    title: str,
    entry: dict[str, Any],
    facts: list[tuple[str, str]],
    pills: list[tuple[str, str]],
    fallback_line: str,
    *,
    show_prob: bool,
    watch_label: str = "Watch next quarter",
) -> str:
    """One company card. ``facts`` values must already be escaped/fixed markup."""
    st = entry.get("status", "No signal")
    col = STATUS_COLOR.get(st, "dggray")
    o = [r"\begin{card}{" + col + "}"]
    o.append(
        r"\begin{minipage}[t]{0.30\textwidth}\vspace{0pt}"
        r"{\large\bfseries\color{dgnavy}" + tex(title) + r"}\\[1pt]"
        r"{\scriptsize\color{dggray}" + tex(entry.get("one_liner") or fallback_line) + r"}"
        r"\par\vspace{4pt}"
        + r"\ ".join(rf"\pill{{{pc}}}{{{tex(pt)}}}" for pc, pt in pills)
        + r"\par\vspace{5pt}"
        r"{\scriptsize\renewcommand{\arraystretch}{1.1}"
        r"\begin{tabular}{@{}>{\color{dggray}}l@{\hspace{4pt}}l@{}}"
        + r"\\".join(f"{tex(a)} & {b}" for a, b in facts)
        + r"\end{tabular}}\par\vspace{5pt}"
    )
    pr = entry.get("p_up_round")
    if show_prob and isinstance(pr, float):
        o.append(
            r"{\scriptsize\color{dggray}P(up-round) \textbf{\color{dgnavy}"
            + f"{pr * 100:.0f}"
            + r"\%}}\par\tikz{\fill[dglight] (0,0) rectangle (4.4,0.16);\fill["
            + col
            + f"] (0,0) rectangle ({4.4 * pr:.2f},0.16);"
            + "}"
        )
    o.append(r"\end{minipage}\hfill\begin{minipage}[t]{0.66\textwidth}\vspace{0pt}\small")
    if entry.get("signals"):
        o.append(r"{\scriptsize\bfseries\color{dgaccent}SIGNALS SO FAR}\begin{itemize}")
        o += [r"\item " + tex(x) for x in entry["signals"]]
        o.append(r"\end{itemize}")
    for lab, key in (("Forecast", "forecast"), ("Key risk", "key_risk"), (watch_label, "watch")):
        if entry.get(key):
            o.append(r"\textbf{\color{dgnavy}" + tex(lab) + r".} " + tex(entry[key]) + r"\par")
    o.append(sources_line(entry))
    if not any(entry.get(k) for k in ("signals", "forecast", "key_risk", "watch")):
        o.append(r"{\color{dggray}No advisor assessment this quarter.}")
    o.append(r"\end{minipage}\end{card}")
    return "\n".join(o)


def _instrument(p: Position) -> str:
    return p.instrument.upper() if p.instrument.lower() == "safe" else p.instrument


# ---------------------------------------------------------------------------
# Vintage digest (one year, per-company cards)
# ---------------------------------------------------------------------------


def build_vintage_tex(
    positions: list[Position],
    cfg: GateConfig,
    content: dict[str, Any],
    brand: Brand,
    meta: DocMeta,
    vintage: int,
    logo_ext: str | None = None,
) -> str:
    gate = gate_retro(positions, cfg)
    comp: dict[str, dict[str, Any]] = content.get("companies", {})
    n = len(positions)
    total = sum(p.invested for p in positions)
    marked = [p for p in positions if p.net is not None]
    mk_cost = sum(p.invested for p in marked)
    mk_val = sum(p.net or 0.0 for p in marked)
    caps = sorted(p.post_cap for p in positions if p.post_cap)
    med_cap = caps[len(caps) // 2] if caps else None
    probs = [comp.get(p.name, {}).get("p_up_round") for p in positions]
    exp_up = sum(x for x in probs if isinstance(x, float))
    passes = sum(1 for g in gate if g.verdict == "Pass")
    fails = sum(1 for g in gate if g.verdict == "Fail")
    label = content.get("gate_label") or cfg.label

    o = [preamble(brand, meta, logo_ext)]
    o.append(
        title_block(
            f"{brand.header_text} · {meta.quarter} · as of {meta.as_of}",
            f"{vintage} Investments",
            f"AngelList syndicate positions of the {vintage} vintage, reviewed against the "
            f"{brand.name} thesis and {the(label)}.",
            content.get("headline", ""),
        )
    )
    tiles = [
        (str(n), "positions"),
        (money(total), "capital deployed"),
        (money(med_cap), "median entry cap (post)"),
        (
            multiple(mk_val / mk_cost) if mk_cost else "--",
            f"mark on {len(marked)} marked; {n - len(marked)} locked",
        ),
    ]
    if any(isinstance(x, float) for x in probs):
        tiles.append((f"{exp_up:.1f}", "expected up-rounds (12-24 mo)"))
    tiles.append((f"{passes}/{n}", f"would pass {the(label)} today"))
    o.append(kpi_row(tiles))
    o.append(summary_block(content))
    o.append(thesis_block(cfg, content, meta.as_of, f"The {vintage} vintage and the thesis."))

    # ---- portfolio graphics
    o.append(r"\dsec{Portfolio at a glance}")
    o.append(capital_by_bucket(cfg, positions, gate))
    ceiling, norm, lim = cfg.cap_no_above, cfg.cap_yes_max, cfg.per_lead_per_year
    rows = []
    for p in sorted(positions, key=lambda p: -(p.post_cap or 0)):
        pc = p.post_cap
        col = (
            "dggray"
            if pc is None
            else ("dgred" if pc > ceiling else "dgamber" if pc > norm else "dgaccent")
        )
        rows.append((short_name(p.name), pc, col))
    vmax = max([r[1] for r in rows if r[1]] + [ceiling]) * 1.6
    lead_tot: dict[str, float] = {}
    for p in positions:
        lead_tot[p.lead or "(no lead)"] = lead_tot.get(p.lead or "(no lead)", 0.0) + p.invested
    lrows = [
        (ld, v, "dgred" if v > lim + 1 else "dgblue")
        for ld, v in sorted(lead_tot.items(), key=lambda x: -x[1])
    ]
    o.append(r"\begin{tcbraster}[raster columns=2,raster column skip=10pt,raster equal height]")
    o.append(
        r"\begin{panel}{Entry cap, post-money (log scale)}\centering"
        + hbar_chart(
            rows,
            4.6,
            vmax,
            money,
            refs=[(norm, "norm", "dgamber"), (ceiling, "ceiling", "dgred")],
            log=True,
            vmin=max(min([r[1] for r in rows if r[1]] + [norm]) / 2, 1e5),
        )
        + r"\par\vspace{2pt}{\tiny\color{dggray}Pre-money caps shown as pre + round. "
        r"Grey: no cap.}\end{panel}"
    )
    o.append(
        r"\begin{panel}{Capital by syndicate lead}\centering"
        + hbar_chart(
            lrows,
            3.9,
            max(max(lead_tot.values(), default=0.0), lim) * 1.15,
            money,
            refs=[(lim, "per-lead limit", "dgred")],
        )
        + r"\par\vspace{2pt}{\tiny\color{dggray}"
        + tex(f"Gate limit: ${lim / 1e3:,.0f}k per lead per year.")
        + r"}\end{panel}"
    )
    o.append(r"\end{tcbraster}")
    if any(isinstance(x, float) for x in probs):
        prow = []
        for p in sorted(positions, key=lambda p: -(comp.get(p.name, {}).get("p_up_round") or 0)):
            c = comp.get(p.name, {})
            pr = c.get("p_up_round")
            prow.append(
                (
                    short_name(p.name),
                    pr * 100 if isinstance(pr, float) else None,
                    STATUS_COLOR.get(c.get("status", ""), "dggray"),
                )
            )
        legend = r"\quad".join(rf"\gdot{{{col}}}\,{tex(st)}" for st, col in STATUS_COLOR.items())
        o.append(
            r"\begin{panel}{Outlook: probability of a priced up-round above our entry cap "
            r"within 12--24 months}\centering"
            + hbar_chart(prow, 10.5, 100, lambda v: f"{v:.0f}\\%", bar_h=0.3, gap=0.1)
            + r"\par\vspace{3pt}{\scriptsize "
            + legend
            + r"}\par{\tiny\color{dggray}Advisor judgement, not model output. Colour = status "
            r"so far. Sum of probabilities = "
            + f"{exp_up:.1f}"
            + r" expected up-rounds.}\end{panel}"
        )

    # ---- gate retro matrix
    o.append(r"\Needspace{0.42\textheight}\dsec{Gate retro-check}")
    o.append(
        r"{\small "
        + tex(
            f"How each {vintage} position scores against {the(label)} on the facts in the "
            "AngelList record. Checks that need the original invite are not scored. "
            f"{passes} pass, {n - passes - fails} borderline, {fails} fail."
        )
        + r"}\par\vspace{2pt}"
    )
    o.append(gate_matrix(positions, gate, cfg))

    # ---- cards
    o.append(r"\newpage\dsec{Company cards}")
    for p, g in zip(positions, gate, strict=True):
        c = comp.get(p.name, {})
        cap_s = (
            "no cap"
            if p.cap is None
            else f"{money(p.cap)} {tex(p.cap_type.replace('-money', '').lower())}"
        )
        if p.discount and p.discount not in ("0%", ""):
            cap_s += f", {tex(p.discount)} discount"
        facts = [
            ("Invested", f"{money(p.invested)} · {p.invest_date.strftime('%d %b %Y')}"),
            ("Round", f"{tex(p.stage)} · {money(p.round_size)} · {tex(_instrument(p))}"),
            ("Cap", cap_s),
            ("Lead", tex(p.lead)),
            ("Bucket", tex(cfg.bucket_label(g.bucket))),
            ("Mark", multiple(p.multiple) if p.multiple is not None else "locked"),
        ]
        o.append(
            card(
                p.name,
                c,
                facts,
                [
                    (
                        STATUS_COLOR.get(c.get("status", ""), "dggray"),
                        c.get("status", "No signal"),
                    ),
                    (VERDICT_COLOR[g.verdict], f"Gate: {g.verdict}"),
                ],
                p.market,
                show_prob=True,
            )
        )
    o.append(actions_block(content))
    o.append(
        method_block(
            brand,
            meta.as_of,
            "Base rate: roughly 15-30% of seed companies raise a priced Series A within two "
            "years. ",
        )
    )
    o.append(r"\end{document}")
    return "\n".join(x for x in o if x)


def gate_matrix(positions: list[Position], gate: list[GateResult], cfg: GateConfig) -> str:
    o = [
        r"{\scriptsize\renewcommand{\arraystretch}{1.25}"
        r"\begin{tabularx}{\textwidth}{@{}l l c c c c c X r@{}}\toprule",
        r"\textbf{Company} & \textbf{Bucket} & \textbf{Stage} & \textbf{Sector} & \textbf{Cap} & "
        r"\textbf{Lead} & \textbf{Size} & \textbf{Why} & \textbf{Verdict}\\\midrule",
    ]
    for p, g in zip(positions, gate, strict=True):
        cells = " & ".join(
            rf"\gdot{{{DOT_COLOR[g.checks[c][0]]}}}"
            for c in ("stage", "sector", "cap", "lead", "size")
        )
        o.append(
            f"{tex(short_name(p.name))} & {tex(cfg.bucket_label(g.bucket))} & {cells} & "
            f"{tex(g.reasons)} & " + rf"\pill{{{VERDICT_COLOR[g.verdict]}}}{{{g.verdict}}}\\"
        )
    o.append(r"\bottomrule\end{tabularx}}\par")
    o.append(
        r"{\tiny\color{dggray}\gdot{dgaccent} yes\quad\gdot{dgamber} open / qualified\quad"
        r"\gdot{dgred} no. Lead shows only the top-lead substitute; the investor's own judgement "
        r"of core risk is not scored. Size counts the running total per lead per calendar year "
        r"in date order.}"
    )
    return "\n".join(o)


# ---------------------------------------------------------------------------
# Aggregate digest (band of years)
# ---------------------------------------------------------------------------


def _table(header: list[str], aligns: str, rows: list[list[str]]) -> str:
    """``header`` is raw text; ``rows`` cells must already be escaped/fixed markup."""
    return "\n".join(
        [
            r"{\scriptsize\renewcommand{\arraystretch}{1.2}"
            rf"\begin{{tabularx}}{{\textwidth}}{{@{{}}{aligns}@{{}}}}\toprule",
            " & ".join(rf"\textbf{{{tex(h)}}}" for h in header) + r"\\\midrule",
        ]
        + [" & ".join(r) + r"\\" for r in rows]
        + [r"\bottomrule\end{tabularx}}\par"]
    )


def _match_positions(name: str, positions: list[Position]) -> list[Position]:
    exact = [p for p in positions if p.name == name]
    if exact:
        return exact
    key = short_name(name).strip().lower()
    return [p for p in positions if short_name(p.name).strip().lower() == key]


def build_aggregate_tex(
    positions: list[Position],
    cfg: GateConfig,
    content: dict[str, Any],
    brand: Brand,
    meta: DocMeta,
    band: tuple[int, int],
    logo_ext: str | None = None,
) -> str:
    gate = gate_retro(positions, cfg)
    m: AggregateMetrics = aggregate(positions, gate)
    first, last = band
    band_s = f"{first}-{last}" if last != first else str(first)
    label = content.get("gate_label") or cfg.label

    o = [preamble(brand, meta, logo_ext)]
    o.append(
        title_block(
            f"{brand.header_text} · {meta.quarter} · as of {meta.as_of}",
            f"{band_s} Portfolio",
            f"AngelList syndicate positions made {band_s}, aggregated, and checked against the "
            f"{brand.name} thesis and {the(label)}.",
            content.get("headline", ""),
        )
    )
    t = m.total
    o.append(
        kpi_row(
            [
                (str(t.n), f"positions ({m.locked} locked)"),
                (money(t.invested), "invested"),
                (money(t.realized), "realized"),
                (money(m.unrealized), "unrealized (marked)"),
                (multiple(m.dpi), "DPI, all capital invested"),
            ]
        )
    )
    o.append(r"\vspace{-4pt}")
    o.append(
        kpi_row(
            [
                (multiple(t.tvpi), "TVPI, locked at cost"),
                (multiple(t.tvpi_marked), f"TVPI, {t.n_marked} marked only"),
                (pct(m.zero_share), "of marked positions at 0x"),
                (pct(m.top1_share), "of value in the top position"),
                (pct(m.top3_share), "of value in the top three"),
            ]
        )
    )
    o.append(summary_block(content, with_extremes=False))

    # ---- graphics: keep the heading with the first chart box
    o.append(r"\Needspace{0.38\textheight}\dsec{Portfolio at a glance}")
    groups = []
    for yr, g in m.by_year.items():
        locked_cost = g.net_at_cost - g.net_marked
        groups.append(
            (
                str(yr),
                [
                    [(g.invested, "dggray!70")],
                    [(g.net_marked, "dgaccent"), (locked_cost, "dgaccent!35")],
                ],
            )
        )
    o.append(
        r"\begin{panel}{Invested vs value by vintage year}\centering"
        + grouped_columns(
            groups,
            [
                ("invested", "dggray!70"),
                ("net value (marked)", "dgaccent"),
                ("locked, at cost", "dgaccent!35"),
            ],
        )
        + r"\end{panel}"
    )
    mrows = []
    for b in MULTIPLE_BUCKETS:
        g = m.by_bucket_multiple[b]
        if b == "locked" and not g.n:
            continue
        colour = {"0x": "dgred", "0-1x": "dgamber", "locked": "dggray"}.get(b, "dgaccent")
        mrows.append((f"{b} · {g.n}", float(g.invested), colour))
    trows = []
    for b in bucket_order(cfg, set(m.by_thesis)):
        g = m.by_thesis[b]
        trows.append((cfg.bucket_label(b), g.tvpi, bucket_colours(cfg, [b])[b]))
    o.append(r"\begin{tcbraster}[raster columns=2,raster column skip=10pt,raster equal height]")
    o.append(
        r"\begin{panel}{Multiple distribution (count, capital)}\centering"
        + hbar_chart(mrows, 3.8, max([r[1] for r in mrows] + [1.0]) * 1.2, money)
        + r"\par\vspace{2pt}{\tiny\color{dggray}Bars: capital invested per multiple bucket. "
        r"Label: bucket and number of positions.}\end{panel}"
    )
    o.append(
        r"\begin{panel}{TVPI by thesis bucket (locked at cost)}\centering"
        + hbar_chart(
            trows,
            3.6,
            max([r[1] or 0.0 for r in trows] + [1.0]) * 1.25,
            multiple,
            refs=[(1.0, "1.0x", "dggray")],
        )
        + r"\end{panel}"
    )
    o.append(r"\end{tcbraster}")

    # ---- top positions
    o.append(r"\Needspace{0.3\textheight}\dsec{Top positions by net value}")
    o.append(
        _table(
            ["Company", "Year", "Lead", "Invested", "Net value", "Multiple"],
            "X l l r r r",
            [
                [
                    tex(p.name),
                    str(p.year),
                    tex(p.lead),
                    money(p.invested),
                    money(p.net),
                    multiple(p.multiple),
                ]
                for p in m.top_positions
            ],
        )
    )

    # ---- per lead / per bucket
    o.append(r"\Needspace{0.3\textheight}\dsec{By syndicate lead}")
    lead_rows = sorted(m.by_lead.items(), key=lambda kv: -kv[1].invested)
    o.append(
        _table(
            ["Lead", "Positions", "Invested", "Net (locked at cost)", "TVPI", "TVPI marked"],
            "X r r r r r",
            [
                [
                    tex(name),
                    f"{g.n} ({g.n - g.n_marked} locked)" if g.n - g.n_marked else str(g.n),
                    money(g.invested),
                    money(g.net_at_cost),
                    multiple(g.tvpi),
                    multiple(g.tvpi_marked),
                ]
                for name, g in lead_rows
            ],
        )
    )
    o.append(r"\dsub{By thesis bucket}")
    o.append(
        _table(
            ["Bucket", "Positions", "Invested", "Net (locked at cost)", "TVPI", "TVPI marked"],
            "X r r r r r",
            [
                [
                    tex(cfg.bucket_label(b)),
                    str(m.by_thesis[b].n),
                    money(m.by_thesis[b].invested),
                    money(m.by_thesis[b].net_at_cost),
                    multiple(m.by_thesis[b].tvpi),
                    multiple(m.by_thesis[b].tvpi_marked),
                ]
                for b in bucket_order(cfg, set(m.by_thesis))
            ],
        )
    )

    # ---- gate retro, aggregated
    o.append(r"\Needspace{0.3\textheight}\dsec{Would the gate have helped?}")
    o.append(
        r"{\small "
        + tex(
            f"Every {band_s} position scored against {the(label)} on the facts in the AngelList "
            "record, then grouped by verdict. " + gate_verdict_sentence(m)
        )
        + r"}\par\vspace{2pt}"
    )
    o.append(
        _table(
            [
                "Verdict",
                "Positions",
                "Marked",
                "Invested",
                "Net (locked at cost)",
                "TVPI",
                "TVPI marked",
            ],
            "X r r r r r r",
            [
                [
                    rf"\pill{{{VERDICT_COLOR[v]}}}{{{v}}}",
                    str(g.n),
                    str(g.n_marked),
                    money(g.invested),
                    money(g.net_at_cost),
                    multiple(g.tvpi),
                    multiple(g.tvpi_marked),
                ]
                for v, g in m.by_verdict.items()
            ],
        )
    )
    fail_counts = dict.fromkeys(("stage", "sector", "cap", "size"), 0)
    for g in gate:
        for c in g.fails:
            fail_counts[c] += 1
    o.append(
        r"{\tiny\color{dggray}"
        + tex(
            "Hard-check failures (a position can fail several): "
            + ", ".join(f"{c} {n}" for c, n in fail_counts.items())
            + ". An unknown cap counts as a fail."
        )
        + "}"
    )

    # ---- holding cards
    holdings: dict[str, dict[str, Any]] = content.get("holdings", {})
    if holdings:
        o.append(r"\newpage\dsec{Holdings to watch}")
    for name, entry in holdings.items():
        ps = _match_positions(name, positions)
        if ps:
            inv = sum(p.invested for p in ps)
            net = sum(p.net_at_cost for p in ps)
            locked = any(p.net is None for p in ps)
            years = sorted({p.year for p in ps})
            leads = sorted({p.lead for p in ps if p.lead})
            gs = [gate[positions.index(p)] for p in ps]
            worst = max(gs, key=lambda g: ("Pass", "Borderline", "Fail").index(g.verdict))
            facts = [
                ("Invested", f"{money(inv)} · {', '.join(str(y) for y in years)}"),
                ("Net value", money(net) + (" (incl. locked at cost)" if locked else "")),
                ("Multiple", multiple(net / inv) if inv else "--"),
                ("Lead", tex(", ".join(leads))),
                ("Bucket", tex(cfg.bucket_label(worst.bucket))),
                ("Positions", str(len(ps))),
            ]
            pills = [
                (
                    STATUS_COLOR.get(entry.get("status", ""), "dggray"),
                    entry.get("status", "No signal"),
                ),
                (VERDICT_COLOR[worst.verdict], f"Gate: {worst.verdict}"),
            ]
            fallback = ps[0].market
        else:
            facts = [("Record", "not in this band's export")]
            pills = [
                (
                    STATUS_COLOR.get(entry.get("status", ""), "dggray"),
                    entry.get("status", "No signal"),
                )
            ]
            fallback = ""
        o.append(card(name, entry, facts, pills, fallback, show_prob=False, watch_label="Watch"))

    o.append(actions_block(content))
    o.append(
        method_block(
            brand,
            meta.as_of,
            "TVPI locked at cost carries locked positions at their cost; TVPI marked only "
            "ignores them. DPI is realized value over all capital invested. ",
        )
    )
    o.append(r"\end{document}")
    return "\n".join(x for x in o if x)
