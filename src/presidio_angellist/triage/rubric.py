"""
Deterministic pre-seed / seed triage rubric.

Six dimensions, each scored 0-5 from whatever fields the intake step could
extract, rolled into a weighted composite (0-100) and a tier. Every score
carries a plain-text rationale so the result is auditable -- the LLM memo step
is layered on top, never a substitute for this.
"""

from __future__ import annotations

import re
from dataclasses import replace

from presidio_angellist.intake.email import parse_money
from presidio_angellist.models import Deal, DimensionScore, Scorecard
from presidio_angellist.rubric_config import DEFAULT_CAP_CEILINGS, DEFAULT_WEIGHTS, RubricConfig

__all__ = ["DEFAULT_WEIGHTS", "score_deal", "detect_stage_scope"]

# --- growth-stage (out-of-scope) detection ---------------------------------
# The rubric targets pre-seed/seed; flag deals that look later-stage so the
# score is presented as indicative rather than authoritative.
_GROWTH_ARR_USD = 5_000_000  # ARR/revenue at/above this reads as growth-stage
_LARGE_ROUND_USD = 15_000_000  # round size clearly above a typical seed
_LATER_STAGE_RE = re.compile(r"series[\s-]+[a-d]\b", re.IGNORECASE)
_PRICED_ROUND_RE = re.compile(
    r"\b(venture round|series[\s-]+[a-d]|priced round|growth round|growth equity)\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"\$\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmMbB]|thousand|million|billion)?")

_TRACTION_KEYWORDS = (
    "revenue",
    "arr",
    "mrr",
    "customers",
    "users",
    "paying",
    "waitlist",
    "growth",
    "mom",
    "month-over-month",
    "loi",
    "pilot",
    "contract",
    "bookings",
)
_STRONG_TEAM_KEYWORDS = (
    "ex-",
    "former",
    "phd",
    "second-time",
    "repeat founder",
    "exited",
    "acquired",
    "y combinator",
    "yc ",
    "techstars",
    "stanford",
    "mit",
    "google",
    "meta",
    "stripe",
)


def score_deal(
    deal: Deal,
    config: RubricConfig | None = None,
    weights: dict[str, float] | None = None,
) -> Scorecard:
    """
    Run the rubric over a deal and return a :class:`Scorecard`.

    Pass a :class:`RubricConfig` for full control (weights, tier thresholds, cap
    ceilings, per-flag penalty), or just ``weights`` for the common case of
    re-weighting dimensions. ``config`` takes precedence over ``weights``.
    """
    if config is None:
        config = RubricConfig.default()
        if weights is not None:
            config = replace(config, weights=weights)

    w = config.weights
    risk_flags: list[str] = []

    dims = [
        _score_team(deal, w["team"], risk_flags),
        _score_market(deal, w["market"]),
        _score_traction(deal, w["traction"], risk_flags),
        _score_terms(deal, w["terms"], risk_flags, config.cap_ceilings),
        _score_syndicate(deal, w["syndicate"], risk_flags),
    ]
    return Scorecard(
        dimensions=dims,
        risk_flags=risk_flags,
        tier_thresholds=config.tier_thresholds,
        risk_penalty=config.risk_penalty,
        scope_note=detect_stage_scope(deal),
    )


def detect_stage_scope(deal: Deal) -> str | None:
    """
    Return a note if the deal looks beyond pre-seed/seed (the rubric's scope).

    Signals: an explicit later-stage label, ARR/revenue at/above $5M, or a
    priced/venture round combined with a large round size or large ARR. Returns
    ``None`` for deals that look in-scope.
    """
    text = deal.raw_text or ""
    reasons: list[str] = []

    if deal.stage and _LATER_STAGE_RE.search(deal.stage):
        reasons.append(f"stage {deal.stage}")

    arr = _max_money_near(text, ("arr", "revenue", "mrr"))
    big_arr = arr is not None and arr >= _GROWTH_ARR_USD
    if big_arr:
        reasons.append(f"~${arr:,.0f} ARR/revenue")

    priced = _PRICED_ROUND_RE.search(text)
    big_round = deal.round_size is not None and deal.round_size >= _LARGE_ROUND_USD
    if priced and (big_round or big_arr):
        label = priced.group(1).lower()
        reasons.append(f"{label} ${deal.round_size:,.0f}" if big_round else label)

    if not reasons:
        return None
    return (
        "Likely growth-stage (" + "; ".join(reasons) + ") — outside pre-seed/seed "
        "scope; score is indicative only"
    )


