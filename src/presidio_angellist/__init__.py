"""
presidio-hardened-angellist
===========================
Presidio security-hardened deal-flow triage & due-diligence toolkit for
early-stage (pre-seed / seed) startups sourced via AngelList syndicates.

The legacy AngelList Startup/Funding Data API (``api.angel.co``) is gone, so this
toolkit triages the deal flow you actually receive — forwarded syndicate emails —
rather than calling a dead API:

  1. **Intake**     parse a forwarded ``.eml`` / pasted email into a ``Deal``
  2. **Extraction** deterministic regex first; Claude fallback when fields are thin
  3. **Enrichment** fetch the company site through the hardened HTTP session
  4. **Triage**     score against a deterministic pre-seed/seed rubric
  5. **Memo**       Claude-assisted investment memo (templated fallback)

The Presidio hardening layer (TLS 1.2+, secret redaction, per-host rate limiting,
structured security logging) is retained and reused for every outbound call.

Usage
-----
    from presidio_angellist import triage_email

    result = triage_email("deal.eml", memo=True)
    print(result.scorecard.tier, result.scorecard.composite)
    print(result.memo)

CLI
---
    angeltriage deal.eml --memo
"""

from __future__ import annotations

from presidio_angellist.config import WeightsConfigError, load_rubric_config, load_weights
from presidio_angellist.enrich.web import enrich_from_website
from presidio_angellist.hardening import (
    HardenedSession,
    RateLimiter,
    SecretRedactor,
)
from presidio_angellist.intake.csv import parse_csv
from presidio_angellist.intake.email import is_complete, parse_email, read_email
from presidio_angellist.intake.imap import (
    FetchedMessage,
    ImapConfig,
    ImapError,
    fetch_imap,
    imap_config_from_env,
)
from presidio_angellist.llm import LLMClient, LLMUnavailableError
from presidio_angellist.models import (
    Deal,
    DimensionScore,
    Founder,
    Scorecard,
    TriageResult,
)
from presidio_angellist.pipeline import triage_csv, triage_deal, triage_email, triage_imap
from presidio_angellist.rubric_config import (
    DEFAULT_CAP_CEILINGS,
    DEFAULT_TIERS,
    DEFAULT_WEIGHTS,
    RubricConfig,
)
from presidio_angellist.store import STATUSES, DealStore, DealStoreError, SavedDeal
from presidio_angellist.triage.memo import write_memo
from presidio_angellist.triage.rubric import score_deal
from presidio_angellist.watch import PollResult, message_identity, poll_once, watch

__all__ = [
    # pipeline
    "triage_email",
    "triage_csv",
    "triage_deal",
    "triage_imap",
    # intake
    "parse_email",
    "read_email",
    "parse_csv",
    "fetch_imap",
    "imap_config_from_env",
    "ImapConfig",
    "ImapError",
    "FetchedMessage",
    "is_complete",
    # watch
    "watch",
    "poll_once",
    "message_identity",
    "PollResult",
    # triage
    "score_deal",
    "write_memo",
    "DEFAULT_WEIGHTS",
    "DEFAULT_CAP_CEILINGS",
    "DEFAULT_TIERS",
    "RubricConfig",
    # config
    "load_weights",
    "load_rubric_config",
    "WeightsConfigError",
    # persistence
    "DealStore",
    "SavedDeal",
    "DealStoreError",
    "STATUSES",
    # enrichment
    "enrich_from_website",
    # models
    "Deal",
    "Founder",
    "Scorecard",
    "DimensionScore",
    "TriageResult",
    # llm
    "LLMClient",
    "LLMUnavailableError",
    # hardening
    "HardenedSession",
    "SecretRedactor",
    "RateLimiter",
]

__version__ = "0.5.1"
