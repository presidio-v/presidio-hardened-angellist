"""
Presidio security-hardening primitives.

These were the heart of the original AngelList API client and remain useful as
infrastructure for every outbound enrichment call the triage tool makes:

  - Strict TLS 1.2+ enforcement; certificate verification always enabled
  - HTTP -> HTTPS auto-upgrade
  - API key / secret redaction from all logs
  - Per-host rate limiting
  - Structured security-event logging (logger: ``presidio_angellist``)
"""

from __future__ import annotations

import logging
import re
import ssl
import time
from collections import defaultdict
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

_log = logging.getLogger("presidio_angellist")

# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sk_(?:live|test)_)[A-Za-z0-9]+"), r"\1***REDACTED***"),
    (re.compile(r"(sk-ant-[A-Za-z0-9]{2,})[A-Za-z0-9\-_]+"), r"\1***REDACTED***"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1***REDACTED***"),
    (re.compile(r"(access_token=)[^&\s]+"), r"\1***REDACTED***"),
    (re.compile(r"(api_key=)[^&\s]+"), r"\1***REDACTED***"),
    (re.compile(r"(Authorization:\s*)[^\r\n]+", re.IGNORECASE), r"\1***REDACTED***"),
]


class SecretRedactor:
    """Scrubs secrets from strings before they reach any log sink."""

    def __init__(self, placeholder: str = "***REDACTED***") -> None:
        self.placeholder = placeholder

    def redact(self, text: str) -> str:
        for pattern, replacement in _SECRET_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        sensitive = {"authorization", "x-access-token", "x-api-key"}
        return {k: (self.placeholder if k.lower() in sensitive else v) for k, v in headers.items()}


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket-style rate limiter, per host."""

    def __init__(self, max_requests_per_second: float = 5.0) -> None:
        self.max_rps = max_requests_per_second
        self._locks: dict[str, Lock] = defaultdict(Lock)
        self._last_call: dict[str, float] = defaultdict(float)

    def wait(self, host: str) -> None:
        with self._locks[host]:
            elapsed = time.monotonic() - self._last_call[host]
            gap = 1.0 / self.max_rps
            if elapsed < gap:
                time.sleep(gap - elapsed)
            self._last_call[host] = time.monotonic()


# ---------------------------------------------------------------------------
# TLS hardening adapter
# ---------------------------------------------------------------------------


class _TLSHardenedAdapter(HTTPAdapter):
    """Enforce TLS 1.2+, strong ciphers, and cert verification."""

    _CIPHERS = (
        "ECDH+AESGCM:ECDH+CHACHA20:DH+AESGCM:DH+CHACHA20:!aNULL:!MD5:!RC4:!DSS:!3DES:!EXPORT"
    )

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers(self._CIPHERS)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


# ---------------------------------------------------------------------------
# HardenedSession
# ---------------------------------------------------------------------------


class HardenedSession(requests.Session):
    """
    A ``requests.Session`` with all Presidio hardening layers applied:
    TLS enforcement, HTTPS upgrade, secret redaction, rate limiting.
    """

    def __init__(
        self,
        redactor: SecretRedactor | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__()
        self._redactor = redactor or SecretRedactor()
        self._rate_limiter = rate_limiter or RateLimiter()
        self.mount("https://", _TLSHardenedAdapter())
        self.mount("http://", _TLSHardenedAdapter())  # will be upgraded below
        self.verify = True

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        # Enforce HTTPS
        if url.startswith("http://"):
            url = "https://" + url[7:]
            _log.info("presidio_angellist: upgraded http -> https for %s", url)

        # Rate limit per host
        host = urlparse(url).netloc
        self._rate_limiter.wait(host)

        # Redact secrets from any headers being sent
        if "headers" in kwargs and kwargs["headers"]:
            safe_headers = self._redactor.redact_headers(dict(kwargs["headers"]))
            _log.debug("presidio_angellist: outgoing headers: %s", safe_headers)

        try:
            response = super().request(method, url, **kwargs)
        except requests.exceptions.SSLError as exc:
            _log.error("presidio_angellist: TLS error for %s -- %s", url, exc)
            raise

        return response
