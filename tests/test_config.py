"""Tests for rubric weight-config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from presidio_angellist.config import WeightsConfigError, load_weights
from presidio_angellist.triage.rubric import DEFAULT_WEIGHTS

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadWeights:
    def test_partial_override_merges_with_defaults(self) -> None:
        weights = load_weights(FIXTURES / "weights.json")
        assert weights["team"] == 0.5
        assert weights["traction"] == 0.3
        # unspecified dimensions keep their defaults
        assert weights["market"] == DEFAULT_WEIGHTS["market"]
        assert set(weights) == set(DEFAULT_WEIGHTS)

    def test_full_override(self, tmp_path: Path) -> None:
        f = tmp_path / "w.json"
        f.write_text('{"team": 1, "market": 1, "traction": 1, "terms": 1, "syndicate": 1}')
        weights = load_weights(f)
        assert all(v == 1.0 for v in weights.values())

    def test_missing_file(self) -> None:
        with pytest.raises(WeightsConfigError, match="not found"):
            load_weights(FIXTURES / "does_not_exist.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        with pytest.raises(WeightsConfigError, match="invalid JSON"):
            load_weights(f)

    def test_not_an_object(self, tmp_path: Path) -> None:
        f = tmp_path / "list.json"
        f.write_text("[1, 2, 3]")
        with pytest.raises(WeightsConfigError, match="must be a JSON object"):
            load_weights(f)

    def test_unknown_dimension(self, tmp_path: Path) -> None:
        f = tmp_path / "w.json"
        f.write_text('{"teamwork": 0.5}')
        with pytest.raises(WeightsConfigError, match="unknown rubric dimension"):
            load_weights(f)

    def test_negative_weight(self, tmp_path: Path) -> None:
        f = tmp_path / "w.json"
        f.write_text('{"team": -0.1}')
        with pytest.raises(WeightsConfigError, match="non-negative"):
            load_weights(f)

    def test_non_numeric_weight(self, tmp_path: Path) -> None:
        f = tmp_path / "w.json"
        f.write_text('{"team": "lots"}')
        with pytest.raises(WeightsConfigError, match="non-negative"):
            load_weights(f)

    def test_bool_weight_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "w.json"
        f.write_text('{"team": true}')
        with pytest.raises(WeightsConfigError, match="non-negative"):
            load_weights(f)

    def test_all_zero_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "w.json"
        f.write_text('{"team": 0, "market": 0, "traction": 0, "terms": 0, "syndicate": 0}')
        with pytest.raises(WeightsConfigError, match="at least one weight must be positive"):
            load_weights(f)
