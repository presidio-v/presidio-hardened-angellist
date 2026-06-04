"""
Rubric configuration data: default weights, tier thresholds, cap ceilings.

This is a leaf module — it imports nothing from the rest of the package — so both
the scoring logic (:mod:`presidio_angellist.triage.rubric`) and the config loader
(:mod:`presidio_angellist.config`) can depend on it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Relative weights; need not sum to 1 (the composite normalizes by total weight).
DEFAULT_WEIGHTS: dict[str, float] = {
    "team": 0.30,
    "market": 0.20,
    "traction": 0.20,
    "terms": 0.15,
    "syndicate": 0.15,
}

# Rough valuation-cap ceilings (USD) beyond which a round looks expensive for the
# stage. Used only for transparent flagging, not hard rejection.
DEFAULT_CAP_CEILINGS: dict[str, float] = {
    "pre-seed": 15_000_000,
    "seed": 30_000_000,
}

# Composite-score thresholds (0-100) mapped to a triage tier, highest first.
# The 0.0 entry is the floor, so a tier is always resolved.
DEFAULT_TIERS: list[tuple[float, str]] = [
    (75.0, "Strong lead"),
    (60.0, "Dig deeper"),
    (45.0, "Track"),
    (0.0, "Pass"),
]


@dataclass
class RubricConfig:
    """All knobs the deterministic rubric exposes for tuning."""

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    tier_thresholds: list[tuple[float, str]] = field(default_factory=lambda: list(DEFAULT_TIERS))
    cap_ceilings: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CAP_CEILINGS))
    # Points deducted from the composite (0-100) per risk flag. 0 = no penalty.
    risk_penalty: float = 0.0

    @classmethod
    def default(cls) -> RubricConfig:
        return cls()
