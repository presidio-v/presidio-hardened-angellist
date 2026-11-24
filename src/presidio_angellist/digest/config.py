"""
Operator configuration for the digest: brand, editorial content, and the run config.

All three are private files that live outside this repository. The package ships
only neutral examples under ``contrib/digest/``. TOML is read with the stdlib
``tomllib`` (Python 3.11+), falling back to ``tomli`` when installed; JSON works
on every supported Python.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from presidio_angellist.digest.latex import hex_color, safe_url

_FONT_RE = re.compile(r"^[A-Za-z0-9 .\-]{1,64}$")
_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")
_LOGO_SUFFIXES = (".png", ".jpg", ".jpeg", ".pdf")
_MAX_CONTENT_BYTES = 2 * 1024 * 1024

DEFAULT_COLORS = {
    "navy": "1E293B",
    "accent": "0F766E",
    "light": "E2E8F0",
    "gray": "94A3B8",
    "blue": "2563EB",
    "red": "B91C1C",
    "amber": "B45309",
    "pale": "F1F5F9",
    "class_bg": "000000",
    "class_fg": "FFC000",
}
FALLBACK_FONT = "TeX Gyre Heros"


class DigestConfigError(ValueError):
    """Raised when a brand, content or run config file is missing or malformed."""


def load_structured(path: str | Path) -> dict[str, Any]:
    """Load a TOML or JSON object from ``path`` (chosen by suffix)."""
    p = Path(path)
    if not p.is_file():
        raise DigestConfigError(f"no such config file: {p}")
    if p.stat().st_size > _MAX_CONTENT_BYTES:
        raise DigestConfigError(f"config file too large: {p}")
    raw = p.read_bytes()
    if p.suffix.lower() == ".toml":
        try:
            import tomllib as toml_mod  # type: ignore[import-not-found]
        except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
            try:
                import tomli as toml_mod  # type: ignore[import-not-found,no-redef]
            except ModuleNotFoundError as exc:
                raise DigestConfigError(
                    f"{p}: TOML needs Python 3.11+ (or 'tomli'); use a .json file instead"
                ) from exc
        try:
            data = toml_mod.loads(raw.decode("utf-8"))
        except (toml_mod.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise DigestConfigError(f"{p} is not valid TOML: {exc}") from exc
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DigestConfigError(f"{p} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DigestConfigError(f"{p} must contain an object at the top level")
    return data


def slug(text: str, default: str = "Digest") -> str:
    s = _SLUG_RE.sub("-", text).strip("-")
    return s or default


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------


@dataclass
class Brand:
    """Visual identity of the generated PDF. Every text field is escaped on output."""

    name: str = "Portfolio"
    tagline: str = ""
    logo: Path | None = None
    colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COLORS))
    classification: str = "TLP:AMBER"
    classification_note: str = (
        "TLP:AMBER: limited disclosure; recipients may share only within their "
        "organisation on a need-to-know basis."
    )
    doc_id_prefix: str = "DIGEST"
    header_text: str = "Quarterly Digest"
    font: str = "Helvetica Neue"
    fallback_font: str = FALLBACK_FONT
    file_prefix: str = ""

    @property
    def file_stem(self) -> str:
        return slug(self.file_prefix or self.name)


def _font(value: Any, default: str) -> str:
    s = str(value or "").strip()
    if not s:
        return default
    if not _FONT_RE.match(s):
        raise DigestConfigError(f"brand font name {s!r} has unsupported characters")
    return s


def parse_brand(data: dict[str, Any], base_dir: Path | None = None) -> Brand:
    b = Brand()
    for key in ("name", "tagline", "classification", "classification_note", "header_text"):
        if key in data:
            setattr(b, key, str(data[key]))
    if "doc_id_prefix" in data:
        b.doc_id_prefix = str(data["doc_id_prefix"])
    if "file_prefix" in data:
        b.file_prefix = str(data["file_prefix"])
    b.font = _font(data.get("font"), b.font)
    b.fallback_font = _font(data.get("fallback_font"), b.fallback_font)
    colors = data.get("colors", {})
    if not isinstance(colors, dict):
        raise DigestConfigError("brand 'colors' must be a table/object")
    b.colors = {k: hex_color(colors.get(k), v) for k, v in DEFAULT_COLORS.items()}
    logo = data.get("logo")
    if logo:
        lp = Path(str(logo)).expanduser()
        if not lp.is_absolute() and base_dir is not None:
            lp = base_dir / lp
        if lp.suffix.lower() not in _LOGO_SUFFIXES:
            raise DigestConfigError(f"brand logo must be one of {', '.join(_LOGO_SUFFIXES)}")
        if not lp.is_file():
            raise DigestConfigError(f"brand logo not found: {lp}")
        b.logo = lp
    return b


def load_brand(path: str | Path | None) -> Brand:
    if path is None:
        return Brand()
    p = Path(path).expanduser()
    return parse_brand(load_structured(p), base_dir=p.parent)


# ---------------------------------------------------------------------------
# Editorial content (advisor-drafted, possibly LLM-drafted: untrusted text)
# ---------------------------------------------------------------------------

STATUSES = ("Ahead", "On track", "Behind", "No signal")


def _s(v: Any) -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    return str(v)


def _str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [_s(x) for x in v if _s(x)]


def _sources(v: Any) -> list[dict[str, str]]:
    out = []
    if not isinstance(v, list):
        return out
    for item in v:
        if not isinstance(item, dict):
            continue
        url = safe_url(item.get("url"))
        if url:
            out.append({"label": _s(item.get("label")) or url, "url": url})
    return out


def normalise_entry(raw: Any) -> dict[str, Any]:
    """Coerce one company/holding entry to the expected shape, dropping anything else."""
    if not isinstance(raw, dict):
        return {}
    e: dict[str, Any] = {}
    for key in ("one_liner", "forecast", "key_risk", "watch"):
        if _s(raw.get(key)):
            e[key] = _s(raw.get(key))
    st = _s(raw.get("status"))
    if st:
        e["status"] = st if st in STATUSES else "No signal"
    e["signals"] = _str_list(raw.get("signals"))
    e["sources"] = _sources(raw.get("sources"))
    p = raw.get("p_up_round")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and 0 <= p <= 1:
        e["p_up_round"] = float(p)
    return e


def normalise_content(raw: Any) -> dict[str, Any]:
    """Validate an editorial content document (vintage or aggregate schema)."""
    if not isinstance(raw, dict):
        raise DigestConfigError("content must be a JSON object")
    c: dict[str, Any] = {}
    for key in ("quarter", "as_of", "headline", "band", "gate_label"):
        if _s(raw.get(key)):
            c[key] = _s(raw.get(key))
    th = raw.get("thesis") if isinstance(raw.get("thesis"), dict) else {}
    pillars = []
    for pl in th.get("pillars", []) if isinstance(th.get("pillars"), list) else []:
        if isinstance(pl, dict):
            pillars.append({"title": _s(pl.get("title")), "text": _s(pl.get("text"))})
    c["thesis"] = {
        "statement": _s(th.get("statement")),
        "pillars": pillars,
        "vintage_note": _s(th.get("vintage_note")),
        "gate_checks": _str_list(th.get("gate_checks")),
    }
    sm = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
    c["summary"] = {
        k: _str_list(sm.get(k))
        for k in ("paragraphs", "strongest", "weakest", "actions", "lessons_for_gate")
    }
    for coll in ("companies", "holdings"):
        src = raw.get(coll)
        if isinstance(src, dict):
            c[coll] = {str(k): normalise_entry(v) for k, v in src.items()}
    return c


def load_content(path: str | Path | None) -> dict[str, Any]:
    """Load content JSON; a missing file yields an empty (but valid) document."""
    if path is None:
        return normalise_content({})
    p = Path(path)
    if not p.is_file():
        return normalise_content({})
    return normalise_content(load_structured(p))


def vintage_content_path(content_dir: Path, vintage: int) -> Path:
    """``vintage-<Y>.json`` if present, else the single-vintage ``content.json``."""
    specific = content_dir / f"vintage-{vintage}.json"
    return specific if specific.is_file() else content_dir / "content.json"


def band_content_path(content_dir: Path, band: str) -> Path:
    return content_dir / f"agg-{band}.json"


def draft_path(approved: Path) -> Path:
    """``content.json`` -> ``content.draft.json``; never the approved file itself."""
    return approved.with_name(f"{approved.stem}.draft{approved.suffix or '.json'}")


def parse_band(band: str) -> tuple[int, int]:
    """``"2017-2020"`` -> (2017, 2020). A single year is a one-year band."""
    m = re.fullmatch(r"\s*(\d{4})\s*(?:[-–]\s*(\d{4}))?\s*", str(band))
    if not m:
        raise DigestConfigError(f"band must look like 2017-2020, got {band!r}")
    first = int(m.group(1))
    last = int(m.group(2) or first)
    if last < first:
        raise DigestConfigError(f"band {band!r} ends before it starts")
    return first, last