def _max_money_near(text: str, keywords: tuple[str, ...], window: int = 25) -> float | None:
    """Largest dollar amount within ``window`` chars of any keyword."""
    low = text.lower()
    best: float | None = None
    for kw in keywords:
        for m in re.finditer(re.escape(kw), low):
            start = max(0, m.start() - window)
            end = min(len(text), m.end() + window)
            for mm in _MONEY_RE.finditer(text[start:end]):
                amount = parse_money(mm.group(1), mm.group(2))
                if amount is not None and (best is None or amount > best):
                    best = amount
    return best


def _haystack(deal: Deal) -> str:
    parts = [deal.raw_text or "", deal.one_liner or "", deal.traction or ""]
    return " ".join(parts).lower()


def _score_team(deal: Deal, weight: float, flags: list[str]) -> DimensionScore:
    text = _haystack(deal)
    n = len(deal.founders)
    score = 3.0
    notes = []

    if n == 0:
        score = 2.0
        notes.append("no founders identified")
    elif n == 1:
        score = 2.5
        notes.append("solo founder")
        flags.append("Solo founder -- no co-founder identified")
    else:
        score = 3.5
        notes.append(f"{n} founders")

    strong = [kw for kw in _STRONG_TEAM_KEYWORDS if kw in text]
    if strong:
        score = min(5.0, score + 1.0)
        notes.append(f"credential signals: {', '.join(sorted(set(strong)))[:80]}")

    return DimensionScore("team", round(score, 1), weight, "; ".join(notes) or "limited team data")


def _score_market(deal: Deal, weight: float) -> DimensionScore:
    if deal.one_liner and 20 <= len(deal.one_liner) <= 200:
        score, note = 3.5, "clear one-liner present"
    elif deal.sector:
        score, note = 3.0, f"sector: {deal.sector}"
    else:
        score, note = 2.5, "no crisp market framing extracted"
    note += " -- market sizing/'why now' needs the memo step or manual review"
    return DimensionScore("market", score, weight, note)


def _score_traction(deal: Deal, weight: float, flags: list[str]) -> DimensionScore:
    text = _haystack(deal)
    hits = sorted({kw for kw in _TRACTION_KEYWORDS if kw in text})
    if not hits:
        flags.append("No traction signal mentioned")
        return DimensionScore("traction", 2.0, weight, "no traction keywords found")
    score = min(5.0, 2.5 + 0.5 * len(hits))
    return DimensionScore("traction", round(score, 1), weight, f"signals: {', '.join(hits)}")


def _score_terms(
    deal: Deal,
    weight: float,
    flags: list[str],
    cap_ceilings: dict[str, float],
) -> DimensionScore:
    notes = []
    score = 3.0

    if deal.valuation_cap is None:
        flags.append("No valuation cap extracted")
        notes.append("no cap")
        score -= 0.5
    else:
        notes.append(f"cap ${deal.valuation_cap:,.0f}")
        ceiling = (
            cap_ceilings.get(deal.stage or "seed")
            or cap_ceilings.get("seed")
            or DEFAULT_CAP_CEILINGS["seed"]
        )
        if deal.valuation_cap > ceiling:
            flags.append(
                f"Cap ${deal.valuation_cap:,.0f} looks high for {deal.stage or 'this stage'}"
            )
            score -= 1.0
        else:
            score += 0.5

    if deal.instrument:
        notes.append(deal.instrument)
        if "safe" in deal.instrument.lower():
            score += 0.5

    rationale = "; ".join(notes) or "no terms data"
    return DimensionScore("terms", round(max(0.0, min(5.0, score)), 1), weight, rationale)


def _score_syndicate(deal: Deal, weight: float, flags: list[str]) -> DimensionScore:
    notes = []
    score = 3.0
    if deal.lead:
        score += 1.0
        notes.append(f"lead: {deal.lead}")
    else:
        notes.append("no named lead")
    if deal.allocation:
        notes.append(f"allocation ${deal.allocation:,.0f}")
    if not deal.website:
        flags.append("No company website found")
    return DimensionScore("syndicate", round(min(5.0, score), 1), weight, "; ".join(notes))
