"""Tests for AngelListClient — mocked at the HTTP layer with `responses`."""

from __future__ import annotations

import pytest
import responses as rsps_lib

from presidio_angellist import (
    AngelListClient,
    AngelListError,
    AuthError,
    RateLimitError,
    SecretRedactor,
)

API_KEY = "sk_live_TEST_KEY_REDACTED"
BASE = "https://api.angel.co/1"


@pytest.fixture()
def client() -> AngelListClient:
    return AngelListClient(api_key=API_KEY, max_retries=1)


# ---------------------------------------------------------------------------
# SecretRedactor
# ---------------------------------------------------------------------------

class TestSecretRedactor:
    def test_redacts_bearer_token(self) -> None:
        r = SecretRedactor()
        result = r.redact("Authorization: Bearer sk_live_supersecret123")
        assert "supersecret123" not in result
        assert "***REDACTED***" in result

    def test_redacts_sk_live_key(self) -> None:
        r = SecretRedactor()
        result = r.redact("key=sk_live_abc123xyz")
        assert "abc123xyz" not in result

    def test_redacts_headers_dict(self) -> None:
        r = SecretRedactor()
        safe = r.redact_headers({"Authorization": "Bearer secret", "Content-Type": "application/json"})
        assert safe["Authorization"] == "***REDACTED***"
        assert safe["Content-Type"] == "application/json"

    def test_passthrough_clean_string(self) -> None:
        r = SecretRedactor()
        assert r.redact("hello world") == "hello world"


# ---------------------------------------------------------------------------
# AngelListClient — startup endpoints
# ---------------------------------------------------------------------------

class TestGetStartup:
    @rsps_lib.activate
    def test_returns_startup_dict(self, client: AngelListClient) -> None:
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1234", json={"id": 1234, "name": "Acme"})
        result = client.get_startup(1234)
        assert result["id"] == 1234
        assert result["name"] == "Acme"

    @rsps_lib.activate
    def test_raises_auth_error_on_401(self, client: AngelListClient) -> None:
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1234", status=401, json={"error": "Unauthorized"})
        with pytest.raises(AuthError) as exc_info:
            client.get_startup(1234)
        assert exc_info.value.status_code == 401

    @rsps_lib.activate
    def test_raises_angellist_error_on_404(self, client: AngelListClient) -> None:
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/9999", status=404, json={"error": "Not found"})
        with pytest.raises(AngelListError) as exc_info:
            client.get_startup(9999)
        assert exc_info.value.status_code == 404


class TestSearchStartups:
    @rsps_lib.activate
    def test_passes_query_params(self, client: AngelListClient) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            f"{BASE}/startups",
            json={"startups": [], "total": 0},
        )
        result = client.search_startups(query="AI", market="Machine Learning", page=2)
        assert result["total"] == 0
        req = rsps_lib.calls[0].request
        assert "q=AI" in req.url
        assert "page=2" in req.url


class TestGetFundingRounds:
    @rsps_lib.activate
    def test_returns_funding_list(self, client: AngelListClient) -> None:
        payload = {"funding": [{"id": 99, "round_type": "Series A", "raised_amount": 5_000_000}]}
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1234/funding", json=payload)
        result = client.get_funding_rounds(1234)
        assert result["funding"][0]["round_type"] == "Series A"


# ---------------------------------------------------------------------------
# TLS / HTTPS hardening
# ---------------------------------------------------------------------------

class TestHTTPSUpgrade:
    @rsps_lib.activate
    def test_upgrades_http_to_https(self) -> None:
        """HTTP base URL should be silently upgraded to HTTPS."""
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1", json={"id": 1})
        # Construct client with http:// base — should still work
        c = AngelListClient(api_key=API_KEY, base_url="http://api.angel.co/1", max_retries=1)
        # responses mock intercepts https:// after the upgrade
        result = c.get_startup(1)
        assert result["id"] == 1


# ---------------------------------------------------------------------------
# Retry / error handling
# ---------------------------------------------------------------------------

class TestRetries:
    @rsps_lib.activate
    def test_raises_after_max_retries_on_500(self, client: AngelListClient) -> None:
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1", status=500, json={"error": "oops"})
        with pytest.raises(AngelListError) as exc_info:
            client.get_startup(1)
        assert exc_info.value.status_code == 500

    @rsps_lib.activate
    def test_raises_rate_limit_then_retries(self) -> None:
        # First call → 429, second → 200
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1", status=429, headers={"Retry-After": "0"})
        rsps_lib.add(rsps_lib.GET, f"{BASE}/startups/1", json={"id": 1})
        c = AngelListClient(api_key=API_KEY, max_retries=2)
        result = c.get_startup(1)
        assert result["id"] == 1
