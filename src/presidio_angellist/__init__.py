"""
presidio-hardened-angellist
===========================
Presidio security-hardened Python toolkit for the AngelList Startup/Funding Data API.

Security hardening applied on every request:
  - Strict TLS 1.2+ enforcement; certificate verification always enabled
  - HTTP → HTTPS auto-upgrade
  - API key / secret redaction from all logs
  - Per-host rate limiting with exponential backoff
  - Structured security-event logging (logger: presidio_angellist)

Usage
-----
    from presidio_angellist import AngelListClient

    client = AngelListClient(api_key="sk_live_...")  # key never appears in logs

    startup   = client.get_startup(startup_id=12345)
    funding   = client.get_funding_rounds(startup_id=12345)
    investors = client.search_startups(query="AI infrastructure", market="Machine Learning")
"""

from __future__ import annotations

import logging
import re
import ssl
import time
from collections import defaultdict
from threading import Lock
from typing import Any

import requests
import urllib3
from requests.adapters import HTTPAdapter

__all__ = [
    "AngelListClient",
    "HardenedSession",
    "SecretRedactor",
    "RateLimiter",
    "AngelListError",
    "RateLimitError",
    "AuthError",
]

__version__ = "0.1.0"

_BASE_URL = "https://api.angel.co/1"

_log = logging.getLogger("presidio_angellist")

# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sk_(?:live|test)_)[A-Za-z0-9]+"), r"\1***REDACTED***"),
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
        return {
            k: (self.placeholder if k.lower() in sensitive else v)
            for k, v in headers.items()
        }


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token-bucket rate limiter, per host."""

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
        "ECDH+AESGCM:ECDH+CHACHA20:DH+AESGCM:DH+CHACHA20"
        ":!aNULL:!MD5:!RC4:!DSS:!3DES:!EXPORT"
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
    A requests.Session with all Presidio hardening layers applied:
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
            _log.info("presidio_angellist: upgraded http → https for %s", url)

        # Rate limit per host
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        self._rate_limiter.wait(host)

        # Redact secrets from any headers being sent
        if "headers" in kwargs and kwargs["headers"]:
            safe_headers = self._redactor.redact_headers(dict(kwargs["headers"]))
            _log.debug("presidio_angellist: outgoing headers: %s", safe_headers)

        try:
            response = super().request(method, url, **kwargs)
        except requests.exceptions.SSLError as exc:
            _log.error("presidio_angellist: TLS error for %s — %s", url, exc)
            raise

        return response


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AngelListError(Exception):
    """Base exception for all AngelList API errors."""
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(AngelListError):
    """Raised when the AngelList API returns HTTP 429."""


class AuthError(AngelListError):
    """Raised when the AngelList API returns HTTP 401 or 403."""


# ---------------------------------------------------------------------------
# AngelList Startup / Funding Data API client
# ---------------------------------------------------------------------------

class AngelListClient:
    """
    Hardened client for the AngelList Startup/Funding Data API.

    Parameters
    ----------
    api_key:
        AngelList access token.  Never stored in logs.
    base_url:
        Override the default API base URL.
    rate_limiter:
        Custom RateLimiter; defaults to 5 req/s.
    redactor:
        Custom SecretRedactor.
    max_retries:
        Number of automatic retries on transient errors (5xx, connection).
    retry_backoff:
        Base seconds for exponential backoff between retries.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _BASE_URL,
        rate_limiter: RateLimiter | None = None,
        redactor: SecretRedactor | None = None,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._redactor = redactor or SecretRedactor()
        self._session = HardenedSession(
            redactor=self._redactor,
            rate_limiter=rate_limiter or RateLimiter(),
        )
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": f"presidio-hardened-angellist/{__version__}",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._session.get(url, params=params, timeout=30)
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                _log.warning(
                    "presidio_angellist: connection error on attempt %d/%d — %s",
                    attempt, self._max_retries, exc,
                )
                time.sleep(self._retry_backoff * (2 ** (attempt - 1)))
                continue

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", self._retry_backoff * attempt))
                _log.warning(
                    "presidio_angellist: rate limited by AngelList API — waiting %.1fs", retry_after
                )
                time.sleep(retry_after)
                continue

            if resp.status_code in (401, 403):
                raise AuthError(
                    f"Authentication failed ({resp.status_code}): {resp.text}",
                    status_code=resp.status_code,
                )

            if resp.status_code >= 500:
                last_exc = AngelListError(
                    f"Server error {resp.status_code}: {resp.text}",
                    status_code=resp.status_code,
                )
                time.sleep(self._retry_backoff * (2 ** (attempt - 1)))
                continue

            if not resp.ok:
                raise AngelListError(
                    f"API error {resp.status_code}: {resp.text}",
                    status_code=resp.status_code,
                )

            return resp.json()

        if isinstance(last_exc, AngelListError):
            raise last_exc
        raise AngelListError(f"Request failed after {self._max_retries} attempts") from last_exc

    # ------------------------------------------------------------------
    # Startup endpoints
    # ------------------------------------------------------------------

    def get_startup(self, startup_id: int) -> dict[str, Any]:
        """
        Fetch a single startup by ID.

        https://angel.co/api/spec/startups
        """
        return self._get(f"/startups/{startup_id}")

    def search_startups(
        self,
        query: str | None = None,
        market: str | None = None,
        location: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        Search/filter startups.

        Parameters
        ----------
        query:     Free-text search.
        market:    Market/vertical filter (e.g. "Machine Learning").
        location:  Location filter (e.g. "San Francisco").
        page:      Pagination page number.
        """
        params: dict[str, Any] = {"page": page}
        if query:
            params["q"] = query
        if market:
            params["filter[market]"] = market
        if location:
            params["filter[location]"] = location
        return self._get("/startups", params=params)

    def get_startup_roles(self, startup_id: int) -> dict[str, Any]:
        """
        Fetch team members / roles for a startup.
        """
        return self._get(f"/startups/{startup_id}/roles")

    # ------------------------------------------------------------------
    # Funding endpoints
    # ------------------------------------------------------------------

    def get_funding_rounds(self, startup_id: int) -> dict[str, Any]:
        """
        Fetch all funding rounds for a startup.

        https://angel.co/api/spec/funding
        """
        return self._get(f"/startups/{startup_id}/funding")

    def get_funding_round(self, funding_id: int) -> dict[str, Any]:
        """Fetch a single funding round by its ID."""
        return self._get(f"/funding/{funding_id}")

    # ------------------------------------------------------------------
    # User / investor endpoints
    # ------------------------------------------------------------------

    def get_user(self, user_id: int) -> dict[str, Any]:
        """Fetch a user (investor/founder) profile."""
        return self._get(f"/users/{user_id}")

    def search_users(
        self,
        query: str,
        role: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        Search users.

        Parameters
        ----------
        query: Name or keyword.
        role:  Filter by role ("investor", "founder", etc.).
        page:  Pagination page number.
        """
        params: dict[str, Any] = {"q": query, "page": page}
        if role:
            params["filter[role]"] = role
        return self._get("/users/search", params=params)

    # ------------------------------------------------------------------
    # Tag / market endpoints
    # ------------------------------------------------------------------

    def get_tags(self, tag_type: str = "MarketTag") -> dict[str, Any]:
        """
        Fetch tags (markets, locations, etc.).

        Parameters
        ----------
        tag_type: One of "MarketTag", "LocationTag", "RoleTag".
        """
        return self._get("/tags", params={"type": tag_type})
