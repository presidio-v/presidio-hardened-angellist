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

#: Hard cap on how much of an enrichment response is read into memory. The
#: signals we extract (meta description, og:description, title) live in the
#: document head, so a prefix is sufficient; a hostile site can otherwise answer
#: a multi-gigabyte body that a wall-clock timeout does not bound (CWE-400).
MAX_BODY_BYTES = 512 * 1024

#: Read granularity while enforcing the cap above.
_CHUNK_BYTES = 8192


def _read_capped(resp: requests.Response) -> str:
    """Read at most :data:`MAX_BODY_BYTES` of ``resp``, decoded to text."""
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=_CHUNK_BYTES):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_BODY_BYTES:
            _log.info(
                "presidio_angellist: enrichment body hit the %d-byte cap; scanning prefix only",
                MAX_BODY_BYTES,
            )
            break
    raw = b"".join(chunks)[:MAX_BODY_BYTES]
    return raw.decode(resp.encoding or "utf-8", errors="replace")


def enrich_from_website(
    deal: Deal,
    session: HardenedSession | None = None,
    timeout: float = 10.0,
) -> Deal:
    """
    Backfill ``deal.one_liner`` from the company site when it's missing.

    Tries, in order: ``<meta name="description">``, ``<meta property=
    "og:description">``, then ``<title>``. Mutates and returns ``deal``.

    The response is streamed and truncated at :data:`MAX_BODY_BYTES`, and only
    textual content types are scanned, so a hostile site cannot exhaust memory.
    """
    if not deal.website:
        return deal

    session = session or HardenedSession()
    try:
        resp = session.get(deal.website, timeout=timeout, stream=True)
    except requests.exceptions.RequestException as exc:
        _log.warning("presidio_angellist: enrichment fetch failed for %s -- %s", deal.website, exc)
        return deal

    try:
        if not resp.ok:
            _log.info(
                "presidio_angellist: enrichment HTTP %s for %s", resp.status_code, deal.website
            )
            return deal

        content_type = resp.headers.get("Content-Type", "").lower()
        if content_type and not any(t in content_type for t in ("html", "text", "xml")):
            _log.info(
                "presidio_angellist: skipping enrichment of non-text content (%s) for %s",
                content_type.split(";")[0],
                deal.website,
            )
            return deal

        if not deal.one_liner:
            try:
                body = _read_capped(resp)
            except requests.exceptions.RequestException as exc:
                _log.warning(
                    "presidio_angellist: enrichment body read failed for %s -- %s",
                    deal.website,
                    exc,
                )
                return deal
            one_liner = (
                _first_group(_META_DESC_RE, body)
                or _first_group(_OG_DESC_RE, body)
                or _first_group(_TITLE_RE, body)
            )
            if one_liner:
                deal.one_liner = one_liner
        return deal
    finally:
        resp.close()


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return _WS_RE.sub(" ", m.group(1)).strip() or None
