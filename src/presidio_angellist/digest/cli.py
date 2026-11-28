"""
``angeltriage digest`` — quarterly portfolio digest subcommands.

    angeltriage digest build   --csv-dir DIR --gate-config FILE --out-dir DIR \\
                               [--vintage 2026] [--band 2017-2020] [--brand FILE] \\
                               [--content-dir DIR] [--locked-estimates FILE] [--portfolio] \\
                               [--market FILE]
    angeltriage digest refresh --csv-dir DIR --content-dir DIR [--vintage Y] \\
                               [--band A-B] [--model M]
    angeltriage digest run     --config digest.toml [--dry-run] [--no-refresh] [--no-notify]

Exit codes: 0 success; 1 one or more digests failed to build; 2 usage or config error.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from presidio_angellist.digest.build import DigestBuildError
from presidio_angellist.digest.config import (
    DigestConfigError,
    band_content_path,
    load_brand,
    parse_band,
    vintage_content_path,
)
from presidio_angellist.digest.csvload import (
    DigestDataError,
    in_years,
    load_positions,
    newest_export,
)
from presidio_angellist.digest.estimates import load_estimates
from presidio_angellist.digest.gate import GateConfigError, load_gate_config
from presidio_angellist.digest.market import load_market, market_warnings
from presidio_angellist.digest.runner import (
    Inputs,
    build_band,
    build_market,
    build_portfolio,
    build_vintage,
    current_quarter,
    estimate_warnings,
    load_run_config,
    run,
)

_CONFIG_ERRORS = (DigestConfigError, DigestDataError, GateConfigError)


def _add_source(p: argparse.ArgumentParser) -> None:
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", type=Path, help="AngelList investments export (CSV).")
    src.add_argument("--csv-dir", type=Path, help="Directory; the newest export is used.")
    p.add_argument("--vintage", type=int, action="append", default=[], help="Vintage year.")
    p.add_argument("--band", action="append", default=[], help="Band of years, e.g. 2017-2020.")
    p.add_argument("--content-dir", type=Path, default=Path("."), help="Editorial content dir.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="angeltriage digest",
        description="Quarterly portfolio digest from an AngelList investments export.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build vintage, band and portfolio PDFs.")
    _add_source(b)
    b.add_argument("--gate-config", type=Path, required=True, help="Gate config JSON.")
    b.add_argument("--brand", type=Path, default=None, help="Brand config (TOML or JSON).")
    b.add_argument("--content", type=Path, default=None, help="Content file (one target only).")
    b.add_argument("--out-dir", type=Path, required=True, help="Where PDFs are written.")
    b.add_argument("--quarter", default=None, help="e.g. 2026-Q4 (default: current quarter).")
    b.add_argument(
        "--as-of", default=None, help="As-of date (default: content as_of, else today)."
    )
    b.add_argument("--doc-version", default="1.0", help="Document version in the footer id.")
    b.add_argument("--state", default="draft", help="draft / approved, shown in the footer id.")
    b.add_argument("--keep-tex", action="store_true", help="Also write the .tex next to the PDF.")
    b.add_argument("--xelatex", default=None, help="Path to xelatex (default: auto-detect).")
    b.add_argument(
        "--locked-estimates",
        type=Path,
        default=None,
        metavar="FILE",
        help="JSON of advisor value estimates for locked positions.",
    )
    b.add_argument(
        "--market",
        type=Path,
        default=None,
        metavar="FILE",
        help="VC market benchmark JSON; also builds the Market Comparison PDF for the "
        "requested segments.",
    )
    b.add_argument(
        "--portfolio",
        action="store_true",
        help="Also build one Portfolio Digest comparing every --vintage and --band "
        "(content: portfolio.json in --content-dir).",
    )

    r = sub.add_parser("refresh", help="Draft editorial content with Claude + web search.")
    _add_source(r)
    r.add_argument("--model", default=None, help="Claude model id (default: most capable).")
    r.add_argument("--max-searches", type=int, default=5, help="Web searches per company.")
    r.add_argument(
        "--redact",
        action="append",
        default=[],
        metavar="TERM",
        help="Extra name never to send (e.g. the investor's own name). Repeatable.",
    )
    r.add_argument("--brand", type=Path, default=None, help="Brand config; its name is redacted.")

    u = sub.add_parser("run", help="Scheduled run from a private digest config.")
    u.add_argument("--config", type=Path, required=True, help="digest.toml (or .json).")
    u.add_argument("--quarter", default=None, help="Override the quarter (default: today's).")
    u.add_argument("--no-refresh", action="store_true", help="Skip the advisor refresh.")
    u.add_argument("--no-notify", action="store_true", help="Skip the notification.")
    u.add_argument("--dry-run", action="store_true", help="Print the plan and exit.")
    return p


def _err(msg: str) -> int:
    print(f"angeltriage digest: {msg}", file=sys.stderr)
    return 2


def _positions(args: argparse.Namespace):  # noqa: ANN202
    path = args.csv or newest_export(args.csv_dir)
    return path, load_positions(path)


def _cmd_build(args: argparse.Namespace) -> int:
    if not args.vintage and not args.band:
        return _err("pass at least one --vintage or --band")
    if args.content and len(args.vintage) + len(args.band) != 1:
        return _err("--content applies to a single --vintage or --band")
    try:
        _, positions = _positions(args)
        estimates = load_estimates(args.locked_estimates)
        market = load_market(args.market)
        inp = Inputs(
            positions=positions,
            gate=load_gate_config(args.gate_config),
            brand=load_brand(args.brand),
            content_dir=args.content_dir,
            out_dir=args.out_dir,
            quarter=args.quarter or current_quarter(),
            as_of=args.as_of or date.today().isoformat(),
            version=args.doc_version,
            state=args.state,
            keep_tex=args.keep_tex,
            xelatex=args.xelatex,
            as_of_override=args.as_of,
            estimates=estimates,
            market=market,
        )
        for b in args.band:
            parse_band(b)
    except _CONFIG_ERRORS as exc:
        return _err(str(exc))
    for w in estimate_warnings(estimates, positions) + market_warnings(market, positions):
        print(f"angeltriage digest: warning: {w}", file=sys.stderr)
    failed = False
    targets = [("v", v) for v in args.vintage] + [("b", b) for b in args.band]
    if args.portfolio:
        targets.append(("p", "portfolio"))
    if market is not None:
        targets.append(("m", "market"))
    for kind, target in targets:
        try:
            if kind == "v":
                out = build_vintage(inp, target, args.content)
            elif kind == "b":
                out = build_band(inp, target, args.content)
            elif kind == "p":
                out = build_portfolio(inp, args.vintage, args.band)
            else:
                out = build_market(inp, args.vintage, args.band)
            print(out)
        except (DigestBuildError, *_CONFIG_ERRORS) as exc:
            failed = True
            print(f"angeltriage digest: {target}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    from presidio_angellist.digest.refresh import RefreshError, refresh_content
    from presidio_angellist.llm import LLMUnavailableError

    if not args.vintage and not args.band:
        return _err("pass at least one --vintage or --band")
    try:
        _, positions = _positions(args)
        brand = load_brand(args.brand) if args.brand else None
        bands = [parse_band(b) for b in args.band]
    except _CONFIG_ERRORS as exc:
        return _err(str(exc))
    terms = [*args.redact, *([brand.name] if brand else [])]
    jobs = [
        (vintage_content_path(args.content_dir, v), in_years(positions, v), "vintage")
        for v in args.vintage
    ]
    for first, last in bands:
        label = f"{first}-{last}" if last != first else str(first)
        jobs.append(
            (
                band_content_path(args.content_dir, label),
                in_years(positions, first, last),
                "aggregate",
            )
        )
    rc = 0
    client = None
    for path, ps, mode in jobs:
        if not ps:
            print(f"angeltriage digest: no positions for {path.name}; skipped", file=sys.stderr)
            continue
        try:
            if client is None:
                from presidio_angellist.digest.refresh import make_client

                client = make_client()
            rep = refresh_content(
                path,
                ps,
                mode=mode,
                client=client,
                model=args.model,
                all_positions=positions,
                extra_terms=terms,
                max_searches=args.max_searches,
            )
        except (RefreshError, LLMUnavailableError) as exc:
            print(f"angeltriage digest: refresh failed: {exc}", file=sys.stderr)
            return 2
        print(f"{rep.draft}  ({len(rep.updated)} updated, {len(rep.skipped)} skipped)")
        for name, why in rep.skipped.items():
            print(f"    skipped {name}: {why}", file=sys.stderr)
            rc = 1
    return rc


def _cmd_run(args: argparse.Namespace) -> int:
    quarter = args.quarter or current_quarter()
    try:
        cfg = load_run_config(args.config, quarter)
        csv = cfg.csv or newest_export(cfg.csv_dir)  # type: ignore[arg-type]
    except _CONFIG_ERRORS as exc:
        return _err(str(exc))
    if args.dry_run:
        print(f"quarter:  {quarter}")
        print(f"csv:      {csv}")
        print(f"vintages: {', '.join(str(v) for v in cfg.vintages) or '-'}")
        print(f"bands:    {', '.join(cfg.bands) or '-'}")
        print(f"out_dir:  {cfg.out_dir}")
        print(f"refresh:  {cfg.refresh and not args.no_refresh}")
        print(f"portfolio: {cfg.portfolio}")
        print(f"locked estimates: {cfg.locked_estimates or '-'}")
        print(f"market:   {cfg.market or '-'}")
        print(f"notify:   {cfg.notify and not args.no_notify} (attach PDF: {cfg.attach_pdf})")
        return 0
    try:
        result = run(
            cfg,
            quarter,
            do_refresh=False if args.no_refresh else None,
            do_notify=False if args.no_notify else None,
        )
    except _CONFIG_ERRORS as exc:
        return _err(str(exc))
    for p in result.pdfs:
        print(p)
    for r in result.refreshed:
        print(f"draft: {r.draft}")
    for w in result.warnings:
        print(f"angeltriage digest: warning: {w}", file=sys.stderr)
    for e in result.errors:
        print(f"angeltriage digest: {e}", file=sys.stderr)
    return 1 if result.errors else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "build":
        return _cmd_build(args)
    if args.cmd == "refresh":
        return _cmd_refresh(args)
    return _cmd_run(args)
