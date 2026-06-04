"""Tests for the angeltriage CLI."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from presidio_angellist.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
COMPLETE = str(FIXTURES / "deal_complete.eml")
SPARSE = str(FIXTURES / "deal_sparse.eml")


class TestTextOutput:
    def test_basic_scorecard(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main([COMPLETE, "--no-llm"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Nimbus Robotics" in out
        assert "Strong lead" in out

    def test_memo_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        main([COMPLETE, "--no-llm", "--memo"])
        out = capsys.readouterr().out
        assert "Diligence Checklist" in out


class TestWeightsOption:
    def test_weights_file_changes_composite(self, capsys: pytest.CaptureFixture[str]) -> None:
        main([COMPLETE, "--no-llm", "--json"])
        base = json.loads(capsys.readouterr().out)["scorecard"]["composite"]
        weights = str(FIXTURES / "weights.json")
        main([COMPLETE, "--no-llm", "--json", "--weights", weights])
        tuned = json.loads(capsys.readouterr().out)["scorecard"]["composite"]
        assert tuned != base

    def test_invalid_weights_file_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main([COMPLETE, "--no-llm", "--weights", "/nonexistent/weights.json"])
        assert rc == 2
        assert "weights file not found" in capsys.readouterr().err


class TestJsonOutput:
    def test_single_json_object(self, capsys: pytest.CaptureFixture[str]) -> None:
        main([COMPLETE, "--no-llm", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["deal"]["company"] == "Nimbus Robotics"
        assert "scorecard" in data

    def test_batch_json_is_list_sorted_desc(self, capsys: pytest.CaptureFixture[str]) -> None:
        main([SPARSE, COMPLETE, "--no-llm", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        scores = [d["scorecard"]["composite"] for d in data]
        assert scores == sorted(scores, reverse=True)


class TestInputHandling:
    def test_missing_file_returns_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["/nonexistent/deal.eml", "--no-llm"])
        assert rc == 2
        assert "no such file" in capsys.readouterr().err

    def test_stdin(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO("Subject: Pipe Co\n\nseed, $1M cap on a SAFE. https://pipe.example.com"),
        )
        rc = main(["-", "--no-llm"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Pipe Co" in out

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
