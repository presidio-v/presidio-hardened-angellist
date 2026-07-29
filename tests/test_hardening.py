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


class TestRedirectSSRFGuard:
    """Regression tests for the redirect-SSRF bypass (audit F-01, CWE-918).

    ``requests`` resolves redirects inside ``Session.send`` -> ``resolve_redirects``,
    which calls ``self.send()`` per hop and never re-enters ``Session.request()``.
    A guard placed only in ``request()`` validates the first hop and follows every
    subsequent attacker-chosen ``Location`` unchecked. These tests pin the guard to
    ``send()`` so each hop is validated.
    """

    @staticmethod
    def _session() -> HardenedSession:
        # A permissive rate limiter keeps the suite fast; the guard is unrelated.
        return HardenedSession(rate_limiter=RateLimiter(10_000))

    @rsps_lib.activate(assert_all_requests_are_fired=False)
    def test_redirect_to_link_local_is_refused(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://startup.example/",
            status=302,
            headers={"Location": "https://169.254.169.254/latest/meta-data/"},
        )
        rsps_lib.add(
            rsps_lib.GET,
            "https://169.254.169.254/latest/meta-data/",
            body="ami-12345",
            status=200,
        )
        with pytest.raises(SSRFError, match="169.254.169.254"):
            self._session().get("https://startup.example/", timeout=5)

    @rsps_lib.activate(assert_all_requests_are_fired=False)
    def test_redirect_to_private_range_is_refused(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://evil.example/r",
            status=302,
            headers={"Location": "https://10.0.0.5/secret"},
        )
        rsps_lib.add(rsps_lib.GET, "https://10.0.0.5/secret", body="INTERNAL", status=200)
        with pytest.raises(SSRFError, match="10.0.0.5"):
            self._session().get("https://evil.example/r", timeout=5)

    @rsps_lib.activate(assert_all_requests_are_fired=False)
    def test_redirect_to_loopback_is_refused(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://evil.example/r",
            status=302,
            headers={"Location": "https://127.0.0.1/admin"},
        )
        rsps_lib.add(rsps_lib.GET, "https://127.0.0.1/admin", body="admin", status=200)
        with pytest.raises(SSRFError, match="127.0.0.1"):
            self._session().get("https://evil.example/r", timeout=5)

    @rsps_lib.activate(assert_all_requests_are_fired=False)
    def test_multi_hop_redirect_is_refused_at_the_private_hop(self) -> None:
        """Two public hops then a private one: the guard must catch the third."""
        rsps_lib.add(
            rsps_lib.GET,
            "https://a.example/",
            status=302,
            headers={"Location": "https://b.example/"},
        )
        rsps_lib.add(
            rsps_lib.GET,
            "https://b.example/",
            status=302,
            headers={"Location": "https://192.168.1.1/internal"},
        )
        rsps_lib.add(rsps_lib.GET, "https://192.168.1.1/internal", body="LAN", status=200)
        with pytest.raises(SSRFError, match="192.168.1.1"):
            self._session().get("https://a.example/", timeout=5)

    @rsps_lib.activate
    def test_http_location_is_upgraded_not_refused(self) -> None:
        """A plaintext Location is upgraded to HTTPS, matching first-hop behaviour."""
        rsps_lib.add(
            rsps_lib.GET,
            "https://c.example/",
            status=302,
            headers={"Location": "http://d.example/x"},
        )
        rsps_lib.add(rsps_lib.GET, "https://d.example/x", body="upgraded", status=200)
        resp = self._session().get("https://c.example/", timeout=5)
        assert resp.status_code == 200
        assert resp.text == "upgraded"
        assert resp.url.startswith("https://")

    @rsps_lib.activate
    def test_public_redirect_chain_still_works(self) -> None:
        """The guard must not break legitimate redirects."""
        rsps_lib.add(
            rsps_lib.GET,
            "https://old.example/",
            status=301,
            headers={"Location": "https://new.example/"},
        )
        rsps_lib.add(rsps_lib.GET, "https://new.example/", body="moved", status=200)
        assert self._session().get("https://old.example/", timeout=5).text == "moved"

    def test_max_redirects_is_capped_well_below_the_requests_default(self) -> None:
        assert HardenedSession().max_redirects == HardenedSession.DEFAULT_MAX_REDIRECTS
        assert HardenedSession().max_redirects <= 5
        assert HardenedSession(max_redirects=2).max_redirects == 2


class TestNumericHostNormalization:
    """Audit F-08: alternative address notations must not reach the resolver."""

    @pytest.mark.parametrize(
        "host",
        ["0177.0.0.1", "0x7f.0.0.1", "2130706433", "0177.0.0.1", "017700000001"],
    )
    def test_ambiguous_numeric_hosts_are_refused(self, host: str) -> None:
        with pytest.raises(SSRFError):
            assert_public_host(host)

    @pytest.mark.parametrize("host", ["127.0.0.1%eth0", "[::1]", "::1"])
    def test_zone_ids_and_brackets_do_not_hide_loopback(self, host: str) -> None:
        with pytest.raises(SSRFError):
            assert_public_host(host)

    @pytest.mark.parametrize("host", ["1.1.1.1", "8.8.8.8"])
    def test_public_literals_still_allowed(self, host: str) -> None:
        assert_public_host(host)


class TestExpandedRedaction:
    """Audit F-04: password-bearing text must not survive a log record."""

    @pytest.mark.parametrize(
        "sample,secret",
        [
            ("password=supersecret123", "supersecret123"),
            ("IMAP_PASSWORD=hunter2", "hunter2"),
            ("ANGELTRIAGE_SMTP_PASSWORD=hunter2", "hunter2"),
            ("passwd: 'topsecret'", "topsecret"),
            ('{"pwd": "abc123"}', "abc123"),
            ("MY_TOKEN=deadbeef", "deadbeef"),
        ],
    )
    def test_password_forms_are_redacted(self, sample: str, secret: str) -> None:
        assert secret not in SecretRedactor().redact(sample)

    def test_non_secret_assignments_are_left_alone(self) -> None:
        text = "user=vladimir host=imap.example folder=INBOX"
        assert SecretRedactor().redact(text) == text
