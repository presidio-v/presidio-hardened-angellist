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
        assert "config file not found" in capsys.readouterr().err


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


class TestRubricAndCsvCli:
    def test_rubric_option_changes_tier(self, capsys: pytest.CaptureFixture[str]) -> None:
        main([COMPLETE, "--no-llm", "--json"])
        base = json.loads(capsys.readouterr().out)["scorecard"]["composite"]
        rubric = str(FIXTURES / "rubric.json")
        main([COMPLETE, "--no-llm", "--json", "--rubric", rubric])
        tuned = json.loads(capsys.readouterr().out)["scorecard"]["composite"]
        assert tuned < base  # penalty + high-cap flag lower it

    def test_weights_and_rubric_mutually_exclusive(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(
            [
                COMPLETE,
                "--no-llm",
                "--weights",
                str(FIXTURES / "weights.json"),
                "--rubric",
                str(FIXTURES / "rubric.json"),
            ]
        )
        assert rc == 2
        assert "not both" in capsys.readouterr().err

    def test_csv_input_emits_one_per_row(self, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(FIXTURES / "deals.csv"), "--no-llm", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert {d["deal"]["company"] for d in data} == {"Nimbus Robotics", "Solo Stealth"}

    def test_bad_rubric_file_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main([COMPLETE, "--no-llm", "--rubric", "/nonexistent/rubric.json"])
        assert rc == 2


class TestQueueCli:
    def test_save_then_queue_round_trip(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        db = str(tmp_path / "q.db")
        rc = main([COMPLETE, "--no-llm", "--save", "--db", db])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Saved 1 deal(s)" in out

        rc = main(["--queue", "--db", db])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Nimbus Robotics" in out

    def test_queue_json(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        db = str(tmp_path / "q.db")
        main([COMPLETE, "--no-llm", "--save", "--db", db])
        capsys.readouterr()
        main(["--queue", "--db", db, "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert data[0]["company"] == "Nimbus Robotics"

    def test_empty_queue(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        rc = main(["--queue", "--db", str(tmp_path / "empty.db")])
        assert rc == 0
        assert "empty" in capsys.readouterr().out

    def test_set_status(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        db = str(tmp_path / "q.db")
        main([COMPLETE, "--no-llm", "--save", "--db", db])
        capsys.readouterr()
        rc = main(["--set-status", "1", "passed", "--db", db])
        assert rc == 0
        assert "passed" in capsys.readouterr().out

    def test_set_status_bad_id(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        rc = main(["--set-status", "notanint", "passed", "--db", str(tmp_path / "q.db")])
        assert rc == 2
        assert "must be an integer" in capsys.readouterr().err

    def test_set_status_bad_status(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        db = str(tmp_path / "q.db")
        main([COMPLETE, "--no-llm", "--save", "--db", db])
        capsys.readouterr()
        rc = main(["--set-status", "1", "bogus", "--db", db])
        assert rc == 2
        assert "unknown status" in capsys.readouterr().err

    def test_queue_invalid_status_filter(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        rc = main(["--queue", "--db", str(tmp_path / "q.db"), "--status", "bogus"])
        assert rc == 2

    def test_nothing_to_do(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main([])
        assert rc == 2
        assert "nothing to do" in capsys.readouterr().err


class TestImapCli:
    def test_imap_flag_triages(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from presidio_angellist.intake.imap import ImapConfig
        from presidio_angellist.models import Deal, DimensionScore, Scorecard, TriageResult

        def fake_cfg(**kw) -> ImapConfig:
            return ImapConfig(host="h", user="u", password="p")  # noqa: S106 - test stub

        def fake_triage_imap(cfg, **kw):
            deal = Deal(company="ImapCo", raw_text="x")
            sc = Scorecard(dimensions=[DimensionScore("team", 4.0, 1.0, "n")])
            return [TriageResult(deal=deal, scorecard=sc)]

        monkeypatch.setattr("presidio_angellist.cli.imap_config_from_env", fake_cfg)
        monkeypatch.setattr("presidio_angellist.cli.triage_imap", fake_triage_imap)

        rc = main(["--imap", "--no-llm", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["deal"]["company"] == "ImapCo"

    def test_imap_config_error_exits_2(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from presidio_angellist.intake.imap import ImapError

        def boom(**kw):
            raise ImapError("missing IMAP credentials: IMAP_HOST")

        monkeypatch.setattr("presidio_angellist.cli.imap_config_from_env", boom)
        rc = main(["--imap", "--no-llm"])
        assert rc == 2
        assert "missing IMAP credentials" in capsys.readouterr().err

    def test_nothing_to_do_without_imap_or_inputs(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main([])
        assert rc == 2
        assert "--imap" in capsys.readouterr().err


class TestWatchCli:
    def test_watch_runs_and_reports(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from presidio_angellist.intake.imap import ImapConfig

        def fake_imap_config(**kw):
            return ImapConfig(host="h", user="u", password="p")  # noqa: S106 - test stub

        captured = {}

        def fake_watch(cfg, store, **kw):
            captured["interval"] = kw.get("interval")
            captured["max_cycles"] = kw.get("max_cycles")
            return 3

        monkeypatch.setattr("presidio_angellist.cli.imap_config_from_env", fake_imap_config)
        monkeypatch.setattr("presidio_angellist.cli.watch", fake_watch)

        rc = main(["--watch", "--no-llm", "--interval", "5", "--max-cycles", "2"])
        assert rc == 0
        assert captured == {"interval": 5.0, "max_cycles": 2}
        assert "saving 3 new deal(s)" in capsys.readouterr().err

    def test_watch_imap_config_error(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from presidio_angellist.intake.imap import ImapError

        def boom(**kw):
            raise ImapError("missing IMAP credentials: IMAP_HOST")

        monkeypatch.setattr("presidio_angellist.cli.imap_config_from_env", boom)
        rc = main(["--watch", "--no-llm"])
        assert rc == 2
        assert "missing IMAP credentials" in capsys.readouterr().err

    def test_nothing_to_do_lists_watch(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main([])
        assert rc == 2
        assert "--watch" in capsys.readouterr().err


class TestScopeRendering:
    def test_growth_deal_shows_out_of_scope(self, capsys: pytest.CaptureFixture[str]) -> None:
        growth = str(FIXTURES / "deal_growth.eml")
        rc = main([growth, "--no-llm"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Out of scope" in out
        assert "growth-stage" in out

    def test_growth_deal_json_has_scope_note(self, capsys: pytest.CaptureFixture[str]) -> None:
        growth = str(FIXTURES / "deal_growth.eml")
        main([growth, "--no-llm", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["scorecard"]["scope_note"] is not None
        assert data["deal"]["company"] == "Campus"
