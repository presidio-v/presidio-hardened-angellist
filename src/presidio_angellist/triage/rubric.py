"""
Deterministic pre-seed / seed triage rubric.

Six dimensions, each scored 0-5 from whatever fields the intake step could
extract, rolled into a weighted composite (0-100) and a tier. Every score
carries a plain-text rationale so the result is auditable -- the LLM memo step
is layered on top, never a substitute for this.
"""

from __future__ import annotations

from presidio_angellist.models import Deal, DimensionScore, Scorecard

# Relative weights; need not sum to 1 (the composite normalizes by total weight).
DEFAULT_WEIGHTS: dict[str, float] = {
    "team": 0.30,
    "market": 0.20,
    "traction": 0.20,
    "terms": 0.15,
    "syndicate": 0.15,
}

# Rough valuation-cap ceilings (USD) beyond which a round looks expensive for
# the stage. Used only for transparent flagging, not hard rejection.
_CAP_CEILING = {"pre-seed": 15_000_000, "seed": 30_000_000}

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


def score_deal(deal: Deal, weights: dict[str, float] | None = None) -> Scorecard:
    """Run the rubric over a deal and return a :class:`Scorecard`."""
    w = weights or DEFAULT_WEIGHTS
    risk_flags: list[str] = []

    dims = [
        _score_team(deal, w["team"], risk_flags),
        _score_market(deal, w["market"]),
        _score_traction(deal, w["traction"], risk_flags),
        _score_terms(deal, w["terms"], risk_flags),
        _score_syndicate(deal, w["syndicate"], risk_flags),
    ]
    return Scorecard(dimensions=dims, risk_flags=risk_flags)


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


def _score_terms(deal: Deal, weight: float, flags: list[str]) -> DimensionScore:
    notes = []
    score = 3.0

    if deal.valuation_cap is None:
        flags.append("No valuation cap extracted")
        notes.append("no cap")
        score -= 0.5
    else:
        notes.append(f"cap ${deal.valuation_cap:,.0f}")
        ceiling = _CAP_CEILING.get(deal.stage or "", _CAP_CEILING["seed"])
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
