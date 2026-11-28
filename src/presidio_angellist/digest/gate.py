"""
Gate retro-check: score historical positions against an LP decision-gate config.

The gate config is operator-supplied JSON (see ``contrib/digest/gate-config.example.json``).
Only the checks an investments export can answer are scored retrospectively:

  stage   the round label is an allowed stage and the round size fits that label
  sector  the position's thesis bucket is on-thesis (avoid-list is a hard no)
  cap     post-money cap (pre-money counts as pre + round) against the norm and ceiling
  lead    the top-lead substitute (a lead listed in ``top_three_leads``)
  size    the running total per lead per calendar year, in date order

A hard ``no`` on stage, sector, cap or size is a Fail; any other non-``yes`` is
Borderline. An unknown fact (no cap on record) counts as ``no``. The config is
validated strictly and fails closed: a missing required key raises
:class:`GateConfigError` rather than silently scoring against a default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from presidio_angellist.digest.csvload import Position

CHECKS = ("stage", "sector", "cap", "lead", "size")
HARD_CHECKS = ("stage", "sector", "cap", "size")
VERDICTS = ("Pass", "Borderline", "Fail")


class GateConfigError(ValueError):
    """Raised when a gate config is missing a required field or is malformed."""


def _strip_comments(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _strip_comments(v) for k, v in d.items() if not str(k).startswith("_")}
    return d


def _need(cfg: dict, *path: str) -> Any:
    cur: Any = cfg
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            raise GateConfigError(f"gate config is missing required field '{'.'.join(path)}'")
        cur = cur[key]
    return cur


def _number(cfg: dict, *path: str) -> float:
    v = _need(cfg, *path)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise GateConfigError(f"gate config field '{'.'.join(path)}' must be a number >= 0")
    return float(v)


def _str_list(cfg: dict, *path: str) -> list[str]:
    v = _need(cfg, *path)
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise GateConfigError(f"gate config field '{'.'.join(path)}' must be a list of strings")
    return list(v)


def _str_map(cfg: dict, key: str) -> dict[str, str]:
    v = cfg.get(key, {})
    if not isinstance(v, dict) or not all(isinstance(x, str) for x in v.values()):
        raise GateConfigError(f"gate config field '{key}' must map strings to strings")
    return dict(v)


@dataclass
class GateConfig:
    """Validated gate parameters (only the fields the retro-check reads)."""

    per_lead_per_year: float
    stage_allowed: list[str]
    stage_aliases: dict[str, str]
    max_round_size: dict[str, float]
    cap_yes_max: float
    cap_no_above: float
    on_thesis: list[str]
    avoid: list[str]
    top_leads: dict[str, dict[str, Any]] = field(default_factory=dict)
    position_sectors: dict[str, str] = field(default_factory=dict)
    market_sectors: dict[str, str] = field(default_factory=dict)
    sector_labels: dict[str, str] = field(default_factory=dict)
    per_company_max: float | None = None
    standard_ticket: float | None = None
    label: str = "LP decision gate"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def bucket_label(self, bucket: str) -> str:
        if bucket in self.sector_labels:
            return self.sector_labels[bucket]
        base = bucket.replace("_", " ").strip().capitalize() or "Other"
        if bucket in self.avoid:
            return f"Avoid: {base.lower()}"
        if bucket not in self.on_thesis:
            return f"Off-thesis ({base.lower()})"
        return base


def parse_gate_config(data: Any) -> GateConfig:
    """Validate a decoded gate-config document. Fails closed on any missing field."""
    if not isinstance(data, dict):
        raise GateConfigError("gate config must be a JSON object")
    cfg = _strip_comments(data)
    allowed = [s.lower() for s in _str_list(cfg, "stage", "allowed")]
    sizes_raw = _need(cfg, "stage", "max_round_size_usd")
    if not isinstance(sizes_raw, dict):
        raise GateConfigError("gate config field 'stage.max_round_size_usd' must be an object")
    sizes: dict[str, float] = {}
    for st in allowed:
        sizes[st] = _number(cfg, "stage", "max_round_size_usd", st)
    aliases = _need(cfg, "stage").get("aliases", {})
    if not isinstance(aliases, dict):
        raise GateConfigError("gate config field 'stage.aliases' must be an object")
    yes_max = _number(cfg, "valuation", "cap_yes_max_usd")
    no_above = _number(cfg, "valuation", "cap_no_above_usd")
    if yes_max > no_above:
        raise GateConfigError("valuation.cap_yes_max_usd must not exceed cap_no_above_usd")
    top = cfg.get("top_three_leads", {})
    if not isinstance(top, dict) or not all(isinstance(v, dict) for v in top.values()):
        raise GateConfigError("gate config field 'top_three_leads' must map names to objects")
    limits = _need(cfg, "limits")
    sectors = _need(cfg, "sectors")
    labels = sectors.get("labels", {}) if isinstance(sectors, dict) else {}
    if not isinstance(labels, dict):
        raise GateConfigError("gate config field 'sectors.labels' must be an object")
    label = cfg.get("label") or cfg.get("version") or "LP decision gate"
    return GateConfig(
        per_lead_per_year=_number(cfg, "limits", "per_lead_per_year_usd"),
        stage_allowed=allowed,
        stage_aliases={str(k).lower(): str(v).lower() for k, v in aliases.items()},
        max_round_size=sizes,
        cap_yes_max=yes_max,
        cap_no_above=no_above,
        on_thesis=_str_list(cfg, "sectors", "on_thesis"),
        avoid=_str_list(cfg, "sectors", "avoid"),
        top_leads=top,
        position_sectors=_str_map(cfg, "position_sectors"),
        market_sectors=_str_map(cfg, "market_sectors"),
        sector_labels={str(k): str(v) for k, v in labels.items()},
        per_company_max=(
            _number(cfg, "limits", "per_company_max_usd")
            if "per_company_max_usd" in limits
            else None
        ),
        standard_ticket=(
            _number(cfg, "limits", "standard_ticket_usd")
            if "standard_ticket_usd" in limits
            else None
        ),
        label=str(label),
        raw=cfg,
    )


def load_gate_config(path: str | Path) -> GateConfig:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateConfigError(f"no such gate config: {p}") from exc
    except json.JSONDecodeError as exc:
        raise GateConfigError(f"gate config {p} is not valid JSON: {exc}") from exc
    return parse_gate_config(data)


@dataclass
class GateResult:
    """Retro-check outcome for one position."""

    checks: dict[str, tuple[str, str]]  # check -> (yes|open|no, reason)
    verdict: str
    bucket: str

    @property
    def fails(self) -> list[str]:
        return [c for c in HARD_CHECKS if self.checks[c][0] == "no"]

    @property
    def reasons(self) -> str:
        return "; ".join(
            self.checks[c][1]
            for c in HARD_CHECKS
            if self.checks[c][0] != "yes" and self.checks[c][1]
        )


def bucket_of(p: Position, cfg: GateConfig) -> str:
    return cfg.position_sectors.get(p.name) or cfg.market_sectors.get(p.market) or "other"


def _fmt_m(v: float) -> str:
    return f"${v / 1e6:,.0f}M"


def _check_stage(p: Position, cfg: GateConfig) -> tuple[str, str]:
    st = p.stage.strip().lower()
    st = cfg.stage_aliases.get(st, st)
    if st not in cfg.stage_allowed:
        return ("no", p.stage or "no stage on record")
    if (p.round_size or 0.0) <= cfg.max_round_size[st]:
        return ("yes", "")
    return ("no", "round too big for label")


def _check_sector(bucket: str, cfg: GateConfig) -> tuple[str, str]:
    if bucket in cfg.avoid:
        return ("no", "avoid-list")
    if bucket in cfg.on_thesis:
        return ("yes", "")
    return ("no", "off-thesis")


def _check_cap(p: Position, cfg: GateConfig) -> tuple[str, str]:
    pc = p.post_cap
    if pc is None:
        return ("no", "no cap (unknown = no)")
    if p.cap_currency and p.cap_currency != "USD":
        return ("open", f"{_fmt_m(pc)} post ({p.cap_currency})".replace("$", ""))
    if pc > cfg.cap_no_above:
        return ("no", f"{_fmt_m(pc)} post")
    if pc > cfg.cap_yes_max:
        return ("open", f"{_fmt_m(pc)} post")
    return ("yes", f"{_fmt_m(pc)} post")


def _check_lead(p: Position, cfg: GateConfig) -> tuple[str, str]:
    t = cfg.top_leads.get(p.lead)
    if t is None:
        return ("no", "")
    if t.get("qualified"):
        return ("open", "qualified")
    return ("yes", "")


def gate_retro(positions: list[Position], cfg: GateConfig) -> list[GateResult]:
    """Score positions against the gate. Returns results aligned with ``positions``.

    The per-lead limit is a running total per (lead, calendar year), accumulated in
    date order regardless of the order ``positions`` arrives in.
    """
    order = sorted(range(len(positions)), key=lambda i: (positions[i].invest_date, i))
    running: dict[tuple[str, int], float] = {}
    out: list[GateResult | None] = [None] * len(positions)
    for i in order:
        p = positions[i]
        b = bucket_of(p, cfg)
        key = (p.lead, p.year)
        running[key] = running.get(key, 0.0) + p.invested
        total = running[key]
        size = (
            ("yes", "")
            if total <= cfg.per_lead_per_year + 1
            else ("no", f"lead total ${total / 1e3:,.0f}k")
        )
        checks = {
            "stage": _check_stage(p, cfg),
            "sector": _check_sector(b, cfg),
            "cap": _check_cap(p, cfg),
            "lead": _check_lead(p, cfg),
            "size": size,
        }
        if any(checks[c][0] == "no" for c in HARD_CHECKS):
            verdict = "Fail"
        elif any(v[0] != "yes" for v in checks.values()):
            verdict = "Borderline"
        else:
            verdict = "Pass"
        out[i] = GateResult(checks=checks, verdict=verdict, bucket=b)
    return [r for r in out if r is not None]
