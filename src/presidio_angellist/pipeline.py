"""
End-to-end triage pipeline: email -> Deal -> (enrich) -> Scorecard -> (memo).

This wires the four layers together with the "deterministic first, LLM fallback"
policy chosen for extraction: the regex parser runs first, and the LLM is only
called when :func:`intake.is_complete` reports the parse is too thin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from presidio_angellist.enrich.web import enrich_from_website
from presidio_angellist.intake.email import is_complete, parse_email
from presidio_angellist.llm import LLMClient, LLMUnavailableError
from presidio_angellist.models import TriageResult
from presidio_angellist.triage.memo import write_memo
from presidio_angellist.triage.rubric import score_deal

if TYPE_CHECKING:
    from pathlib import Path

    from presidio_angellist.hardening import HardenedSession

_log = logging.getLogger("presidio_angellist")


def triage_email(
    source: str | bytes | Path,
    *,
    source_name: str | None = None,
    enrich: bool = False,
    memo: bool = False,
    llm: LLMClient | None = None,
    session: HardenedSession | None = None,
    weights: dict[str, float] | None = None,
) -> TriageResult:
    """
    Triage a single forwarded syndicate email.

    Parameters
    ----------
    source:       ``.eml`` path, raw email bytes/text, or pasted body text.
    enrich:       Fetch the company website to backfill the one-liner.
    memo:         Generate an investment memo (LLM if available, else templated).
    llm:          Optional :class:`LLMClient`; enables extraction fallback + LLM memo.
    session:      Optional :class:`HardenedSession` reused for enrichment.
    weights:      Optional rubric weight overrides.
    """
    deal = parse_email(source, source_name=source_name)

    if not is_complete(deal) and llm is not None and llm.available():
        try:
            enriched = llm.extract_deal(deal.raw_text or "", source=deal.source)
            deal = enriched
            _log.info("presidio_angellist: used LLM extraction fallback for %s", deal.company)
        except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001 - keep deterministic result
            _log.warning("presidio_angellist: LLM extraction failed, keeping parse -- %s", exc)

    if enrich:
        enrich_from_website(deal, session=session)

    scorecard = score_deal(deal, weights=weights)

    memo_text = write_memo(deal, scorecard, llm=llm) if memo else None

    return TriageResult(deal=deal, scorecard=scorecard, memo=memo_text)
