"""
``angeltriage`` — command-line deal-flow triage for forwarded syndicate emails.

Examples
--------
    angeltriage deal.eml                 # scorecard for one deal
    angeltriage deal.eml --memo          # + investment memo
    angeltriage deal.eml --json          # machine-readable output
    cat deal.txt | angeltriage -         # read from stdin
    angeltriage *.eml                    # batch, ranked by composite score

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

if TYPE_CHECKING:
    from presidio_angellist.models import TriageResult


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="angeltriage",
        description="Triage forwarded AngelList/syndicate deal emails (pre-seed/seed).",
    )
    p.add_argument(
        "inputs",
        nargs="+",
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
                triage_csv(
                    source,
                    enrich=args.enrich,
                    memo=args.memo,
                    llm=llm,
                    config=config,
                )
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

    if args.json:
        payload = [r.to_dict() for r in results]
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2))
    else:
        print(_render(results))
    return 0


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
