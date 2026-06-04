"""Tests for rubric weight-config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from presidio_angellist.config import (
    WeightsConfigError,
    load_rubric_config,
    load_weights,
)
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


class TestLoadRubricConfig:
    def test_full_config_from_fixture(self) -> None:
        cfg = load_rubric_config(FIXTURES / "rubric.json")
        assert cfg.weights["team"] == 0.4
        assert cfg.weights["market"] == DEFAULT_WEIGHTS["market"]  # default kept
        assert cfg.cap_ceilings["pre-seed"] == 8_000_000
        assert cfg.cap_ceilings["seed"] == 30_000_000  # default kept
        assert cfg.risk_penalty == 5.0
        # tier thresholds sorted highest-first, with the Pass floor retained
        labels = [label for _, label in cfg.tier_thresholds]
        assert labels[0] == "Strong lead"
        assert ("Pass" in labels) and cfg.tier_thresholds[-1] == (0.0, "Pass")

    def test_empty_object_is_defaults(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text("{}")
        cfg = load_rubric_config(f)
        assert cfg.weights == DEFAULT_WEIGHTS
        assert cfg.risk_penalty == 0.0

    def test_unknown_top_level_key(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"weight": {"team": 1}}')
        with pytest.raises(WeightsConfigError, match="unknown config key"):
            load_rubric_config(f)

    def test_bad_cap_ceiling(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"cap_ceilings": {"seed": -1}}')
        with pytest.raises(WeightsConfigError, match="cap ceiling"):
            load_rubric_config(f)

    def test_cap_ceilings_not_object(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"cap_ceilings": 5}')
        with pytest.raises(WeightsConfigError, match="cap_ceilings"):
            load_rubric_config(f)

    def test_bad_tier_threshold_out_of_range(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"tier_thresholds": {"Strong lead": 150}}')
        with pytest.raises(WeightsConfigError, match="tier threshold"):
            load_rubric_config(f)

    def test_tier_thresholds_not_object(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"tier_thresholds": [90, 75]}')
        with pytest.raises(WeightsConfigError, match="tier_thresholds"):
            load_rubric_config(f)

    def test_bad_risk_penalty(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"risk_penalty": -2}')
        with pytest.raises(WeightsConfigError, match="risk_penalty"):
            load_rubric_config(f)

    def test_weights_section_not_object(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"weights": 3}')
        with pytest.raises(WeightsConfigError, match="weights"):
            load_rubric_config(f)

    def test_unknown_dimension_in_weights_section(self, tmp_path: Path) -> None:
        f = tmp_path / "r.json"
        f.write_text('{"weights": {"teamwork": 1}}')
        with pytest.raises(WeightsConfigError, match="unknown rubric dimension"):
            load_rubric_config(f)
