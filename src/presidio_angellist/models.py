"""Dataclasses describing a deal, its scorecard, and the triage result."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from presidio_angellist.rubric_config import DEFAULT_TIERS


@dataclass
class Founder:
    """A founder mentioned in the deal."""

    name: str
    role: str | None = None
    linkedin: str | None = None
    background: str | None = None


@dataclass
class Deal:
    """
    A normalized early-stage deal, extracted from a syndicate email.

    Every field beyond ``company`` is optional: syndicate emails are
    inconsistent, and a missing field is a signal in its own right.
    """

    company: str
    one_liner: str | None = None
    sector: str | None = None
    stage: str | None = None  # "pre-seed" | "seed" | ...
    instrument: str | None = None  # "SAFE" | "priced equity" | ...
    valuation_cap: float | None = None  # USD
    round_size: float | None = None  # USD total round
    allocation: float | None = None  # USD allocated to this syndicate
    lead: str | None = None  # syndicate lead / GP
    deadline: str | None = None  # raw deadline text
    location: str | None = None
    traction: str | None = None
    website: str | None = None
    founders: list[Founder] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    source: str | None = None  # email subject / file name
    raw_text: str | None = None
    extraction_method: str = "deterministic"  # "deterministic" | "llm"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # raw_text is bulky and not useful in JSON output
        data.pop("raw_text", None)
        return data


@dataclass
class DimensionScore:
    """Score for one rubric dimension."""

    name: str
    score: float  # 0-5
    weight: float  # relative weight
    rationale: str


@dataclass
class Scorecard:
    """Result of running the deterministic rubric over a deal."""

    dimensions: list[DimensionScore]
    risk_flags: list[str] = field(default_factory=list)
    # Tier thresholds (highest first) and per-flag composite penalty; defaults
    # reproduce the built-in rubric, so existing callers are unaffected.
    tier_thresholds: list[tuple[float, str]] = field(default_factory=lambda: list(DEFAULT_TIERS))
    risk_penalty: float = 0.0
    # Set when the deal looks outside the pre-seed/seed scope the rubric targets,
    # in which case the composite/tier are only indicative.
    scope_note: str | None = None

    @property
    def composite(self) -> float:
        """Weighted score normalized to 0-100, minus any per-flag penalty."""
        total_weight = sum(d.weight for d in self.dimensions)
        if total_weight == 0:
            return 0.0
        weighted = sum(d.score * d.weight for d in self.dimensions)
        base = (weighted / (5.0 * total_weight)) * 100.0
        penalized = base - self.risk_penalty * len(self.risk_flags)
        return round(max(0.0, min(100.0, penalized)), 1)

    @property
    def tier(self) -> str:
        if self.scope_note:
            return "Out of scope"
        score = self.composite
        for threshold, label in sorted(self.tier_thresholds, reverse=True):
            if score >= threshold:
                return label
        return "Pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": self.composite,
            "tier": self.tier,
            "scope_note": self.scope_note,
            "dimensions": [asdict(d) for d in self.dimensions],
            "risk_flags": list(self.risk_flags),
        }


@dataclass
class TriageResult:
    """A fully triaged deal: parsed deal + scorecard + optional memo."""

    deal: Deal
    scorecard: Scorecard
    memo: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal": self.deal.to_dict(),
            "scorecard": self.scorecard.to_dict(),
            "memo": self.memo,
        }
