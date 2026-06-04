"""
Fetch a deal's company website and pull a few light signals.

All requests go through :class:`HardenedSession` so the Presidio hardening
(TLS 1.2+, HTTPS upgrade, per-host rate limiting, secret redaction) applies to
every outbound enrichment call. Failures are non-fatal -- enrichment only ever
adds to a Deal, never blocks triage.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import requests

from presidio_angellist.hardening import HardenedSession

if TYPE_CHECKING:
    from presidio_angellist.models import Deal

_log = logging.getLogger("presidio_angellist")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"\s+")


def enrich_from_website(
    deal: Deal,
    session: HardenedSession | None = None,
    timeout: float = 10.0,
) -> Deal:
    """
    Backfill ``deal.one_liner`` from the company site when it's missing.

    Tries, in order: ``<meta name="description">``, ``<meta property=
    "og:description">``, then ``<title>``. Mutates and returns ``deal``.
    """
    if not deal.website:
        return deal

    session = session or HardenedSession()
    try:
        resp = session.get(deal.website, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        _log.warning("presidio_angellist: enrichment fetch failed for %s -- %s", deal.website, exc)
        return deal

    if not resp.ok:
        _log.info("presidio_angellist: enrichment HTTP %s for %s", resp.status_code, deal.website)
        return deal

    if not deal.one_liner:
        body = resp.text
        one_liner = (
            _first_group(_META_DESC_RE, body)
            or _first_group(_OG_DESC_RE, body)
            or _first_group(_TITLE_RE, body)
        )
        if one_liner:
            deal.one_liner = one_liner
    return deal


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return _WS_RE.sub(" ", m.group(1)).strip() or None
