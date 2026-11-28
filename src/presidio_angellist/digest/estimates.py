"""
Advisor estimates for positions whose AngelList value is still locked.

AngelList shows no mark for a locked position, so TVPI either ignores it (marked
only) or carries it at cost. An operator can supply a private JSON file of
estimates drawn from public information (a later priced round, an acquisition, a
shutdown ...)::

    {"as_of": "...", "method": "...",
     "positions": {"<company>": {"evidence": "priced_round", "event": "...",
                                 "post_money_usd": 40000000, "est_multiple": 2.0,
                                 "range": [1.5, 3.0], "confidence": "medium",
                                 "sources": [{"label": "...", "url": "https://..."}]}}}

Estimates apply **only** to locked positions; a marked position always uses its
mark. For an estimated multiple ``m`` on ``invested``:

- gross value = invested × m
- net value   = invested × (1 + (m − 1) × (1 − carry)) when m > 1, else invested × m

``carry`` comes from the export's ``Carry`` column; an empty column is taken as
20%, the standard syndicate carry. These are advisor estimates, not marks, and
the PDF says so. The file is validated strictly; a bad value raises
:class:`EstimatesError`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from presidio_angellist.digest.config import DigestConfigError, load_structured
from presidio_angellist.digest.latex import safe_url, short_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from presidio_angellist.digest.csvload import Position

_log = logging.getLogger("presidio_angellist")

EVIDENCE = ("priced_round", "acquisition", "shutdown", "down_round", "distress", "none")
CONFIDENCE = ("high", "medium", "low")
DEFAULT_CARRY = 0.20
_PCT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%?\s*$")


class EstimatesError(DigestConfigError):
    """Raised when a locked-estimates file is malformed."""


@dataclass
class LockedEstimate:
    name: str
    evidence: str
    est_multiple: float
    low: float
    high: float
    confidence: str
    event: str = ""
    post_money: float | None = None
    sources: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Estimates:
    as_of: str = ""
    method: str = ""
    positions: dict[str, LockedEstimate] = field(default_factory=dict)

    def for_position(self, p: Position) -> LockedEstimate | None:
        """The estimate for a *locked* position (exact name, then without batch suffix)."""
        if not p.locked:
            return None
        hit = self.positions.get(p.name)
        if hit is not None:
            return hit
        key = short_name(p.name).strip().lower()
        for name, est in self.positions.items():
            if short_name(name).strip().lower() == key:
                return est
        return None

    def unknown_names(self, positions: Iterable[Position]) -> list[str]:
        """Estimate names that match no position in the export."""
        names = {p.name for p in positions}
        shorts = {short_name(n).strip().lower() for n in names}
        return sorted(
            n
            for n in self.positions
            if n not in names and short_name(n).strip().lower() not in shorts
        )


def _num(v: Any, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise EstimatesError(f"locked estimates: {what} must be a number")
    return float(v)


def _entry(name: str, raw: Any) -> LockedEstimate:
    if not isinstance(raw, dict):
        raise EstimatesError("locked estimates: each position must be an object")
    evidence = raw.get("evidence")
    if evidence not in EVIDENCE:
        raise EstimatesError(
            f"locked estimates: evidence must be one of {', '.join(EVIDENCE)} (got {evidence!r})"
        )
    m = _num(raw.get("est_multiple"), "est_multiple")
    if m < 0:
        raise EstimatesError("locked estimates: est_multiple must not be negative")
    rng = raw.get("range", [m, m])
    if not isinstance(rng, list) or len(rng) != 2:
        raise EstimatesError("locked estimates: range must be [low, high]")
    lo, hi = _num(rng[0], "range low"), _num(rng[1], "range high")
    if lo < 0 or lo > hi:
        raise EstimatesError("locked estimates: range must satisfy 0 <= low <= high")
    conf = raw.get("confidence", "low")
    if conf not in CONFIDENCE:
        raise EstimatesError(
            f"locked estimates: confidence must be one of {', '.join(CONFIDENCE)}"
        )
    pm = raw.get("post_money_usd")
    post = None if pm is None else _num(pm, "post_money_usd")
    if post is not None and post < 0:
        raise EstimatesError("locked estimates: post_money_usd must not be negative")
    sources = []
    for s in raw.get("sources") or []:
        if isinstance(s, dict) and safe_url(s.get("url")):
            sources.append({"label": str(s.get("label") or s["url"]), "url": str(s["url"])})
    event = raw.get("event")
    return LockedEstimate(
        name=name,
        evidence=evidence,
        est_multiple=m,
        low=lo,
        high=hi,
        confidence=conf,
        event="" if event is None else str(event),
        post_money=post,
        sources=sources,
    )


def parse_estimates(data: Any) -> Estimates:
    if not isinstance(data, dict):
        raise EstimatesError("locked estimates must be a JSON object")
    positions = data.get("positions", {})
    if not isinstance(positions, dict):
        raise EstimatesError("locked estimates: 'positions' must be an object")
    return Estimates(
        as_of=str(data.get("as_of") or ""),
        method=str(data.get("method") or ""),
        positions={str(k): _entry(str(k), v) for k, v in positions.items()},
    )


def load_estimates(path: str | Path | None) -> Estimates | None:
    if path is None:
        return None
    return parse_estimates(load_structured(Path(path).expanduser()))


def carry_rate(p: Position) -> float:
    """The position's carry as a fraction; an empty or unreadable column -> 20%."""
    m = _PCT_RE.match(p.carry or "")
    if not m:
        return DEFAULT_CARRY
    v = float(m.group(1))
    return min(max(v / 100.0 if v > 1 or "%" in p.carry else v, 0.0), 1.0)


def est_gross(p: Position, e: LockedEstimate) -> float:
    return p.invested * e.est_multiple


def est_net(p: Position, e: LockedEstimate) -> float:
    m = e.est_multiple
    if m > 1:
        return p.invested * (1 + (m - 1) * (1 - carry_rate(p)))
    return p.invested * m


def value_incl_estimates(p: Position, est: Estimates | None, *, gross: bool = False) -> float:
    """Mark if marked; else cash paid out plus the estimate (net or gross); else at cost."""
    if p.net is not None:
        return p.net
    e = est.for_position(p) if est else None
    if e is None:
        return p.net_at_cost
    return p.realized + (est_gross(p, e) if gross else est_net(p, e))


def has_estimate(p: Position, est: Estimates | None) -> bool:
    return bool(est and est.for_position(p))
