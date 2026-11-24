"""
LaTeX escaping and hand-drawn TikZ chart helpers for the digest.

**Every string that did not originate in this module is untrusted** -- company
names and leads from the CSV, editorial text from content JSON (which an LLM may
have drafted), and brand text. All of it goes through :func:`tex` (or
:func:`tex_url` for link targets) before it reaches the document. :func:`tex`
neutralises every character with a special meaning to TeX, including the ones
that start a control sequence (``\\``), open or close a group, switch to math
mode, start a comment, or begin an optional argument (``[``/``]``), and it drops
control characters. Nothing from outside is ever interpolated raw.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_TEX_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "[": r"{[}",
    "]": r"{]}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "|": r"\textbar{}",
    '"': r"\textquotedbl{}",
    " ": "~",
}

# Characters allowed verbatim inside a URL target; everything else is percent-encoded.
_URL_SAFE = "/:?=&.-_@!+,;#"
_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


def _is_pictograph(ch: str) -> bool:
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0xFE00 <= o <= 0xFE0F or o == 0x200D


def tex(value: object) -> str:
    """Escape arbitrary text for safe inclusion in a LaTeX document body."""
    s = "" if value is None else str(value)
    # Emoji and pictographs have no glyph in the body font; drop them and the gap they leave.
    s = re.sub(r"\s+", " ", "".join(c for c in s if not _is_pictograph(c)))
    out: list[str] = []
    for ch in s:
        if ch in _TEX_MAP:
            out.append(_TEX_MAP[ch])
        elif ch in "\r\n\t\f\v":
            out.append(" ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue
        else:
            out.append(ch)
    return "".join(out).replace("—", "--").replace("–", "--")


def safe_url(url: object) -> str | None:
    """Return a normalised http(s) URL, or ``None`` for any other scheme or junk."""
    s = str(url or "").strip()
    if not s or any(unicodedata.category(c) == "Cc" for c in s):
        return None
    try:
        parts = urlsplit(s)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return s


def _tick(v: float) -> str:
    """Short axis label: 0.04, 0.5, 1, 2.5, 12."""
    if v >= 10:
        return f"{v:.0f}"
    s = f"{v:.2f}" if v < 1 else f"{v:.1f}"
    return s.rstrip("0").rstrip(".")


def tex_url(url: object) -> str | None:
    """Escape a URL for the first argument of ``\\href``; ``None`` if not http(s).

    The URL is percent-encoded down to a small safe set (so no brace, backslash,
    tilde, caret, space or non-ASCII byte survives), then the three characters
    hyperref still treats specially (``%``, ``#``, ``&``) are backslash-escaped.
    """
    s = safe_url(url)
    if s is None:
        return None
    # Decode nothing: encode every byte outside the safe set, including an existing '%'.
    enc = quote(s, safe=_URL_SAFE).replace("~", "%7E")
    return enc.replace("%", r"\%").replace("#", r"\#").replace("&", r"\&")


def hex_color(value: object, default: str) -> str:
    """Validate a 6-digit hex colour (``#`` optional); fall back to ``default``."""
    s = str(value or "").strip().lstrip("#")
    return s.upper() if _HEX_RE.match(s) else default


def money(v: float | None) -> str:
    """Compact, already-escaped money string: ``\\$68.9k``, ``\\$1.2M``."""
    if v is None:
        return "--"
    if v == 0:
        return "\\$0"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e6:
        return (f"{sign}\\${v / 1e6:,.1f}M").replace(".0M", "M")
    return (f"{sign}\\${v / 1e3:,.1f}k").replace(".0k", "k")


def multiple(v: float | None) -> str:
    return "--" if v is None else f"{v:.2f}x"


def pct(v: float | None) -> str:
    return "--" if v is None else f"{v * 100:.0f}\\%"


def short_name(name: str) -> str:
    """Drop accelerator batch suffixes such as ``(YC W24)`` from a company name."""
    return re.sub(r"\s*\((?:YC|yc)\s+[A-Za-z]\d+\)", "", name)


# ---------------------------------------------------------------------------
# Charts (hand-drawn TikZ; inputs are numbers and already-escaped labels)
# ---------------------------------------------------------------------------


def hbar_chart(
    rows: Sequence[tuple[str, float | None, str]],
    width_cm: float,
    vmax: float,
    fmt: Callable[[float], str],
    *,
    refs: Sequence[tuple[float, str, str]] = (),
    log: bool = False,
    vmin: float = 1.0,
    bar_h: float = 0.36,
    gap: float = 0.14,
) -> str:
    """Horizontal bars. ``rows`` = (raw label, value, colour); labels are escaped here."""
    vmax = max(vmax, vmin * 10 if log else 1e-9)

    def xpos(v: float | None) -> float:
        if v is None or v <= 0:
            return 0.0
        if log:
            v = max(v, vmin)
            span = math.log10(vmax) - math.log10(vmin)
            return min((math.log10(v) - math.log10(vmin)) / span, 1.0) * width_cm
        return min(v / vmax, 1.0) * width_cm

    h = max(len(rows), 1) * (bar_h + gap)
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    for i, (lab, v, col) in enumerate(rows):
        y = h - (i + 1) * (bar_h + gap) + gap / 2
        mid = y + bar_h / 2
        o.append(rf"\node[anchor=east,text=dgnavy] at (0,{mid:.3f}) {{{tex(lab)}}};")
        if v is None:
            o.append(rf"\node[anchor=west,text=dggray] at (0.05,{mid:.3f}) {{n/a}};")
            continue
        x = xpos(v)
        o.append(rf"\fill[{col}] (0,{y:.3f}) rectangle ({max(x, 0.04):.3f},{y + bar_h:.3f});")
        o.append(rf"\node[anchor=west,text=dgnavy] at ({x + 0.05:.3f},{mid:.3f}) {{{fmt(v)}}};")
    o.append(rf"\draw[dggray!60] (0,0) -- (0,{h:.3f});")
    for j, (v, lab, col) in enumerate(refs):
        x = xpos(v)
        o.append(rf"\draw[{col},thick,dashed] ({x:.3f},-0.1) -- ({x:.3f},{h + 0.05:.3f});")
        anchor, yy = ("south", h + 0.05) if j == len(refs) - 1 else ("north", -0.1)
        o.append(
            rf"\node[anchor={anchor},text={col},font=\tiny\bfseries] at ({x:.3f},{yy:.3f}) "
            rf"{{{tex(lab)}}};"
        )
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)


def stacked_bar(parts: Sequence[tuple[str, float, str]], width_cm: float = 16.5) -> str:
    """One horizontal 100% bar with a legend underneath. Labels are escaped here."""
    h = 0.55
    tot = sum(v for _, v, _ in parts) or 1.0
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    x = 0.0
    for _lab, v, col in parts:
        w = v / tot * width_cm
        o.append(rf"\fill[{col}] ({x:.3f},0) rectangle ({x + w:.3f},{h});")
        if w > 1.0:
            o.append(
                rf"\node[text=white,font=\scriptsize\bfseries] at ({x + w / 2:.3f},{h / 2}) "
                rf"{{{v / tot * 100:.0f}\%}};"
            )
        x += w
    lx, ly = 0.0, -0.45
    for lab, v, col in parts:
        o.append(
            rf"\fill[{col}] ({lx:.2f},{ly - 0.1:.2f}) rectangle ({lx + 0.25:.2f},{ly + 0.1:.2f});"
        )
        o.append(
            rf"\node[anchor=west,text=dgnavy] at ({lx + 0.3:.2f},{ly:.2f}) "
            rf"{{{tex(lab)} ({money(v)})}};"
        )
        lx += 0.65 + 0.135 * (len(lab) + 9)
        if lx > width_cm - 3:
            lx, ly = 0.0, ly - 0.4
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)


