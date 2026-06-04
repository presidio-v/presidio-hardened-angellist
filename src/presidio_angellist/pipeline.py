"""
End-to-end triage pipeline: Deal -> (enrich) -> Scorecard -> (memo).

Email intake adds the "deterministic first, LLM fallback" extraction policy on
top: the regex parser runs first, and the LLM is only called when
:func:`intake.is_complete` reports the parse is too thin. CSV intake feeds the
same scoring path with already-structured rows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from presidio_angellist.enrich.web import enrich_from_website
from presidio_angellist.intake.csv import parse_csv
from presidio_angellist.intake.email import is_complete, parse_email
from presidio_angellist.intake.imap import fetch_imap
from presidio_angellist.llm import LLMClient, LLMUnavailableError
from presidio_angellist.models import Deal, TriageResult
from presidio_angellist.triage.memo import write_memo
from presidio_angellist.triage.rubric import score_deal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import Any

    from presidio_angellist.hardening import HardenedSession
    from presidio_angellist.intake.imap import ImapConfig
    from presidio_angellist.rubric_config import RubricConfig

_log = logging.getLogger("presidio_angellist")


def triage_deal(
    deal: Deal,
    *,
    enrich: bool = False,
    memo: bool = False,
    llm: LLMClient | None = None,
    session: HardenedSession | None = None,
    config: RubricConfig | None = None,
    weights: dict[str, float] | None = None,
) -> TriageResult:
    """Enrich (optionally), score, and optionally write a memo for one Deal."""
    if enrich:
        enrich_from_website(deal, session=session)
    scorecard = score_deal(deal, config=config, weights=weights)
    memo_text = write_memo(deal, scorecard, llm=llm) if memo else None
    return TriageResult(deal=deal, scorecard=scorecard, memo=memo_text)


def triage_email(
    source: str | bytes | Path,
    *,
    source_name: str | None = None,
    enrich: bool = False,
    memo: bool = False,
    llm: LLMClient | None = None,
    session: HardenedSession | None = None,
    config: RubricConfig | None = None,
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
    config:       Optional :class:`RubricConfig` (weights, tiers, ceilings, penalty).
    weights:      Optional rubric weight overrides (ignored when ``config`` is set).
    """
    deal = parse_email(source, source_name=source_name)

    if not is_complete(deal) and llm is not None and llm.available():
        try:
            deal = llm.extract_deal(deal.raw_text or "", source=deal.source)
            _log.info("presidio_angellist: used LLM extraction fallback for %s", deal.company)
        except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001 - keep deterministic result
            _log.warning("presidio_angellist: LLM extraction failed, keeping parse -- %s", exc)

    return triage_deal(
        deal,
        enrich=enrich,
        memo=memo,
        llm=llm,
        session=session,
        config=config,
        weights=weights,
    )


def triage_csv(
    source: str | Path,
    *,
    enrich: bool = False,
    memo: bool = False,
    llm: LLMClient | None = None,
    session: HardenedSession | None = None,
    config: RubricConfig | None = None,
    weights: dict[str, float] | None = None,
) -> list[TriageResult]:
    """Triage every row of a CSV of deals. Returns one result per row."""
    return [
        triage_deal(
            deal,
            enrich=enrich,
            memo=memo,
            llm=llm,
            session=session,
            config=config,
            weights=weights,
        )
        for deal in parse_csv(source)
    ]


def triage_imap(
    imap_config: ImapConfig,
    *,
    enrich: bool = False,
    memo: bool = False,
    llm: LLMClient | None = None,
    session: HardenedSession | None = None,
    config: RubricConfig | None = None,
    weights: dict[str, float] | None = None,
    connection_factory: Callable[[], Any] | None = None,
) -> list[TriageResult]:
    """Fetch deal emails over IMAP and triage each. Returns one result per message."""
    messages = fetch_imap(imap_config, connection_factory=connection_factory)
    return [
        triage_email(
            msg.raw,
            source_name=f"imap:{msg.uid}",
            enrich=enrich,
            memo=memo,
            llm=llm,
            session=session,
            config=config,
            weights=weights,
        )
        for msg in messages
    ]
