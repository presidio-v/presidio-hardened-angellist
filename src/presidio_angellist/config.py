"""
Loading rubric configuration from a JSON file.

Two entry points:

- :func:`load_weights` — the simple ``--weights`` shape: a flat object of
  ``dimension -> number`` (merged over the default weights).
- :func:`load_rubric_config` — the full ``--rubric`` shape: an object that may
  carry ``weights``, ``tier_thresholds``, ``cap_ceilings``, and ``risk_penalty``.

Kept separate from the scoring logic so file IO / validation lives in one place.
Validation fails closed: anything malformed raises :class:`WeightsConfigError`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presidio_angellist.rubric_config import (
    DEFAULT_CAP_CEILINGS,
    DEFAULT_TIERS,
    DEFAULT_WEIGHTS,
    RubricConfig,
)

_TOP_LEVEL_KEYS = {"weights", "tier_thresholds", "cap_ceilings", "risk_penalty"}


class WeightsConfigError(ValueError):
    """Raised when a rubric config file is missing, malformed, or invalid."""


def _load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WeightsConfigError(f"config file not found: {path}") from exc
    except OSError as exc:
        raise WeightsConfigError(f"could not read config file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WeightsConfigError(f"invalid JSON in config file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WeightsConfigError("config file must be a JSON object")
    return raw


def _is_number(value: Any) -> bool:
    # bool is a subclass of int -- reject it as a numeric weight.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_weights(raw: dict[str, Any]) -> dict[str, float]:
    """Validate a flat dimension->number object and merge over DEFAULT_WEIGHTS."""
    unknown = set(raw) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise WeightsConfigError(
            f"unknown rubric dimension(s): {', '.join(sorted(unknown))}; "
            f"valid dimensions are: {', '.join(DEFAULT_WEIGHTS)}"
        )
    merged = dict(DEFAULT_WEIGHTS)
    for key, value in raw.items():
        if not _is_number(value) or value < 0:
            raise WeightsConfigError(f"weight for '{key}' must be a non-negative number")
        merged[key] = float(value)
    if sum(merged.values()) <= 0:
        raise WeightsConfigError("at least one weight must be positive")
    return merged


def load_weights(path: str | Path) -> dict[str, float]:
    """
    Load rubric weights from a JSON file, merged over :data:`DEFAULT_WEIGHTS`.

    The file is a JSON object mapping rubric dimension names to non-negative
    numbers, e.g. ``{"team": 0.4, "traction": 0.25}``. Omitted dimensions keep
    their default weight; at least one must be positive.

    Raises
    ------
    WeightsConfigError
        On a missing file, invalid JSON, a non-object, an unknown dimension, a
        negative/non-numeric weight, or an all-zero set.
    """
    return _validate_weights(_load_json_object(path))


def _validate_cap_ceilings(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise WeightsConfigError("'cap_ceilings' must be an object of stage -> amount")
    merged = dict(DEFAULT_CAP_CEILINGS)
    for stage, amount in raw.items():
        if not _is_number(amount) or amount <= 0:
            raise WeightsConfigError(f"cap ceiling for '{stage}' must be a positive number")
        merged[str(stage)] = float(amount)
    return merged


def _validate_tier_thresholds(raw: Any) -> list[tuple[float, str]]:
    if not isinstance(raw, dict):
        raise WeightsConfigError("'tier_thresholds' must be an object of label -> score")
    merged: dict[str, float] = {label: score for score, label in DEFAULT_TIERS}
    for label, score in raw.items():
        if not _is_number(score) or not (0 <= score <= 100):
            raise WeightsConfigError(f"tier threshold for '{label}' must be a number in 0-100")
        merged[str(label)] = float(score)
    return sorted(((score, label) for label, score in merged.items()), reverse=True)


def load_rubric_config(path: str | Path) -> RubricConfig:
    """
    Load a full :class:`RubricConfig` from a JSON file.

    Recognized top-level keys (all optional):

    - ``weights`` — object of ``dimension -> number`` (see :func:`load_weights`)
    - ``tier_thresholds`` — object of ``tier label -> min composite score`` (0-100)
    - ``cap_ceilings`` — object of ``stage -> max sane valuation cap (USD)``
    - ``risk_penalty`` — composite points deducted per risk flag (>= 0)

    Unspecified sections fall back to the built-in defaults.

    Raises
    ------
    WeightsConfigError
        On a missing file, invalid JSON, a non-object, an unknown top-level key,
        or any malformed section.
    """
    raw = _load_json_object(path)
    unknown = set(raw) - _TOP_LEVEL_KEYS
    if unknown:
        raise WeightsConfigError(
            f"unknown config key(s): {', '.join(sorted(unknown))}; "
            f"valid keys are: {', '.join(sorted(_TOP_LEVEL_KEYS))}"
        )

    config = RubricConfig.default()

    if "weights" in raw:
        if not isinstance(raw["weights"], dict):
            raise WeightsConfigError("'weights' must be an object of dimension -> number")
        config.weights = _validate_weights(raw["weights"])
    if "cap_ceilings" in raw:
        config.cap_ceilings = _validate_cap_ceilings(raw["cap_ceilings"])
    if "tier_thresholds" in raw:
        config.tier_thresholds = _validate_tier_thresholds(raw["tier_thresholds"])
    if "risk_penalty" in raw:
        penalty = raw["risk_penalty"]
        if not _is_number(penalty) or penalty < 0:
            raise WeightsConfigError("'risk_penalty' must be a non-negative number")
        config.risk_penalty = float(penalty)

    return config
