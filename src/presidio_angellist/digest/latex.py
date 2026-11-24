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
) -> str:
    """Grouped vertical columns.

    ``groups`` = (raw label, [column, ...]) where each column is a stack of
    (value, colour) segments drawn bottom-up. The column total is printed on top.
    """
    totals = [sum(max(v, 0.0) for v, _ in col) for _, cols in groups for col in cols]
    vmax = max(totals, default=0.0) or 1.0
    slot = width_cm / max(len(groups), 1)
    o = [r"\begin{tikzpicture}[font=\scriptsize]"]
    o.append(rf"\draw[dggray!60] (0,0) -- ({width_cm:.2f},0);")
    for gi, (lab, cols) in enumerate(groups):
        bw = min(0.6, slot * 0.8 / max(len(cols), 1))
        x0 = gi * slot + (slot - bw * len(cols)) / 2
        for ci, col in enumerate(cols):
            x = x0 + ci * bw
            base = 0.0
            for v, colour in col:
                v = max(v, 0.0)
                y0, y1 = base / vmax * height_cm, (base + v) / vmax * height_cm
                if y1 - y0 > 0.005:
                    o.append(
                        rf"\fill[{colour}] ({x:.3f},{y0:.3f}) rectangle "
                        rf"({x + bw * 0.9:.3f},{y1:.3f});"
                    )
                base += v
            o.append(
                rf"\node[anchor=south,text=dgnavy,font=\tiny] at ({x + bw * 0.45:.3f},"
                rf"{base / vmax * height_cm:.3f}) {{{fmt(base)}}};"
            )
        o.append(
            rf"\node[anchor=north,text=dgnavy] at ({gi * slot + slot / 2:.3f},-0.05) "
            rf"{{{tex(lab)}}};"
        )
    lx = 0.0
    for lab, colour in legend:
        o.append(rf"\fill[{colour}] ({lx:.2f},-0.75) rectangle ({lx + 0.25:.2f},-0.55);")
        o.append(rf"\node[anchor=west,text=dgnavy] at ({lx + 0.3:.2f},-0.65) {{{tex(lab)}}};")
        lx += 0.7 + 0.14 * len(lab)
    o.append(r"\end{tikzpicture}")
    return "\n".join(o)
