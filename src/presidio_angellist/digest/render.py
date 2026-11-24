"""
Build the LaTeX source for a vintage or aggregate digest.

Rule for this module: a value that came from the CSV, the content JSON, the gate
config or the brand config reaches the output only through :func:`tex`,
:func:`tex_url`, or one of the numeric formatters in :mod:`latex` (which emit
digits and fixed markup only). Literal LaTeX in this file is the only markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from presidio_angellist.digest.estimates import (
    Estimates,
    est_net,
    has_estimate,
    value_incl_estimates,
)
from presidio_angellist.digest.gate import GateConfig, GateResult, gate_retro
from presidio_angellist.digest.latex import (
    grouped_columns,
    hbar_chart,
    money,
    multiple,
    paired_hbar,
    pct,
    short_name,
    stacked_bar,
    stacked_rows,
    tex,
    tex_url,
)
from presidio_angellist.digest.metrics import (
    MULTIPLE_BUCKETS,
    AggregateMetrics,
    Group,
    aggregate,
    gate_verdict_sentence,
)

if TYPE_CHECKING:
    from presidio_angellist.digest.config import Brand
    from presidio_angellist.digest.csvload import Position
    from presidio_angellist.digest.market import Market

CONFIDENCE_COLOR = {"high": "dgaccent", "medium": "dgblue", "low": "dgamber"}
EST_DISCLAIMER = (
    "These are advisor estimates from public information, not marks. Net value deducts "
    "carry on the gain above cost (the export's carry, 20% where empty). Locked positions "
    "without an estimate are carried at cost and flagged."
)

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
            r"booktabs,multicol,needspace,xltabular}",
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
            r"\Needspace{0.55\textheight}\dsec{Actions and lessons}",
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


GLOSSARY_MARKER = "%% digest-glossary %%"

# Venture terms the digests use. Only terms that actually occur in a document are listed
# in its glossary; company names, sectors and labels are never glossary entries.
GLOSSARY: tuple[tuple[str, str, str], ...] = (
    (
        "TVPI",
        r"\bTVPI\b",
        "Total value to paid-in: (cash returned + remaining value) / capital "
        "invested. Shown marked-only, with locked positions at cost, and with locked estimates.",
    ),
    ("DPI", r"\bDPI\b", "Distributions to paid-in: cash actually returned / capital invested."),
    ("LP", r"\bLPs?\b", "Limited partner: an investor in a fund or SPV who does not manage it."),
    ("GP", r"\bGPs?\b", "General partner: the manager of a fund or syndicate."),
    (
        "SPV",
        r"\bSPVs?\b",
        "Special purpose vehicle: a single-deal fund through which a syndicate invests.",
    ),
    (
        "SAFE",
        r"\bSAFEs?\b",
        "Simple agreement for future equity: converts into shares at the "
        "next priced round, at the cap or discount.",
    ),
    (
        "Cap",
        r"\b[Cc]aps?\b",
        "Valuation cap: the maximum valuation at which a SAFE or note converts.",
    ),
    (
        "Pre-money / post-money",
        r"\b(?:[Pp]re|[Pp]ost)(?:-money)?\b",
        "Company valuation before / after the new money of a round. "
        "A pre-money cap is compared as cap + round size.",
    ),
    (
        "Carry",
        r"\b[Cc]arry\b",
        "Carried interest: the lead's share of the gain (typically 20%), "
        "deducted from net values.",
    ),
    ("Mark", r"\b[Mm]ark(?:ed|s)?\b", "The value the platform currently assigns to a position."),
    (
        "Locked",
        r"\b[Ll]ocked\b",
        "A position the platform has not yet marked; shown at cost unless an estimate is given.",
    ),
    ("0x", r"\b0x\b", "A position marked at zero (written off)."),
    (
        "P(up-round)",
        r"P\(up-round\)",
        "Advisor's judgement of the chance of a priced round "
        "above our entry cap within 12-24 months.",
    ),
    (
        "p25 / p75 (quartiles)",
        r"\bp(?:25|75)\b|[Qq]uartiles?",
        "The 25th and 75th percentiles of a benchmark: a quarter of funds sit below p25, "
        "a quarter above p75; the band between them is the middle half.",
    ),
    (
        "Median",
        r"\b[Mm]edian\b",
        "The middle value: half of the observations are above it, half below.",
    ),
    (
        "Vintage",
        r"\b[Vv]intages?\b",
        "The year an investment (or a fund) was made; returns are compared within a vintage.",
    ),
    (
        "Graduation rate",
        r"\b[Gg]raduation\b",
        "The share of companies at one stage that raise the next round (e.g. seed to "
        "Series A) within a given window.",
    ),
    (
        "Over-/under-weight",
        r"\b(?:[Oo]ver|[Uu]nder)-weight\b",
        "How much larger (or smaller) a portfolio's share of capital in a segment is than "
        "the market's share of dollars, in percentage points.",
    ),
    (
        "Pro-rata",
        r"\b[Pp]ro[- ]rata\b",
        "The right to invest in later rounds to keep the same ownership share.",
    ),
)


def _plain(doc: str) -> str:
    """Rough plain text of a LaTeX body, for deciding which glossary terms occur."""
    body = doc.split(r"\begin{document}", 1)[-1]
    body = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", body)
    return body.replace("{", " ").replace("}", " ")


def glossary_block(doc: str) -> str:
    text = _plain(doc.split(GLOSSARY_MARKER, 1)[0])
    picked: set[str] = set()
    while True:  # a definition may use another term (LP -> SPV): include that too
        new = {t for t, pat, _ in GLOSSARY if t not in picked and re.search(pat, text)}
        if not new:
            break
        picked |= new
        text += " " + " ".join(d for t, _, d in GLOSSARY if t in new)
    rows = [(t, d) for t, _, d in GLOSSARY if t in picked]
    if not rows:
        return ""
    items = "".join(r"\item[\textbf{" + tex(t) + r"}] " + tex(d) for t, d in rows)
    return (
        r"\Needspace{0.2\textheight}\dsec{Glossary}"
        + "\n"
        + r"{\scriptsize\color{dgnavy}\begin{description}[leftmargin=2.6cm,style=nextline,"
        + r"itemsep=1pt,topsep=2pt,parsep=0pt,font=\normalfont]"
        + items
        + r"\end{description}}\par"
    )


def with_glossary(doc: str) -> str:
    """Replace the glossary marker with the terms that occur in the document."""
    if GLOSSARY_MARKER not in doc:
        return doc
    return doc.replace(GLOSSARY_MARKER, glossary_block(doc), 1)


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
        GLOSSARY_MARKER
        + "\n"
        + r"\dsec{Method}"
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


def estimate_tile(g: Group, est: Estimates | None) -> list[tuple[str, str]]:
    """KPI tile for TVPI including locked estimates (net, with gross in the label)."""
    if est is None:
        return []
    return [
        (
            multiple(g.tvpi_est),
            f"TVPI incl. locked estimates, net ({multiple(g.tvpi_est_gross)} gross)",
        )
    ]


def estimates_note(est: Estimates) -> str:
    when = f" ({est.as_of})" if est.as_of else ""
    method = f"Method{when}: {est.method} " if est.method else ""
    return r"{\tiny\color{dggray}" + tex(method + EST_DISCLAIMER) + "}"


def locked_estimates_block(positions: list[Position], est: Estimates | None) -> str:
    """Table and chart of locked positions at their estimated value (empty if no file)."""
    locked = [p for p in positions if p.locked]
    if est is None or not locked:
        return ""
    locked.sort(key=lambda p: (-value_incl_estimates(p, est), p.name))
    rows = []
    for p in locked:
        e = est.for_position(p)
        if e is None:
            rows.append(
                [
                    tex(p.name),
                    str(p.year),
                    money(p.invested),
                    "--",
                    r"\textit{no estimate: carried at cost}",
                    "--",
                    "--",
                    "--",
                    money(p.invested) + r"\,$^{\dagger}$",
                ]
            )
            continue
        rows.append(
            [
                tex(p.name),
                str(p.year),
                money(p.invested),
                tex(e.evidence.replace("_", " ")),
                tex(e.event),
                multiple(e.est_multiple),
                f"{multiple(e.low)}--{multiple(e.high)}",
                rf"\pill{{{CONFIDENCE_COLOR[e.confidence]}}}{{{e.confidence}}}",
                money(est_net(p, e)),
            ]
        )
    chart_rows = [
        (
            short_name(p.name),
            p.invested,
            value_incl_estimates(p, est),
            CONFIDENCE_COLOR[e.confidence] if (e := est.for_position(p)) else "dggray",
        )
        for p in locked[:12]
    ]
    n_missing = sum(1 for p in locked if not has_estimate(p, est))
    return "\n".join(
        [
            r"\Needspace{0.25\textheight}\dsec{Locked positions: estimated value}",
            _table(
                [
                    "Company",
                    "Year",
                    "Invested",
                    "Evidence",
                    "Event",
                    "Est. multiple",
                    "Range",
                    "Confidence",
                    "Est. net value",
                ],
                "l r r l >{\\raggedright\\arraybackslash}X r r c r",
                rows,
            ),
            (
                r"{\tiny\color{dggray}$^{\dagger}$ "
                + tex(f"{n_missing} locked position(s) without an estimate, at cost.")
                + "}\\par"
                if n_missing
                else ""
            ),
            r"\begin{panel}{Locked positions: cost (grey) against estimated net value}\centering"
            + paired_hbar(chart_rows, 9.5)
            + r"\par\vspace{2pt}{\tiny\color{dggray}Colour = confidence: green high, blue "
            r"medium, amber low; grey = no estimate (cost).}\end{panel}",
            estimates_note(est),
        ]
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
    estimates: Estimates | None = None,
) -> str:
    gate = gate_retro(positions, cfg)
    totals = Group()
    for p in positions:
        totals.add(p, estimates)
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
    tiles += estimate_tile(totals, estimates)
    o.append(kpi_row(tiles, columns=4 if len(tiles) > 6 else None))
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
    o.append(locked_estimates_block(positions, estimates))

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
        if estimates is not None and p.locked:
            e = estimates.for_position(p)
            facts.append(
                (
                    "Est. locked value",
                    f"{money(est_net(p, e))} · {multiple(e.est_multiple)}, {tex(e.confidence)}"
                    if e
                    else r"none: at cost\,$^{\dagger}$",
                )
            )
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
    return with_glossary("\n".join(x for x in o if x))


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
    """``header`` is raw text; ``rows`` cells must already be escaped/fixed markup.

    Breakable across pages (xltabular), with the header repeated on each page, so a
    long table no longer strands its section heading at the foot of a page.
    """
    head = " & ".join(rf"\textbf{{{tex(h)}}}" for h in header) + r"\\\midrule"
    return "\n".join(
        [
            r"{\scriptsize\renewcommand{\arraystretch}{1.2}\setlength{\LTpre}{2pt}"
            r"\setlength{\LTpost}{2pt}"
            rf"\begin{{xltabular}}{{\textwidth}}{{@{{}}{aligns}@{{}}}}\toprule",
            head + r"\endfirsthead",
            r"\toprule " + head + r"\endhead",
            r"\bottomrule\endlastfoot",
        ]
        + [" & ".join(r) + r"\\" for r in rows]
        + [r"\end{xltabular}}\par"]
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
    estimates: Estimates | None = None,
) -> str:
    gate = gate_retro(positions, cfg)
    m: AggregateMetrics = aggregate(positions, gate, estimates=estimates)
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
                *estimate_tile(t, estimates),
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

    o.append(locked_estimates_block(positions, estimates))

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
    return with_glossary("\n".join(x for x in o if x))


# ---------------------------------------------------------------------------
# Portfolio digest (every requested segment compared, plus a total)
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """One requested vintage ("2026") or band ("2015-2020") and its positions."""

    label: str
    positions: list[Position]


def _union(segments: list[Segment]) -> list[Position]:
    seen: set[int] = set()
    out: list[Position] = []
    for seg in segments:
        for p in seg.positions:
            if id(p) not in seen:
                seen.add(id(p))
                out.append(p)
    return sorted(out, key=lambda p: (p.invest_date, p.name))


def _verdict_counts(gate: list[GateResult]) -> str:
    c = {v: sum(1 for g in gate if g.verdict == v) for v in ("Pass", "Borderline", "Fail")}
    return f"{c['Pass']}/{c['Borderline']}/{c['Fail']}"


def build_portfolio_tex(
    segments: list[Segment],
    all_positions: list[Position],
    cfg: GateConfig,
    content: dict[str, Any],
    brand: Brand,
    meta: DocMeta,
    logo_ext: str | None = None,
    estimates: Estimates | None = None,
    market: Market | None = None,
) -> str:
    """Compare the run's segments side by side; ``all_positions`` feeds the J-curve.

    With ``market``, the J-curve chart also draws the market median TVPI per vintage.
    """
    est = estimates
    union = _union(segments)
    rows: list[tuple[str, list[Position], list[GateResult], AggregateMetrics]] = []
    for seg in segments:
        g = gate_retro(seg.positions, cfg)
        rows.append((seg.label, seg.positions, g, aggregate(seg.positions, g, estimates=est)))
    ugate = gate_retro(union, cfg)
    um = aggregate(union, ugate, estimates=est)
    rows_t = [*rows, ("Total", union, ugate, um)]
    verdicts: dict[str, str] = content.get("segments", {})
    seg_of: dict[int, str] = {}
    for seg in segments:
        for p in seg.positions:
            seg_of[id(p)] = seg_of[id(p)] + ", " + seg.label if id(p) in seg_of else seg.label
    label = content.get("gate_label") or cfg.label
    t = um.total
    labels = ", ".join(s.label for s in segments)

    o = [preamble(brand, meta, logo_ext)]
    o.append(
        title_block(
            f"{brand.header_text} · {meta.quarter} · as of {meta.as_of}",
            f"Portfolio Digest {meta.quarter}",
            f"AngelList syndicate positions compared across {labels}, checked against the "
            f"{brand.name} thesis and {the(label)}.",
            content.get("headline", ""),
        )
    )
    tiles = [
        (str(t.n), f"positions ({um.locked} locked)"),
        (money(t.invested), "invested"),
        (money(t.realized), "realized"),
        (multiple(t.tvpi_marked), "TVPI, marked only"),
        (multiple(t.tvpi), "TVPI, locked at cost"),
        *estimate_tile(t, est),
        (multiple(um.dpi), "DPI, all capital invested"),
        (pct(um.zero_share), "of marked positions at 0x"),
    ]
    o.append(kpi_row(tiles, columns=4))
    o.append(summary_block(content, with_extremes=False))

    # ---- comparison table
    o.append(r"\Needspace{0.3\textheight}\dsec{Segments compared}")
    head = ["Segment", "Positions", "Invested", "Realized", "Unreal.", "TVPI marked",
            "TVPI at cost"]  # fmt: skip
    if est is not None:
        head.append("TVPI incl. est. (net)")
    head += ["DPI", "0x", "Top-1", "Gate P/B/F", "Verdict"]
    trows = []
    for i, (lab, _ps, g, m) in enumerate(rows_t):
        gt = m.total
        cells = [
            (r"\textbf{" + tex(lab) + "}") if lab == "Total" else tex(lab),
            f"{gt.n} ({m.locked})",
            money(gt.invested),
            money(gt.realized),
            money(m.unrealized),
            multiple(gt.tvpi_marked),
            multiple(gt.tvpi),
        ]
        if est is not None:
            cells.append(multiple(gt.tvpi_est))
        cells += [
            multiple(m.dpi),
            pct(m.zero_share),
            pct(m.top1_share),
            _verdict_counts(g),
            tex(verdicts.get(lab, "")),
        ]
        if i == len(rows_t) - 1:
            cells[0] = r"\midrule " + cells[0]
        trows.append(cells)
    aligns = "l " + "r " * (len(head) - 2) + ">{\\raggedright\\arraybackslash}X"
    o.append(
        r"{\tiny\setlength{\tabcolsep}{3pt}"
        + _table(head, aligns, trows).replace(r"{\scriptsize", "{", 1)
        + "}"
    )
    o.append(
        r"{\tiny\color{dggray}"
        + tex(
            "Positions: total (locked). Unreal.: unrealized value of marked positions. "
            "Top-1: share of the segment's value (locked at cost) in its largest position. "
            "Total: every position in the segments above, counted once."
        )
        + "}"
    )

    # ---- charts
    o.append(r"\Needspace{0.35\textheight}\dsec{Portfolio at a glance}")
    legend = [("TVPI marked", "dggray!70"), ("TVPI at cost", "dgblue")]
    if est is not None:
        legend.append(("TVPI incl. estimates", "dgaccent"))
    groups = []
    for lab, _ps, _g, m in rows_t:
        cols = [[(m.total.tvpi_marked or 0.0, "dggray!70")], [(m.total.tvpi or 0.0, "dgblue")]]
        if est is not None:
            cols.append([(m.total.tvpi_est or 0.0, "dgaccent")])
        groups.append((lab, cols))
    o.append(
        r"\begin{panel}{TVPI by segment}\centering"
        + grouped_columns(groups, legend, height_cm=3.4, fmt=multiple)
        + r"\end{panel}"
    )
    buckets = bucket_order(cfg, {g.bucket for _, _, gs, _ in rows_t for g in gs})
    bcol = bucket_colours(cfg, buckets)
    brows = []
    for lab, ps, gs, _m in rows_t:
        inv: dict[str, float] = {}
        for p, g in zip(ps, gs, strict=True):
            inv[g.bucket] = inv.get(g.bucket, 0.0) + p.invested
        tot = sum(inv.values()) or 1.0
        brows.append(
            (
                lab,
                [
                    (inv.get(b, 0.0), bcol[b], f"{inv.get(b, 0.0) / tot * 100:.0f}%")
                    for b in buckets
                ],
            )  # fmt: skip
        )
    o.append(
        r"\begin{panel}{Capital by thesis bucket, per segment (100\%)}\centering"
        + stacked_rows(brows, [(cfg.bucket_label(b), bcol[b]) for b in buckets], 12.5)
        + r"\end{panel}"
    )
    years: dict[int, Group] = {}
    for p in all_positions:
        years.setdefault(p.year, Group()).add(p, est)
    ygroups = []
    for yr, g in sorted(years.items()):
        cols = [[(g.tvpi or 0.0, "dgblue")]]
        if est is not None:
            cols.append([(g.tvpi_est or 0.0, "dgaccent")])
        ygroups.append((str(yr), cols))
    ylegend = [("TVPI at cost", "dgblue")] + (
        [("TVPI incl. estimates", "dgaccent")] if est is not None else []
    )
    yline = None
    ynote = ""
    if market is not None:
        yrs = sorted(years)
        yline = [market.vintages[y].median if y in market.vintages else None for y in yrs]
        if any(v is not None for v in yline):
            ylegend.append(("market median", "dgamber"))
            ynote = (
                " Market median TVPI: "
                + market.cite(market.vintages[y].source for y in yrs if y in market.vintages)
                + "."
            )
        else:
            yline = None
    o.append(r"\begin{tcbraster}[raster columns=2,raster column skip=10pt,raster equal height]")
    o.append(
        r"\begin{panel}{TVPI by vintage year (J-curve view)}\centering"
        + grouped_columns(ygroups, ylegend, height_cm=3.0, width_cm=7.6, fmt=multiple, line=yline)
        + r"\par\vspace{2pt}{\tiny\color{dggray}"
        + tex("All positions in the export, by invest year." + ynote)
        + r"}\end{panel}"
    )
    drows = [(lab, m.dpi, "dgnavy" if lab == "Total" else "dgblue") for lab, _, _, m in rows_t]
    o.append(
        r"\begin{panel}{DPI by segment}\centering"
        + hbar_chart(
            drows,
            4.2,
            max([d[1] or 0.0 for d in drows] + [1.0]) * 1.2,
            multiple,
            refs=[(1.0, "1.0x", "dggray")],
        )  # fmt: skip
        + r"\end{panel}"
    )
    o.append(r"\end{tcbraster}")

    # ---- gate per segment
    o.append(r"\Needspace{0.3\textheight}\dsec{Gate retro-check by segment}")
    grows = []
    for lab, _ps, _gs, m in rows_t:
        parts = []
        for v in ("Pass", "Borderline", "Fail"):
            gv = m.by_verdict[v]
            parts.append((float(gv.n), VERDICT_COLOR[v], f"{gv.n} · {multiple(gv.tvpi)}"))
        grows.append((lab, parts))
    o.append(
        r"\begin{panel}{Positions by gate verdict, with the TVPI (at cost) of each group}"
        r"\centering"
        + stacked_rows(
            grows, [(v, VERDICT_COLOR[v]) for v in ("Pass", "Borderline", "Fail")], 12.5
        )
        + r"\par\vspace{2pt}{\tiny\color{dggray}"
        + tex(gate_verdict_sentence(um))
        + r"}\end{panel}"
    )

    # ---- top value drivers
    o.append(r"\Needspace{0.3\textheight}\dsec{Top value drivers across the portfolio}")
    drivers = sorted(union, key=lambda p: -value_incl_estimates(p, est))[:10]
    o.append(
        _table(
            ["Company", "Segment", "Year", "Invested", "Value", "Multiple", "Basis"],
            "X l r r r r l",
            [
                [
                    tex(p.name),
                    tex(seg_of.get(id(p), "")),
                    str(p.year),
                    money(p.invested),
                    money(value_incl_estimates(p, est)),
                    multiple(value_incl_estimates(p, est) / p.invested if p.invested else None),
                    "mark"
                    if p.net is not None
                    else ("estimate" if has_estimate(p, est) else "cost"),
                ]
                for p in drivers
            ],
        )
    )
    o.append(
        r"{\tiny\color{dggray}"
        + tex(
            "Value: net value incl. realized; locked positions at their estimated net value "
            "where an estimate exists, else at cost."
        )  # fmt: skip
        + "}"
    )

    # ---- biggest locked estimates
    if est is not None:
        locked = [p for p in union if has_estimate(p, est)]
        locked.sort(key=lambda p: -value_incl_estimates(p, est))
        if locked:
            o.append(r"\Needspace{0.25\textheight}\dsec{Biggest locked estimates}")
            trow = []
            for p in locked[:8]:
                e = est.for_position(p)
                trow.append(
                    [
                        tex(p.name),
                        tex(seg_of.get(id(p), "")),
                        money(p.invested),
                        tex(e.evidence.replace("_", " ")),
                        tex(e.event),
                        multiple(e.est_multiple),
                        rf"\pill{{{CONFIDENCE_COLOR[e.confidence]}}}{{{e.confidence}}}",
                        money(est_net(p, e)),
                    ]
                )
            o.append(
                _table(
                    [
                        "Company",
                        "Segment",
                        "Invested",
                        "Evidence",
                        "Event",
                        "Est. multiple",
                        "Confidence",
                        "Est. net value",
                    ],  # fmt: skip
                    "l l r l >{\\raggedright\\arraybackslash}X r c r",
                    trow,
                )
            )
            o.append(estimates_note(est))

    o.append(actions_block(content))
    o.append(
        method_block(
            brand,
            meta.as_of,
            "Segments are the vintages and bands requested in this run, labelled as requested; "
            "the total counts each position once. TVPI locked at cost carries locked positions "
            "at cost; TVPI marked only ignores them; TVPI incl. estimates uses the advisor "
            "estimates for locked positions where given. DPI is realized value over all capital "
            "invested. ",
        )
    )
    o.append(r"\end{document}")
    return with_glossary("\n".join(x for x in o if x))
