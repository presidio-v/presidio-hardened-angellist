"""Dataclasses describing a deal, its scorecard, and the triage result."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Composite-score thresholds (0-100) mapped to a triage tier.
_TIERS: list[tuple[float, str]] = [
    (75.0, "Strong lead"),
    (60.0, "Dig deeper"),
    (45.0, "Track"),
    (0.0, "Pass"),
]


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

    @property
    def composite(self) -> float:
        """Weighted score normalized to 0-100."""
        total_weight = sum(d.weight for d in self.dimensions)
        if total_weight == 0:
            return 0.0
        weighted = sum(d.score * d.weight for d in self.dimensions)
        return round((weighted / (5.0 * total_weight)) * 100.0, 1)

    @property
    def tier(self) -> str:
        score = self.composite
        for threshold, label in _TIERS:
            if score >= threshold:
                return label
        return "Pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": self.composite,
            "tier": self.tier,
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
