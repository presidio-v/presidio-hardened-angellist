"""
``angeltriage`` — command-line deal-flow triage for forwarded syndicate emails.

Examples
--------
    angeltriage deal.eml                 # scorecard for one deal
    angeltriage deal.eml --memo          # + investment memo
    angeltriage deal.eml --json          # machine-readable output
    cat deal.txt | angeltriage -         # read from stdin
    angeltriage *.eml deals.csv          # batch (emails + CSV), ranked
    angeltriage deal.eml --save          # persist to the deal queue
    angeltriage --queue                  # show the ranked deal queue
    angeltriage --set-status 4 passed    # update a deal's workflow status

The deterministic path needs no API key. ``--memo`` and the extraction fallback
use Claude when ANTHROPIC_API_KEY is set (and the ``[llm]`` extra is installed).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from presidio_angellist import __version__
from presidio_angellist.config import WeightsConfigError, load_rubric_config, load_weights
from presidio_angellist.llm import LLMClient
from presidio_angellist.pipeline import triage_csv, triage_email
from presidio_angellist.rubric_config import RubricConfig
from presidio_angellist.store import STATUSES, DealStore, DealStoreError, default_db_path

if TYPE_CHECKING:
    from presidio_angellist.models import TriageResult


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="angeltriage",
        description="Triage forwarded AngelList/syndicate deal emails (pre-seed/seed).",
    )
    p.add_argument(
        "inputs",
        nargs="*",
        help="One or more .eml or .csv files, or '-' for stdin (treated as an email).",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    p.add_argument("--memo", action="store_true", help="Generate an investment memo.")
    p.add_argument("--enrich", action="store_true", help="Fetch the company website for signal.")
    p.add_argument("--no-llm", action="store_true", help="Disable the LLM (deterministic only).")
    p.add_argument(
        "--weights",
        metavar="FILE",
        default=None,
        help="JSON file of rubric weight overrides (dimension -> non-negative number).",
    )
    p.add_argument(
        "--rubric",
        metavar="FILE",
        default=None,
        help="JSON file of full rubric config (weights, tier_thresholds, cap_ceilings, "
        "risk_penalty). Mutually exclusive with --weights.",
    )
    p.add_argument("--model", default=None, help="Override the Claude model id.")
    # Deal queue (persistence)
    p.add_argument("--save", action="store_true", help="Persist triaged deals to the queue.")
    p.add_argument(
        "--db",
        metavar="FILE",
        default=None,
        help="Deal-queue SQLite path (default: $ANGELTRIAGE_DB or ~/.angeltriage/deals.db).",
    )
    p.add_argument("--queue", action="store_true", help="Show the ranked deal queue and exit.")
    p.add_argument("--status", metavar="STATUS", default=None, help="Filter the queue by status.")
    p.add_argument("--tier", metavar="TIER", default=None, help="Filter the queue by tier.")
    p.add_argument(
        "--set-status",
        nargs=2,
        metavar=("ID", "STATUS"),
        default=None,
        help=f"Set a deal's status ({'/'.join(STATUSES)}) and exit.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _read_stdin() -> tuple[str, str]:
    return sys.stdin.read(), "stdin"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.set_status is not None:
        return _run_set_status(args)
    if args.queue:
        return _run_queue(args)
    if not args.inputs:
        print(
            "angeltriage: nothing to do — pass input files, --queue, or --set-status",
            file=sys.stderr,
        )
        return 2
    return _run_triage(args)


# ---------------------------------------------------------------------------
# Deal-queue modes
# ---------------------------------------------------------------------------


def _db_path(args: argparse.Namespace) -> Path:
    return Path(args.db) if args.db else default_db_path()


def _run_set_status(args: argparse.Namespace) -> int:
    raw_id, status = args.set_status
    try:
        deal_id = int(raw_id)
    except ValueError:
        print(f"angeltriage: deal id must be an integer, got '{raw_id}'", file=sys.stderr)
        return 2
    with DealStore(_db_path(args)) as store:
        try:
            saved = store.set_status(deal_id, status)
        except DealStoreError as exc:
            print(f"angeltriage: {exc}", file=sys.stderr)
            return 2
    print(f"#{saved.id} {saved.company}: status -> {saved.status}")
    return 0


def _run_queue(args: argparse.Namespace) -> int:
    with DealStore(_db_path(args)) as store:
        try:
            rows = store.list(status=args.status, tier=args.tier)
        except DealStoreError as exc:
            print(f"angeltriage: {exc}", file=sys.stderr)
            return 2
    if args.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2))
    else:
        print(_render_queue(rows))
    return 0


def _render_queue(rows: list) -> str:  # list[SavedDeal]
    if not rows:
        return "(deal queue is empty)"
    out = [f"{'#':>3}  {'tier':<11}  {'score':>5}  {'status':<9}  {'seen':>4}  company"]
    for r in rows:
        out.append(
            f"{r.id:>3}  {r.tier:<11}  {r.composite:>5}  {r.status:<9}  "
            f"{r.times_seen:>4}  {r.company}"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Triage mode
# ---------------------------------------------------------------------------


def _run_triage(args: argparse.Namespace) -> int:
    if args.weights and args.rubric:
        print("angeltriage: use either --weights or --rubric, not both", file=sys.stderr)
        return 2

    config: RubricConfig | None = None
    try:
        if args.rubric:
            config = load_rubric_config(args.rubric)
        elif args.weights:
            config = RubricConfig.default()
            config.weights = load_weights(args.weights)
    except WeightsConfigError as exc:
        print(f"angeltriage: {exc}", file=sys.stderr)
        return 2

    llm = None
    if not args.no_llm:
        llm = LLMClient(model=args.model) if args.model else LLMClient()

    results: list[TriageResult] = []
    for item in args.inputs:
        if item == "-":
            text, name = _read_stdin()
            results.append(
                triage_email(
                    text,
                    source_name=name,
                    enrich=args.enrich,
                    memo=args.memo,
                    llm=llm,
                    config=config,
                )
            )
            continue

        source = Path(item)
        if not source.is_file():
            print(f"angeltriage: no such file: {item}", file=sys.stderr)
            return 2

        if source.suffix.lower() == ".csv":
            results.extend(
                triage_csv(source, enrich=args.enrich, memo=args.memo, llm=llm, config=config)
            )
        else:
            results.append(
                triage_email(
                    source,
                    source_name=item,
                    enrich=args.enrich,
                    memo=args.memo,
                    llm=llm,
                    config=config,
                )
            )

    # Rank highest-scoring first when triaging a batch.
    results.sort(key=lambda r: r.scorecard.composite, reverse=True)

    save_note = _save_results(results, args) if args.save else None

    if args.json:
        payload = [r.to_dict() for r in results]
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2))
    else:
        print(_render(results))
        if save_note:
            print("\n" + save_note)
    return 0


def _save_results(results: list[TriageResult], args: argparse.Namespace) -> str:
    db_path = _db_path(args)
    new_count = 0
    with DealStore(db_path) as store:
        for r in results:
            _, is_new = store.save(r)
            new_count += int(is_new)
    updated = len(results) - new_count
    return f"Saved {len(results)} deal(s) to {db_path} ({new_count} new, {updated} updated)."


def _render(results: list[TriageResult]) -> str:
    out: list[str] = []
    for i, r in enumerate(results):
        if i:
            out.append("\n" + "=" * 60 + "\n")
        out.append(_render_one(r))
    return "\n".join(out)


def _render_one(result: TriageResult) -> str:
    deal = result.deal
    sc = result.scorecard
    lines = [
        f"{deal.company}  [{sc.tier} · {sc.composite}/100]",
    ]
    meta = []
    if deal.stage:
        meta.append(deal.stage)
    if deal.instrument:
        meta.append(deal.instrument)
    if deal.valuation_cap:
        meta.append(f"${deal.valuation_cap:,.0f} cap")
    if deal.lead:
        meta.append(f"lead: {deal.lead}")
    if meta:
        lines.append("  " + " · ".join(meta))
    if deal.one_liner:
        lines.append(f"  {deal.one_liner}")
    lines.append("")
    lines.append("  Scorecard:")
    for d in sc.dimensions:
        lines.append(f"    {d.name.title():<10} {d.score:>3}/5   {d.rationale}")
    if sc.risk_flags:
        lines.append("  Risk flags:")
        for flag in sc.risk_flags:
            lines.append(f"    ⚠ {flag}")
    if deal.extraction_method == "llm":
        lines.append("  (fields extracted via LLM fallback)")
    if result.memo:
        lines.append("")
        lines.append(result.memo)
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
