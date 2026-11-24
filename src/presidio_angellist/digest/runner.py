"""
Orchestration: build vintage and band digests, and the scheduled ``digest run``.

``digest run --config digest.toml`` reads a private run config (see
``contrib/digest/digest.example.toml``), picks the newest export in ``csv_dir``,
determines the current quarter, optionally refreshes editorial drafts, builds one
PDF per vintage and per band, and optionally sends a notification. Paths in the
config may contain ``{quarter}`` and resolve relative to the config file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from presidio_angellist.digest.build import compile_pdf
from presidio_angellist.digest.config import (
    Brand,
    DigestConfigError,
    band_content_path,
    load_brand,
    load_content,
    load_structured,
    parse_band,
    vintage_content_path,
)
from presidio_angellist.digest.csvload import in_years, load_positions, newest_export
from presidio_angellist.digest.gate import GateConfig, load_gate_config
from presidio_angellist.digest.render import DocMeta, build_aggregate_tex, build_vintage_tex

if TYPE_CHECKING:
    from presidio_angellist.digest.csvload import Position
    from presidio_angellist.digest.refresh import RefreshReport

_log = logging.getLogger("presidio_angellist")


def current_quarter(today: date | None = None) -> str:
    d = today or date.today()
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def output_name(brand: Brand, quarter: str, label: str) -> str:
    return f"{brand.file_stem}-Digest-{quarter}-{label}.pdf"


def _logo_ext(brand: Brand) -> str | None:
    return brand.logo.suffix.lower() if brand.logo else None


@dataclass
class Inputs:
    """Everything a build needs, already loaded."""

    positions: list[Position]
    gate: GateConfig
    brand: Brand
    content_dir: Path
    out_dir: Path
    quarter: str
    as_of: str
    version: str = "1.0"
    state: str = "draft"
    keep_tex: bool = False
    xelatex: str | None = None
    as_of_override: str | None = None


def build_vintage(inp: Inputs, vintage: int, content_path: Path | None = None) -> Path:
    positions = in_years(inp.positions, vintage)
    if not positions:
        raise DigestConfigError(f"no {vintage} positions in the export")
    cpath = content_path or vintage_content_path(inp.content_dir, vintage)
    content = load_content(cpath)
    meta = DocMeta(
        inp.quarter,
        inp.as_of_override or content.get("as_of") or inp.as_of,
        f"{vintage} vintage",
        inp.version,
        inp.state,
    )
    tex = build_vintage_tex(
        positions, inp.gate, content, inp.brand, meta, vintage, _logo_ext(inp.brand)
    )
    out = inp.out_dir / output_name(inp.brand, inp.quarter, f"{vintage}-vintage")
    return compile_pdf(tex, out, logo=inp.brand.logo, xelatex=inp.xelatex, keep_tex=inp.keep_tex)


def build_band(inp: Inputs, band: str, content_path: Path | None = None) -> Path:
    first, last = parse_band(band)
    positions = in_years(inp.positions, first, last)
    if not positions:
        raise DigestConfigError(f"no positions in band {band}")
    label = f"{first}-{last}" if last != first else str(first)
    cpath = content_path or band_content_path(inp.content_dir, label)
    content = load_content(cpath)
    as_of = inp.as_of_override or content.get("as_of") or inp.as_of
    meta = DocMeta(inp.quarter, as_of, label, inp.version, inp.state)
    tex = build_aggregate_tex(
        positions, inp.gate, content, inp.brand, meta, (first, last), _logo_ext(inp.brand)
    )
    out = inp.out_dir / output_name(inp.brand, inp.quarter, label)
    return compile_pdf(tex, out, logo=inp.brand.logo, xelatex=inp.xelatex, keep_tex=inp.keep_tex)


# ---------------------------------------------------------------------------
# Scheduled run
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    csv_dir: Path | None
    csv: Path | None
    gate_config: Path
    brand: Path | None
    content_dir: Path
    out_dir: Path
    vintages: list[int] = field(default_factory=list)
    bands: list[str] = field(default_factory=list)
    refresh: bool = False
    refresh_model: str | None = None
    refresh_max_searches: int = 5
    redact_terms: list[str] = field(default_factory=list)
    notify: bool = False
    attach_pdf: bool = False
    version: str = "1.0"
    state: str = "draft"
    keep_tex: bool = False
    xelatex: str | None = None


def _path(raw: Any, base: Path, quarter: str) -> Path:
    p = Path(str(raw).replace("{quarter}", quarter)).expanduser()
    return p if p.is_absolute() else base / p


def _bool(data: dict, key: str, default: bool = False) -> bool:
    v = data.get(key, default)
    if not isinstance(v, bool):
        raise DigestConfigError(f"run config '{key}' must be true or false")
    return v


def parse_run_config(data: dict[str, Any], base: Path, quarter: str) -> RunConfig:
    for key in ("gate_config", "content_dir", "out_dir"):
        if not data.get(key):
            raise DigestConfigError(f"run config is missing required key '{key}'")
    if not (data.get("csv_dir") or data.get("csv")):
        raise DigestConfigError("run config needs 'csv_dir' (or an explicit 'csv')")
    vintages = data.get("vintages", [])
    bands = data.get("bands", [])
    if not isinstance(vintages, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in vintages
    ):
        raise DigestConfigError("run config 'vintages' must be a list of years")
    if not isinstance(bands, list) or not all(isinstance(b, str) for b in bands):
        raise DigestConfigError("run config 'bands' must be a list of strings like '2017-2020'")
    for b in bands:
        parse_band(b)
    refresh = data.get("refresh_options", {})
    if not isinstance(refresh, dict):
        raise DigestConfigError("run config 'refresh_options' must be a table")
    terms = refresh.get("redact_terms", [])
    if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
        raise DigestConfigError("refresh_options.redact_terms must be a list of strings")
    return RunConfig(
        csv_dir=_path(data["csv_dir"], base, quarter) if data.get("csv_dir") else None,
        csv=_path(data["csv"], base, quarter) if data.get("csv") else None,
        gate_config=_path(data["gate_config"], base, quarter),
        brand=_path(data["brand"], base, quarter) if data.get("brand") else None,
        content_dir=_path(data["content_dir"], base, quarter),
        out_dir=_path(data["out_dir"], base, quarter),
        vintages=list(vintages),
        bands=list(bands),
        refresh=_bool(data, "refresh"),
        refresh_model=str(refresh["model"]) if refresh.get("model") else None,
        refresh_max_searches=int(refresh.get("max_searches", 5)),
        redact_terms=list(terms),
        notify=_bool(data, "notify"),
        attach_pdf=_bool(data, "attach_pdf"),
        version=str(data.get("version", "1.0")),
        state=str(data.get("state", "draft")),
        keep_tex=_bool(data, "keep_tex"),
        xelatex=str(data["xelatex"]) if data.get("xelatex") else None,
    )


def load_run_config(path: str | Path, quarter: str) -> RunConfig:
    p = Path(path).expanduser()
    return parse_run_config(load_structured(p), p.parent, quarter)


@dataclass
class RunResult:
    quarter: str
    csv: Path
    pdfs: list[Path] = field(default_factory=list)
    refreshed: list[RefreshReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run(
    cfg: RunConfig,
    quarter: str,
    *,
    today: date | None = None,
    client: Any = None,
    do_refresh: bool | None = None,
    do_notify: bool | None = None,
) -> RunResult:
    """Execute a scheduled digest run. Build failures are collected, not raised."""
    csv = cfg.csv or newest_export(cfg.csv_dir)  # type: ignore[arg-type]
    positions = load_positions(csv)
    gate = load_gate_config(cfg.gate_config)
    brand = load_brand(cfg.brand)
    as_of = (today or date.today()).isoformat()
    result = RunResult(quarter=quarter, csv=csv)
    inp = Inputs(
        positions=positions,
        gate=gate,
        brand=brand,
        content_dir=cfg.content_dir,
        out_dir=cfg.out_dir,
        quarter=quarter,
        as_of=as_of,
        version=cfg.version,
        state=cfg.state,
        keep_tex=cfg.keep_tex,
        xelatex=cfg.xelatex,
    )
    if cfg.refresh if do_refresh is None else do_refresh:
        _refresh_all(cfg, positions, brand, client, result)
    for v in cfg.vintages:
        try:
            result.pdfs.append(build_vintage(inp, v))
        except Exception as exc:  # noqa: BLE001 - one failed digest must not stop the rest
            result.errors.append(f"{v} vintage: {exc}")
    for b in cfg.bands:
        try:
            result.pdfs.append(build_band(inp, b))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"band {b}: {exc}")
    if cfg.notify if do_notify is None else do_notify:
        _notify(cfg, result)
    return result


def _refresh_all(
    cfg: RunConfig, positions: list[Position], brand: Brand, client: Any, result: RunResult
) -> None:
    from presidio_angellist.digest.refresh import RefreshError, make_client, refresh_content
    from presidio_angellist.llm import LLMUnavailableError

    try:
        client = client if client is not None else make_client()
    except LLMUnavailableError as exc:
        result.errors.append(f"refresh: {exc}")
        return
    terms = [*cfg.redact_terms, brand.name]
    jobs: list[tuple[Path, list[Position], str]] = []
    for v in cfg.vintages:
        jobs.append((vintage_content_path(cfg.content_dir, v), in_years(positions, v), "vintage"))
    for b in cfg.bands:
        first, last = parse_band(b)
        label = f"{first}-{last}" if last != first else str(first)
        jobs.append(
            (
                band_content_path(cfg.content_dir, label),
                in_years(positions, first, last),
                "aggregate",
            )
        )
    for path, ps, mode in jobs:
        if not ps:
            continue
        try:
            result.refreshed.append(
                refresh_content(
                    path,
                    ps,
                    mode=mode,
                    client=client,
                    model=cfg.refresh_model,
                    all_positions=positions,
                    extra_terms=terms,
                    max_searches=cfg.refresh_max_searches,
                )
            )
        except RefreshError as exc:
            result.errors.append(f"refresh {path.name}: {exc}")


def _notify(cfg: RunConfig, result: RunResult) -> None:
    from presidio_angellist.notify import NotifyError, notify_config_from_env, send_plain

    lines = [f"Digest run for {result.quarter} finished.", ""]
    lines += [f"Built: {p.name}" for p in result.pdfs]
    lines += [f"Draft written (needs review): {r.draft.name}" for r in result.refreshed]
    lines += [f"Error: {(e.splitlines() or [''])[0]}" for e in result.errors]
    lines += ["", "The PDFs are confidential and stay on the machine that built them."]
    try:
        send_plain(
            notify_config_from_env(),
            f"[angeltriage] Portfolio digest {result.quarter}",
            "\n".join(lines),
            attachments=result.pdfs if cfg.attach_pdf else (),
        )
    except NotifyError as exc:
        result.errors.append(f"notify: {exc}")