def grouped_columns(
    groups: Sequence[tuple[str, Sequence[Sequence[tuple[float, str]]]]],
    legend: Sequence[tuple[str, str]],
    *,
    height_cm: float = 4.0,
    width_cm: float = 16.0,
    fmt: Callable[[float], str] = money,
    band: Sequence[tuple[float, float] | None] | None = None,
    line: Sequence[float | None] | None = None,
    vmax_cap: float | None = None,
) -> str:
    """Grouped vertical columns.

    ``groups`` = (raw label, [column, ...]) where each column is a stack of
    (value, colour) segments drawn bottom-up. The column total is printed on top.
    Optional per-group ``band`` (low, high) is shaded behind the columns and ``line``
    values are joined as a dashed reference line (e.g. a market p25-p75 band and median).
    ``vmax_cap`` limits the axis; a taller column is cut at the top (marked with a
    break) and still labelled with its true value.
    """
    totals = [sum(max(v, 0.0) for v, _ in col) for _, cols in groups for col in cols]
    extra = [hi for b in band or () if b for hi in b[1:]] + [v for v in line or () if v]
    vmax = max(totals + extra, default=0.0) or 1.0
    if vmax_cap is not None and 0 < vmax_cap < vmax:
        vmax = vmax_cap
    slot = width_cm / max(len(groups), 1)
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    o.append(rf"\draw[dggray!60] (0,0) -- ({width_cm:.2f},0);")
    for gi, b in enumerate(band or ()):
        if b and gi < len(groups):
            lo, hi = (max(v, 0.0) / vmax * height_cm for v in b)
            o.append(
                rf"\fill[dgamber!18] ({gi * slot + 0.08:.3f},{lo:.3f}) rectangle "
                rf"({(gi + 1) * slot - 0.08:.3f},{hi:.3f});"
            )
    for gi, (lab, cols) in enumerate(groups):
        bw = min(0.6, slot * 0.8 / max(len(cols), 1))
        x0 = gi * slot + (slot - bw * len(cols)) / 2
        for ci, col in enumerate(cols):
            x = x0 + ci * bw
            base = 0.0
            for v, colour in col:
                v = max(v, 0.0)
                y0 = min(base / vmax, 1.0) * height_cm
                y1 = min((base + v) / vmax, 1.0) * height_cm
                if y1 - y0 > 0.005:
                    o.append(
                        rf"\fill[{colour}] ({x:.3f},{y0:.3f}) rectangle "
                        rf"({x + bw * 0.9:.3f},{y1:.3f});"
                    )
                base += v
            if base > vmax:
                yb = height_cm - 0.12
                o.append(
                    rf"\fill[white] ({x - 0.02:.3f},{yb:.3f}) -- ({x + bw * 0.92:.3f},"
                    rf"{yb + 0.06:.3f}) -- ({x + bw * 0.92:.3f},{yb + 0.1:.3f}) -- "
                    rf"({x - 0.02:.3f},{yb + 0.04:.3f}) -- cycle;"
                )
            o.append(
                rf"\node[anchor=south,text=dgnavy,font=\tiny] at ({x + bw * 0.45:.3f},"
                rf"{min(base / vmax, 1.0) * height_cm:.3f}) {{{fmt(base)}}};"
            )
        o.append(
            rf"\node[anchor=north,text=dgnavy] at ({gi * slot + slot / 2:.3f},-0.05) "
            rf"{{{tex(lab)}}};"
        )
    pts = [
        (gi * slot + slot / 2, v / vmax * height_cm)
        for gi, v in enumerate(line or ())
        if v is not None and gi < len(groups)
    ]
    if pts:
        path = " -- ".join(f"({x:.3f},{y:.3f})" for x, y in pts)
        o.append(rf"\draw[dgamber,thick,dashed] {path};")
        o += [rf"\fill[dgamber] ({x:.3f},{y:.3f}) circle (1.6pt);" for x, y in pts]
    lx = 0.0
    for lab, colour in legend:
        o.append(rf"\fill[{colour}] ({lx:.2f},-0.75) rectangle ({lx + 0.25:.2f},-0.55);")
        o.append(rf"\node[anchor=west,text=dgnavy] at ({lx + 0.3:.2f},-0.65) {{{tex(lab)}}};")
        lx += 0.7 + 0.14 * len(lab)
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)


