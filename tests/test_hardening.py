"""Tests for the retained Presidio hardening primitives."""

from __future__ import annotations

import logging

import pytest
import requests
import responses as rsps_lib

from presidio_angellist.hardening import (
    HardenedSession,
    RateLimiter,
    RedactingFilter,
    SecretRedactor,
    SSRFError,
    _retry_after_seconds,
    assert_public_host,
    install_log_redaction,
)


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


class TestSSRFGuard:
    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1",  # loopback
            "10.0.0.5",  # RFC1918
            "192.168.1.1",  # RFC1918
            "169.254.169.254",  # cloud metadata / link-local
            "::1",  # IPv6 loopback
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "0.0.0.0",  # unspecified  # noqa: S104
        ],
    )
    def test_blocks_non_public_ip_literals(self, host: str) -> None:
        with pytest.raises(SSRFError):
            assert_public_host(host)

    def test_allows_public_ip_literal(self) -> None:
        assert_public_host("8.8.8.8")  # must not raise

    def test_unresolvable_host_is_allowed(self) -> None:
        # No address to attack; the connection fails naturally instead.
        assert_public_host("nonexistent.invalid")

    def test_empty_host_is_refused(self) -> None:
        with pytest.raises(SSRFError):
            assert_public_host("")

    def test_session_blocks_metadata_endpoint(self) -> None:
        session = HardenedSession(rate_limiter=RateLimiter(max_requests_per_second=1000.0))
        with pytest.raises(SSRFError):
            session.get("http://169.254.169.254/latest/meta-data/", timeout=5)

    def test_session_refuses_non_https_scheme(self) -> None:
        session = HardenedSession(rate_limiter=RateLimiter(max_requests_per_second=1000.0))
        with pytest.raises(SSRFError):
            session.get("ftp://example.com/file", timeout=5)

    @rsps_lib.activate
    def test_guard_can_be_disabled(self) -> None:
        rsps_lib.add(rsps_lib.GET, "https://127.0.0.1/x", json={"ok": True})
        session = HardenedSession(
            rate_limiter=RateLimiter(max_requests_per_second=1000.0), guard_ssrf=False
        )
        assert session.get("https://127.0.0.1/x", timeout=5).json()["ok"] is True


class TestRedactingFilter:
    def test_filter_redacts_record_message(self) -> None:
        flt = RedactingFilter()
        record = logging.LogRecord(
            "presidio_angellist",
            logging.INFO,
            __file__,
            1,
            "fetching https://x/?access_token=topsecret",
            None,
            None,
        )
        flt.filter(record)
        assert "topsecret" not in record.getMessage()
        assert "***REDACTED***" in record.getMessage()

    def test_install_is_idempotent(self) -> None:
        first = install_log_redaction()
        second = install_log_redaction()
        assert first is second
        logger = logging.getLogger("presidio_angellist")
        assert sum(isinstance(f, RedactingFilter) for f in logger.filters) == 1

    def test_logger_output_is_redacted(self, caplog: pytest.LogCaptureFixture) -> None:
        install_log_redaction()
        logger = logging.getLogger("presidio_angellist")
        with caplog.at_level(logging.INFO, logger="presidio_angellist"):
            logger.info("key sk-ant-api03-DEADBEEFsecrettail used")
        assert "secrettail" not in caplog.text


class TestRetryAfter:
    def test_parses_integer_seconds(self) -> None:
        resp = requests.Response()
        resp.headers["Retry-After"] = "5"
        assert _retry_after_seconds(resp) == 5.0

    def test_parses_http_date(self) -> None:
        resp = requests.Response()
        resp.headers["Retry-After"] = "Wed, 21 Oct 2099 07:28:00 GMT"
        assert _retry_after_seconds(resp) and _retry_after_seconds(resp) > 0

    def test_none_without_header(self) -> None:
        assert _retry_after_seconds(requests.Response()) is None

    def test_garbage_header_is_none(self) -> None:
        resp = requests.Response()
        resp.headers["Retry-After"] = "soon-ish"
        assert _retry_after_seconds(resp) is None


class TestRetryBackoff:
    @rsps_lib.activate
    def test_retries_on_503_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("presidio_angellist.hardening.time.sleep", lambda _s: None)
        rsps_lib.add(rsps_lib.GET, "https://api.test/x", status=503)
        rsps_lib.add(rsps_lib.GET, "https://api.test/x", json={"ok": True}, status=200)
        session = HardenedSession(
            rate_limiter=RateLimiter(max_requests_per_second=1000.0), guard_ssrf=False
        )
        resp = session.get("https://api.test/x", timeout=5)
        assert resp.status_code == 200
        assert len(rsps_lib.calls) == 2

    @rsps_lib.activate
    def test_gives_up_after_max_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("presidio_angellist.hardening.time.sleep", lambda _s: None)
        for _ in range(5):
            rsps_lib.add(rsps_lib.GET, "https://api.test/x", status=503)
        session = HardenedSession(
            rate_limiter=RateLimiter(max_requests_per_second=1000.0),
            guard_ssrf=False,
            max_retries=2,
        )
        resp = session.get("https://api.test/x", timeout=5)
        assert resp.status_code == 503
        assert len(rsps_lib.calls) == 3  # initial + 2 retries

    @rsps_lib.activate
    def test_retries_on_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("presidio_angellist.hardening.time.sleep", lambda _s: None)
        rsps_lib.add(
            rsps_lib.GET, "https://api.test/x", body=requests.exceptions.ConnectionError("boom")
        )
        rsps_lib.add(rsps_lib.GET, "https://api.test/x", json={"ok": True}, status=200)
        session = HardenedSession(
            rate_limiter=RateLimiter(max_requests_per_second=1000.0), guard_ssrf=False
        )
        assert session.get("https://api.test/x", timeout=5).json()["ok"] is True
