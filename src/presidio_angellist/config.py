"""
Loading rubric weight overrides from a config file.

Kept separate from :mod:`presidio_angellist.triage.rubric` so the scoring logic
stays pure and the file IO / validation lives in one place. The CLI exposes this
via ``angeltriage --weights FILE``.
"""

from __future__ import annotations

import json
from pathlib import Path

from presidio_angellist.triage.rubric import DEFAULT_WEIGHTS


class WeightsConfigError(ValueError):
    """Raised when a ``--weights`` config file is missing, malformed, or invalid."""


def load_weights(path: str | Path) -> dict[str, float]:
    """
    Load rubric weights from a JSON file, merged over :data:`DEFAULT_WEIGHTS`.

    The file is a JSON object mapping rubric dimension names to non-negative
    numbers, e.g. ``{"team": 0.4, "traction": 0.25}``. Dimensions you omit keep
    their default weight, so partial overrides are fine. Weights need not sum to
    one (the composite normalizes by total weight), but at least one must be
    positive.

    Raises
    ------
    WeightsConfigError
        If the file is missing, not valid JSON, not an object, references an
        unknown dimension, contains a negative/non-numeric weight, or zeroes out
        every dimension.
    """
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WeightsConfigError(f"weights file not found: {path}") from exc
    except OSError as exc:
        raise WeightsConfigError(f"could not read weights file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WeightsConfigError(f"invalid JSON in weights file {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise WeightsConfigError("weights file must be a JSON object of dimension -> weight")

    unknown = set(raw) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise WeightsConfigError(
            f"unknown rubric dimension(s): {', '.join(sorted(unknown))}; "
            f"valid dimensions are: {', '.join(DEFAULT_WEIGHTS)}"
        )

    merged = dict(DEFAULT_WEIGHTS)
    for key, value in raw.items():
        # bool is a subclass of int -- reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise WeightsConfigError(f"weight for '{key}' must be a non-negative number")
        merged[key] = float(value)

    if sum(merged.values()) <= 0:
        raise WeightsConfigError("at least one weight must be positive")
    return merged