def paired_hbar(
    rows: Sequence[tuple[str, float, float, str]],
    width_cm: float,
    *,
    fmt: Callable[[float], str] = money,
    bar_h: float = 0.17,
    gap: float = 0.16,
) -> str:
    """Two thin bars per row: cost (grey) above value (``colour``). Labels escaped here."""
    vmax = max([max(a, b) for _, a, b, _ in rows] + [1e-9])
    row_h = 2 * bar_h + gap
    h = max(len(rows), 1) * row_h
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    for i, (lab, cost, value, col) in enumerate(rows):
        y = h - (i + 1) * row_h + gap / 2
        o.append(rf"\node[anchor=east,text=dgnavy] at (0,{y + bar_h:.3f}) {{{tex(lab)}}};")
        for j, (v, c) in enumerate(((cost, "dggray!70"), (value, col))):
            yy = y + bar_h * (1 - j)
            x = max(min(max(v, 0.0) / vmax, 1.0) * width_cm, 0.03)
            o.append(rf"\fill[{c}] (0,{yy:.3f}) rectangle ({x:.3f},{yy + bar_h * 0.9:.3f});")
            o.append(
                rf"\node[anchor=west,text=dgnavy,font=\tiny] at ({x + 0.04:.3f},"
                rf"{yy + bar_h * 0.45:.3f}) {{{fmt(v)}}};"
            )
    o.append(rf"\draw[dggray!60] (0,0) -- (0,{h:.3f});")
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)


