"""
Presidio security-hardening primitives.

These were the heart of the original AngelList API client and remain useful as
infrastructure for every outbound enrichment call the triage tool makes:

  - Strict TLS 1.2+ enforcement; certificate verification always enabled
  - HTTP -> HTTPS auto-upgrade
  - SSRF guard: refuse requests to non-public (loopback/private/link-local/
    reserved) addresses, so attacker-supplied deal URLs can't reach cloud
    metadata endpoints or internal services
  - API key / secret redaction from all logs (enforced at the log sink via
    :class:`RedactingFilter`, installed on the ``presidio_angellist`` logger)
  - Retry with exponential backoff, honouring ``Retry-After`` on 429/503
  - Per-host rate limiting
  - Structured security-event logging (logger: ``presidio_angellist``)
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import ssl
import time
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    (re.compile(r"(sk-ant-)[A-Za-z0-9\-_]+"), r"\1***REDACTED***"),
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


class RedactingFilter(logging.Filter):
    """A ``logging.Filter`` that scrubs secrets from every record at the sink.

    Installed on the ``presidio_angellist`` logger at import time, so the
    "secrets are scrubbed from all log output" commitment in SECURITY.md is
    enforced for *every* log call on that logger -- not just the handful that
    redact manually. The filter mutates the already-formatted message and drops
    the args, so downstream handlers only ever see redacted text.
    """

    def __init__(self, redactor: SecretRedactor | None = None) -> None:
        super().__init__()
        self._redactor = redactor or SecretRedactor()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - never let logging crash a request
            return True
        record.msg = self._redactor.redact(message)
        record.args = None
        return True


def install_log_redaction(redactor: SecretRedactor | None = None) -> RedactingFilter:
    """Attach a :class:`RedactingFilter` to the ``presidio_angellist`` logger.

    Idempotent: a second call does not stack filters. Returns the active filter.
    """
    logger = logging.getLogger("presidio_angellist")
    for existing in logger.filters:
        if isinstance(existing, RedactingFilter):
            return existing
    flt = RedactingFilter(redactor)
    logger.addFilter(flt)
    return flt


# Enforce redaction as soon as the hardening layer is imported.
install_log_redaction()


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


class SSRFError(requests.exceptions.RequestException):
    """Raised when a request target resolves to a non-public address.

    Subclasses ``RequestException`` so callers that already treat network
    failures as non-fatal (e.g. website enrichment) handle it uniformly.
    """


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for any address an enrichment fetch must never reach."""
    if ip.version == 6 and ip.ipv4_mapped is not None:
        # ::ffff:127.0.0.1 etc. -- evaluate the embedded v4 address.
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_public_host(host: str) -> None:
    """Raise :class:`SSRFError` if ``host`` is (or resolves to) a non-public IP.

    IP literals are checked directly. Hostnames are resolved and *every*
    returned address must be public. A host that fails to resolve is allowed
    through -- there is no address to attack, and the connection will simply
    fail naturally -- which also keeps mocked tests hermetic.
    """
    if not host:
        raise SSRFError("refusing request with empty host")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise SSRFError(f"refusing request to non-public address {host}")
        return

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        _log.debug("presidio_angellist: %s did not resolve; letting the connection fail", host)
        return
    addresses = {info[4][0] for info in infos}
    for addr in addresses:
        if _is_blocked_ip(ipaddress.ip_address(addr)):
            raise SSRFError(f"refusing request to {host}: resolves to non-public address {addr}")


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

    # Ephemeral-EC suites only, matching PRESIDIO-REQ.md. Non-EC DH is excluded
    # to avoid negotiating weak/expensive finite-field DH groups.
    _CIPHERS = "ECDH+AESGCM:ECDH+CHACHA20:!aNULL:!MD5:!RC4:!DSS:!3DES:!EXPORT"

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


# Status codes worth retrying: transient server/throttling responses.
_RETRY_STATUSES = frozenset({429, 502, 503, 504})


def _retry_after_seconds(response: requests.Response) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date)."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return max(delta, 0.0)


class HardenedSession(requests.Session):
    """
    A ``requests.Session`` with all Presidio hardening layers applied:
    TLS enforcement, HTTPS upgrade, SSRF guard, secret redaction, retry with
    exponential backoff, and per-host rate limiting.
    """

    def __init__(
        self,
        redactor: SecretRedactor | None = None,
        rate_limiter: RateLimiter | None = None,
        *,
        max_retries: int = 2,
        backoff_factor: float = 0.3,
        guard_ssrf: bool = True,
    ) -> None:
        super().__init__()
        self._redactor = redactor or SecretRedactor()
        self._rate_limiter = rate_limiter or RateLimiter()
        self._max_retries = max(0, max_retries)
        self._backoff_factor = backoff_factor
        self._guard_ssrf = guard_ssrf
        self.mount("https://", _TLSHardenedAdapter())
        self.mount("http://", _TLSHardenedAdapter())  # will be upgraded below
        self.verify = True

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        # Enforce HTTPS
        if url.startswith("http://"):
            url = "https://" + url[7:]
            _log.info("presidio_angellist: upgraded http -> https for %s", url)

        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise SSRFError(f"refusing request with non-HTTPS scheme: {parsed.scheme or '(none)'}")

        # SSRF guard: never let an attacker-supplied URL reach an internal host.
        if self._guard_ssrf:
            assert_public_host(parsed.hostname or "")

        # Rate limit per host
        host = parsed.netloc
        self._rate_limiter.wait(host)

        # Redact secrets from any headers being sent
        if "headers" in kwargs and kwargs["headers"]:
            safe_headers = self._redactor.redact_headers(dict(kwargs["headers"]))
            _log.debug("presidio_angellist: outgoing headers: %s", safe_headers)

        attempt = 0
        while True:
            try:
                response = super().request(method, url, **kwargs)
            except requests.exceptions.SSLError as exc:
                _log.error("presidio_angellist: TLS error for %s -- %s", url, exc)
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt >= self._max_retries:
                    raise
                delay = self._backoff_factor * (2**attempt)
                _log.warning(
                    "presidio_angellist: %s on %s, retry %d/%d in %.2fs",
                    type(exc).__name__,
                    host,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue

            if response.status_code in _RETRY_STATUSES and attempt < self._max_retries:
                delay = _retry_after_seconds(response)
                if delay is None:
                    delay = self._backoff_factor * (2**attempt)
                _log.warning(
                    "presidio_angellist: HTTP %s on %s, retry %d/%d in %.2fs",
                    response.status_code,
                    host,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue

            return response
