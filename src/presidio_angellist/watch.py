"""
IMAP watch loop: poll a mailbox on an interval and auto-triage new deals.

Each cycle fetches from IMAP, triages messages not already handled **this session**
(deduped by ``Message-ID``, so the same unread email isn't re-triaged every cycle),
saves to the deal queue, and reports a summary. Across restarts the store's own
dedup prevents duplicate rows.

Designed for testability: the sleep and the IMAP connection are both injectable
(``sleeper`` / ``connection_factory``), so the loop runs in tests with no real
clock or network.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from typing import TYPE_CHECKING, Any

from presidio_angellist.intake.imap import ImapError, fetch_imap
from presidio_angellist.pipeline import triage_email

if TYPE_CHECKING:
    from collections.abc import Callable

    from presidio_angellist.intake.imap import ImapConfig
    from presidio_angellist.llm import LLMClient
    from presidio_angellist.models import TriageResult
    from presidio_angellist.rubric_config import RubricConfig
    from presidio_angellist.store import DealStore

_log = logging.getLogger("presidio_angellist")


@dataclass
class PollResult:
    """Outcome of one polling cycle."""

    fetched: int = 0
    processed: int = 0  # newly triaged this cycle (not seen earlier this session)
    new_saved: int = 0  # of those, how many were new to the store
    results: list[TriageResult] = field(default_factory=list)


def message_identity(raw: bytes) -> str:
    """Stable per-message id: the ``Message-ID`` header, else a content hash."""
    try:
        msg = message_from_bytes(raw, policy=policy.default)
        mid = msg.get("Message-ID")
        if mid:
            return str(mid).strip()
    except (ValueError, TypeError):  # pragma: no cover - defensive
        pass
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def poll_once(
    imap_config: ImapConfig,
    store: DealStore,
    *,
    seen: set[str],
    llm: LLMClient | None = None,
    config: RubricConfig | None = None,
    enrich: bool = False,
    memo: bool = False,
    connection_factory: Callable[[], Any] | None = None,
) -> PollResult:
    """Run one fetch → triage (new-only) → save cycle. Mutates ``seen``."""
    messages = fetch_imap(imap_config, connection_factory=connection_factory)
    result = PollResult(fetched=len(messages))
    for msg in messages:
        ident = message_identity(msg.raw)
        if ident in seen:
            continue
        seen.add(ident)
        triaged = triage_email(
            msg.raw,
            source_name=f"imap:{msg.uid}",
            enrich=enrich,
            memo=memo,
            llm=llm,
            config=config,
        )
        _, is_new = store.save(triaged)
        result.processed += 1
        result.new_saved += int(is_new)
        result.results.append(triaged)
    return result


def watch(
    imap_config: ImapConfig,
    store: DealStore,
    *,
    interval: float = 300.0,
    max_cycles: int = 0,
    seen: set[str] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    on_cycle: Callable[[int, PollResult], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    llm: LLMClient | None = None,
    config: RubricConfig | None = None,
    enrich: bool = False,
    memo: bool = False,
    connection_factory: Callable[[], Any] | None = None,
) -> int:
    """
    Poll the mailbox every ``interval`` seconds, triaging new deals into ``store``.

    Runs until ``max_cycles`` is reached (0 = until interrupted) or KeyboardInterrupt.
    The **first** cycle fails fast on :class:`ImapError` (catches misconfiguration);
    later cycles tolerate transient errors via ``on_error`` and keep polling.

    Returns the total number of deals newly saved to the store.
    """
    seen = seen if seen is not None else set()
    cycle = 0
    total_new = 0
    try:
        while True:
            cycle += 1
            try:
                res = poll_once(
                    imap_config,
                    store,
                    seen=seen,
                    llm=llm,
                    config=config,
                    enrich=enrich,
                    memo=memo,
                    connection_factory=connection_factory,
                )
            except ImapError as exc:
                if cycle == 1:
                    raise  # fail fast on first-cycle misconfiguration
                if on_error is not None:
                    on_error(exc)
            else:
                total_new += res.new_saved
                if on_cycle is not None:
                    on_cycle(cycle, res)

            if max_cycles and cycle >= max_cycles:
                break
            sleeper(interval)
    except KeyboardInterrupt:  # pragma: no cover - exercised interactively
        pass
    return total_new
