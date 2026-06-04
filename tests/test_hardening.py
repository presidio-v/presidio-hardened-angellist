"""Tests for the retained Presidio hardening primitives."""

from __future__ import annotations

import responses as rsps_lib

from presidio_angellist.hardening import HardenedSession, RateLimiter, SecretRedactor


class TestSecretRedactor:
    def test_redacts_bearer_token(self) -> None:
        result = SecretRedactor().redact("Authorization: Bearer sk_live_supersecret123")
        assert "supersecret123" not in result
        assert "***REDACTED***" in result

    def test_redacts_sk_live_key(self) -> None:
        assert "abc123xyz" not in SecretRedactor().redact("key=sk_live_abc123xyz")

    def test_redacts_anthropic_key(self) -> None:
        result = SecretRedactor().redact("ANTHROPIC_API_KEY=sk-ant-api03-DEADBEEFsecrettail")
        assert "secrettail" not in result

    def test_redacts_headers_dict(self) -> None:
        safe = SecretRedactor().redact_headers(
            {"Authorization": "Bearer secret", "Content-Type": "application/json"}
        )
        assert safe["Authorization"] == "***REDACTED***"
        assert safe["Content-Type"] == "application/json"

    def test_passthrough_clean_string(self) -> None:
        assert SecretRedactor().redact("hello world") == "hello world"


class TestRateLimiter:
    def test_wait_does_not_raise(self) -> None:
        rl = RateLimiter(max_requests_per_second=1000.0)
        rl.wait("example.com")
        rl.wait("example.com")  # second call exercises the gap branch


class TestHardenedSessionHTTPSUpgrade:
    @rsps_lib.activate
    def test_http_is_upgraded_to_https(self) -> None:
        rsps_lib.add(rsps_lib.GET, "https://acme.example.com/data", json={"ok": True})
        session = HardenedSession(rate_limiter=RateLimiter(max_requests_per_second=1000.0))
        resp = session.get("http://acme.example.com/data", timeout=5)
        assert resp.json()["ok"] is True
        assert rsps_lib.calls[0].request.url.startswith("https://")