def stacked_rows(
    rows: Sequence[tuple[str, Sequence[tuple[float, str, str]]]],
    legend: Sequence[tuple[str, str]],
    width_cm: float = 12.0,
    *,
    bar_h: float = 0.42,
    gap: float = 0.16,
) -> str:
    """One 100% bar per row. Segments are (value, colour, raw text shown inside)."""
    h = max(len(rows), 1) * (bar_h + gap)
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    for i, (lab, parts) in enumerate(rows):
        y = h - (i + 1) * (bar_h + gap) + gap / 2
        o.append(rf"\node[anchor=east,text=dgnavy] at (0,{y + bar_h / 2:.3f}) {{{tex(lab)}}};")
        tot = sum(max(v, 0.0) for v, _, _ in parts) or 1.0
        x = 0.0
        for v, col, text in parts:
            w = max(v, 0.0) / tot * width_cm
            if w <= 0:
                continue
            o.append(rf"\fill[{col}] ({x:.3f},{y:.3f}) rectangle ({x + w:.3f},{y + bar_h:.3f});")
            if text and w > 0.25 * max(len(text), 3) * 0.6:
                o.append(
                    rf"\node[text=white,font=\tiny\bfseries] at ({x + w / 2:.3f},"
                    rf"{y + bar_h / 2:.3f}) {{{tex(text)}}};"
                )
            x += w
    lx, ly = 0.0, -0.25
    for lab, col in legend:
        step = 0.7 + 0.14 * len(lab)
        if lx and lx + step > width_cm:
            lx, ly = 0.0, ly - 0.4
        o.append(
            rf"\fill[{col}] ({lx:.2f},{ly - 0.1:.2f}) rectangle ({lx + 0.25:.2f},{ly + 0.1:.2f});"
        )
        o.append(rf"\node[anchor=west,text=dgnavy] at ({lx + 0.3:.2f},{ly:.2f}) {{{tex(lab)}}};")
        lx += step
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)


def diverging_hbar(
    rows: Sequence[tuple[str, float]],
    half_width_cm: float = 4.0,
    *,
    fmt: Callable[[float], str] | None = None,
    bar_h: float = 0.34,
    gap: float = 0.14,
) -> str:
    """Bars left (negative, red) or right (positive, green) of a zero line."""
    fmt = fmt or (lambda v: f"{v * 100:+.0f} pp")
    vmax = max([abs(v) for _, v in rows] + [1e-9])
    h = max(len(rows), 1) * (bar_h + gap)
    x0 = half_width_cm + 3.0
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    for i, (lab, v) in enumerate(rows):
        y = h - (i + 1) * (bar_h + gap) + gap / 2
        w = v / vmax * half_width_cm
        col = "dgaccent" if v >= 0 else "dgred"
        o.append(rf"\node[anchor=east,text=dgnavy] at (0,{y + bar_h / 2:.3f}) {{{tex(lab)}}};")
        o.append(rf"\fill[{col}] ({x0:.3f},{y:.3f}) rectangle ({x0 + w:.3f},{y + bar_h:.3f});")
        anchor = "west" if v >= 0 else "east"
        o.append(
            rf"\node[anchor={anchor},text=dgnavy,font=\tiny] at "
            rf"({x0 + w + (0.05 if v >= 0 else -0.05):.3f},{y + bar_h / 2:.3f}) {{{fmt(v)}}};"
        )
    o.append(rf"\draw[dggray] ({x0:.3f},-0.05) -- ({x0:.3f},{h + 0.05:.3f});")
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)


def strip_chart(
    groups: Sequence[tuple[str, Sequence[tuple[float, str]]]],
    width_cm: float = 9.0,
    *,
    vmin: float = 0.1,
    vmax: float = 10.0,
    ref: float = 1.0,
    row_h: float = 0.5,
) -> str:
    """Dots per row on a log axis, with a reference line (e.g. 1.0x the market median)."""
    span = math.log10(vmax) - math.log10(vmin)

    def xpos(v: float) -> float:
        v = min(max(v, vmin), vmax)
        return (math.log10(v) - math.log10(vmin)) / span * width_cm

    h = max(len(groups), 1) * row_h
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    for i, (lab, pts) in enumerate(groups):
        y = h - (i + 0.5) * row_h
        o.append(rf"\node[anchor=east,text=dgnavy] at (-0.1,{y:.3f}) {{{tex(lab)}}};")
        o.append(rf"\draw[dglight] (0,{y:.3f}) -- ({width_cm:.3f},{y:.3f});")
        for j, (v, col) in enumerate(pts):
            jitter = ((j % 3) - 1) * 0.08
            o.append(rf"\fill[{col},opacity=0.8] ({xpos(v):.3f},{y + jitter:.3f}) circle (2.4pt);")
    for tick in (vmin, ref, vmax):
        o.append(
            rf"\node[anchor=north,text=dggray,font=\tiny] at ({xpos(tick):.3f},0) "
            rf"{{{_tick(tick)}x}};"
        )
    o.append(rf"\draw[dgred,thick,dashed] ({xpos(ref):.3f},0) -- ({xpos(ref):.3f},{h:.3f});")
    o.append(rf"\draw[dggray!60] (0,0) -- ({width_cm:.3f},0);")
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)
