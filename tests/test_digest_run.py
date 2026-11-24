"""Digest orchestration: run config, scheduled run, notification, and the CLI."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from digest_helpers import AGG_CONTENT, BRAND, CSV, GATE, VINTAGE_CONTENT, fake_xelatex

from presidio_angellist.cli import main as angeltriage
from presidio_angellist.digest import runner
from presidio_angellist.digest.config import DigestConfigError, parse_band
from presidio_angellist.digest.runner import (
    current_quarter,
    load_run_config,
    parse_run_config,
    run,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def workspace(tmp_path):
    """A private-workspace lookalike built from the synthetic fixtures."""
    (tmp_path / "data").mkdir()
    shutil.copy(CSV, tmp_path / "data" / CSV.name)
    (tmp_path / "data" / "older_angellist_investments_2020_01_01.csv").write_text("stale")
    q = tmp_path / "digests" / "2026-Q4"
    q.mkdir(parents=True)
    shutil.copy(VINTAGE_CONTENT, q / "vintage-2026.json")
    shutil.copy(AGG_CONTENT, q / "agg-2017-2020.json")
    shutil.copy(GATE, tmp_path / "gate.json")
    shutil.copy(BRAND, tmp_path / "brand.toml")
    exe = fake_xelatex(tmp_path)
    cfg = {
        "csv_dir": "data",
        "gate_config": "gate.json",
        "brand": "brand.toml",
        "content_dir": "digests/{quarter}",
        "out_dir": "digests/{quarter}/out",
        "vintages": [2026],
        "bands": ["2017-2020"],
        "xelatex": exe,
    }
    path = tmp_path / "digest.json"
    path.write_text(json.dumps(cfg))
    return tmp_path, path, cfg


def test_current_quarter():
    assert current_quarter(date(2026, 11, 24)) == "2026-Q4"
    assert current_quarter(date(2027, 1, 1)) == "2027-Q1"
    assert current_quarter(date(2026, 6, 30)) == "2026-Q2"
    assert current_quarter().startswith(str(date.today().year))


def test_parse_band():
    assert parse_band("2017-2020") == (2017, 2020)
    assert parse_band("2026") == (2026, 2026)
    for bad in ("2020-2017", "twenty", "17-20"):
        with pytest.raises(DigestConfigError):
            parse_band(bad)


def test_example_run_config_parses():
    pytest.importorskip("tomllib")
    cfg = load_run_config(ROOT / "contrib" / "digest" / "digest.example.toml", "2026-Q4")
    assert cfg.content_dir.name == "2026-Q4"
    assert cfg.refresh is False and cfg.notify is False and cfg.attach_pdf is False
    assert cfg.bands == ["2017-2020", "2021-2025"]


@pytest.mark.parametrize(
    "patch",
    [
        {"gate_config": ""},
        {"csv_dir": None},
        {"vintages": ["2026"]},
        {"bands": [2017]},
        {"bands": ["bad"]},
        {"refresh": "yes"},
        {"refresh_options": []},
        {"refresh_options": {"redact_terms": "x"}},
    ],
)
def test_run_config_validation(tmp_path, patch):
    data = {"csv_dir": "d", "gate_config": "g", "content_dir": "c", "out_dir": "o"}
    data.update(patch)
    with pytest.raises(DigestConfigError):
        parse_run_config(data, tmp_path, "2026-Q4")


def test_run_builds_one_pdf_per_vintage_and_band(workspace):
    root, path, _ = workspace
    cfg = load_run_config(path, "2026-Q4")
    result = run(cfg, "2026-Q4", today=date(2026, 11, 28))
    assert result.errors == []
    assert result.csv.name == CSV.name  # newest by name, not the stale file
    names = sorted(p.name for p in result.pdfs)
    assert names == [
        "Example-Ventures-Digest-2026-Q4-2017-2020.pdf",
        "Example-Ventures-Digest-2026-Q4-2026-vintage.pdf",
    ]
    assert all(p.parent == root / "digests" / "2026-Q4" / "out" for p in result.pdfs)


def test_run_collects_errors_and_notifies_without_attachment(workspace, monkeypatch):
    _, path, data = workspace
    data["vintages"] = [2026, 1999]
    data["notify"] = True
    path.write_text(json.dumps(data))
    sent = {}

    def fake_send(config, subject, body, attachments=()):
        sent.update(subject=subject, body=body, attachments=list(attachments))

    monkeypatch.setattr("presidio_angellist.notify.send_plain", fake_send)
    monkeypatch.setattr("presidio_angellist.notify.notify_config_from_env", lambda: object())
    result = run(load_run_config(path, "2026-Q4"), "2026-Q4")
    assert any("1999" in e for e in result.errors)
    assert sent["attachments"] == []
    assert "2026-vintage.pdf" in sent["body"] and "$" not in sent["body"]

    data["attach_pdf"] = True
    path.write_text(json.dumps(data))
    run(load_run_config(path, "2026-Q4"), "2026-Q4")
    assert len(sent["attachments"]) == 2


def test_run_notify_failure_is_reported(workspace, monkeypatch):
    from presidio_angellist.notify import NotifyError

    _, path, data = workspace
    data["notify"] = True
    path.write_text(json.dumps(data))

    def boom():
        raise NotifyError("no smtp")

    monkeypatch.setattr("presidio_angellist.notify.notify_config_from_env", boom)
    result = run(load_run_config(path, "2026-Q4"), "2026-Q4")
    assert result.errors == ["notify: no smtp"]


def test_run_refresh_uses_injected_client(workspace):
    from test_digest_refresh import FakeClient

    root, path, data = workspace
    data["refresh"] = True
    data["refresh_options"] = {"redact_terms": ["Example Holdings LLC"], "max_searches": 2}
    path.write_text(json.dumps(data))
    client = FakeClient()
    result = run(load_run_config(path, "2026-Q4"), "2026-Q4", client=client)
    drafts = sorted(r.draft.name for r in result.refreshed)
    assert drafts == ["agg-2017-2020.draft.json", "vintage-2026.draft.json"]
    sent = json.dumps(client.calls)
    assert "Example Holdings" not in sent and "Example Ventures" not in sent
    # Approved content is untouched and the PDFs were built from it.
    assert (root / "digests" / "2026-Q4" / "vintage-2026.json").read_text() == (
        VINTAGE_CONTENT.read_text()
    )
    assert len(result.pdfs) == 2


def test_run_refresh_without_sdk_client(workspace, monkeypatch):
    from presidio_angellist.llm import LLMUnavailableError

    _, path, data = workspace
    data["refresh"] = True
    path.write_text(json.dumps(data))

    def no_sdk():
        raise LLMUnavailableError("anthropic SDK not installed")

    monkeypatch.setattr("presidio_angellist.digest.refresh.make_client", no_sdk)
    result = run(load_run_config(path, "2026-Q4"), "2026-Q4")
    assert result.errors == ["refresh: anthropic SDK not installed"]


# ---------------------------------------------------------------- CLI


def test_cli_run_dry_run(workspace, capsys):
    _, path, _ = workspace
    assert (
        angeltriage(["digest", "run", "--config", str(path), "--quarter", "2026-Q4", "--dry-run"])
        == 0
    )
    out = capsys.readouterr().out
    assert "quarter:  2026-Q4" in out and CSV.name in out and "refresh:  False" in out


def test_cli_run_builds(workspace, capsys):
    _, path, _ = workspace
    rc = angeltriage(
        ["digest", "run", "--config", str(path), "--quarter", "2026-Q4", "--no-notify"]
    )
    assert rc == 0
    assert capsys.readouterr().out.count(".pdf") == 2


def test_cli_run_bad_config(tmp_path, capsys):
    bad = tmp_path / "d.json"
    bad.write_text("{}")
    assert angeltriage(["digest", "run", "--config", str(bad)]) == 2
    assert "missing required key" in capsys.readouterr().err


def test_cli_build_vintage_and_band(workspace, capsys):
    root, _, data = workspace
    args = [
        "digest", "build", "--csv-dir", str(root / "data"),
        "--gate-config", str(root / "gate.json"),
        "--brand", str(root / "brand.toml"), "--content-dir", str(root / "digests" / "2026-Q4"),
        "--out-dir", str(root / "out"), "--quarter", "2026-Q4", "--as-of", "2026-11-30",
        "--vintage", "2026", "--band", "2017-2020", "--xelatex", data["xelatex"], "--keep-tex",
    ]  # fmt: skip
    assert angeltriage(args) == 0
    assert len(list((root / "out").glob("*.pdf"))) == 2
    tex = next((root / "out").glob("*2026-vintage.tex")).read_text()
    assert "2026-11-30" in tex


def test_cli_build_errors(workspace, capsys):
    root, _, data = workspace
    base = ["digest", "build", "--csv", str(root / "data" / CSV.name),
            "--gate-config", str(root / "gate.json"), "--out-dir", str(root / "out"),
            "--xelatex", data["xelatex"]]  # fmt: skip
    assert angeltriage(base) == 2  # no target
    assert angeltriage([*base, "--vintage", "2026", "--band", "2017-2020", "--content", "x"]) == 2
    assert angeltriage([*base, "--band", "nope"]) == 2
    assert angeltriage([*base, "--vintage", "1999"]) == 1
    missing_gate = [*base[:4], "--gate-config", str(root / "missing.json"), *base[6:]]
    assert angeltriage([*missing_gate, "--vintage", "2026"]) == 2


def test_cli_refresh(workspace, monkeypatch, capsys):
    from test_digest_refresh import FakeClient

    root, _, _ = workspace
    monkeypatch.setattr("presidio_angellist.digest.refresh.make_client", lambda: FakeClient())
    args = ["digest", "refresh", "--csv-dir", str(root / "data"),
            "--content-dir", str(root / "digests" / "2026-Q4"), "--vintage", "2026",
            "--band", "2017-2020", "--band", "1990-1991", "--redact", "Someone",
            "--brand", str(root / "brand.toml")]  # fmt: skip
    assert angeltriage(args) == 0
    out = capsys.readouterr()
    assert "vintage-2026.draft.json" in out.out and "1990-1991" in out.err
    assert angeltriage(args[:6]) == 2  # no target


def test_cli_refresh_skips_and_failures(workspace, monkeypatch, capsys):
    from types import SimpleNamespace

    from test_digest_refresh import FakeClient

    from presidio_angellist.llm import LLMUnavailableError

    root, _, _ = workspace
    refusal = SimpleNamespace(stop_reason="refusal", content=[])
    monkeypatch.setattr(
        "presidio_angellist.digest.refresh.make_client", lambda: FakeClient([refusal])
    )
    args = ["digest", "refresh", "--csv-dir", str(root / "data"),
            "--content-dir", str(root / "digests" / "2026-Q4"), "--vintage", "2026"]  # fmt: skip
    assert angeltriage(args) == 1
    assert "skipped" in capsys.readouterr().err

    def no_sdk():
        raise LLMUnavailableError("no sdk")

    monkeypatch.setattr("presidio_angellist.digest.refresh.make_client", no_sdk)
    assert angeltriage(args) == 2


def test_cli_refresh_bad_inputs(tmp_path):
    assert angeltriage(["digest", "refresh", "--csv-dir", str(tmp_path), "--vintage", "2026"]) == 2


def test_runner_output_name():
    from presidio_angellist.digest.config import Brand

    assert runner.output_name(Brand(name="A B"), "2026-Q4", "2026-vintage") == (
        "A-B-Digest-2026-Q4-2026-vintage.pdf"
    )
