"""
Investment memo generation.

Uses the Claude-assisted memo when an :class:`LLMClient` is available, otherwise
falls back to a deterministic template built entirely from the scorecard -- so
``--memo`` produces useful output even with no API key.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from presidio_angellist.llm import LLMClient, LLMUnavailableError

if TYPE_CHECKING:
    from presidio_angellist.models import Deal, Scorecard

_log = logging.getLogger("presidio_angellist")


def write_memo(deal: Deal, scorecard: Scorecard, llm: LLMClient | None = None) -> str:
    """Return an investment memo, LLM-drafted if possible, templated otherwise."""
    if llm is not None and llm.available():
        try:
            return llm.write_memo(deal, scorecard)
        except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001 - never fail triage on memo
            _log.warning("presidio_angellist: LLM memo failed, using template -- %s", exc)
    return _template_memo(deal, scorecard)


def _template_memo(deal: Deal, scorecard: Scorecard) -> str:
    lines: list[str] = []
    lines.append(f"# Triage Memo — {deal.company}")
    lines.append("")
    if scorecard.scope_note:
        lines.append(f"> ⚠ **{scorecard.scope_note}**")
        lines.append("")
    if deal.one_liner:
        lines.append(deal.one_liner)
        lines.append("")

    lines.append(f"**Tier:** {scorecard.tier}  ·  **Composite:** {scorecard.composite}/100")
    if deal.stage or deal.instrument or deal.valuation_cap:
        bits = []
        if deal.stage:
            bits.append(deal.stage)
        if deal.instrument:
            bits.append(deal.instrument)
        if deal.valuation_cap:
            bits.append(f"${deal.valuation_cap:,.0f} cap")
        lines.append("**Terms:** " + " · ".join(bits))
    lines.append("")

    lines.append("## Scorecard")
    for d in scorecard.dimensions:
        lines.append(f"- **{d.name.title()}** — {d.score}/5 ({d.rationale})")
    lines.append("")

    if scorecard.risk_flags:
        lines.append("## Risks / Open Questions")
        for flag in scorecard.risk_flags:
            lines.append(f"- {flag}")
        lines.append("")

    lines.append("## Diligence Checklist")
    for item in _diligence_items(deal):
        lines.append(f"- [ ] {item}")
    lines.append("")

    lines.append("## Recommendation")
    lines.append(_recommendation(scorecard))
    lines.append("")
    lines.append(
        "_Generated without the LLM step (no API key). Run with `--memo` and "
        "ANTHROPIC_API_KEY set for a full qualitative memo._"
    )
    return "\n".join(lines)


def _diligence_items(deal: Deal) -> list[str]:
    items = [
        "Confirm founder backgrounds and founder–market fit",
        "Validate the market size and 'why now'",
        "Verify any stated traction (revenue, users, LOIs) with primary sources",
    ]
    if deal.valuation_cap is None:
        items.append("Obtain the round terms (cap, instrument, target size)")
    if not deal.website:
        items.append("Locate the company website / product and review it")
    if deal.lead:
        items.append(f"Diligence the syndicate lead ({deal.lead}) and their track record")
    else:
        items.append("Identify the syndicate lead and assess their track record")
    return items


def _recommendation(scorecard: Scorecard) -> str:
    tier = scorecard.tier
    if tier == "Strong lead":
        return "Strong signal — prioritize for a founder call and deeper diligence."
    if tier == "Dig deeper":
        return "Promising — worth a closer look; resolve the open questions before committing."
    if tier == "Track":
        return "Track for now — revisit if traction or terms improve."
    return "Pass — does not meet the bar at this stage on the available signal."
