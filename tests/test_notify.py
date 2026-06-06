"""Tests for SMTP deal notifications (SMTP mocked, no network)."""

from __future__ import annotations

import pytest

from presidio_angellist.models import Deal, DimensionScore, Scorecard, TriageResult
from presidio_angellist.notify import (
    NotifyConfig,
    NotifyError,
    build_message,
    notify_config_from_env,
    send_notifications,
)

_SMTP_ENV = {
    "ANGELTRIAGE_SMTP_HOST": "smtp.example.com",
    "ANGELTRIAGE_SMTP_PORT": "465",
    "ANGELTRIAGE_SMTP_USER": "sender@example.com",
    "ANGELTRIAGE_SMTP_PASSWORD": "secret",  # noqa: S106 - test stub
    "ANGELTRIAGE_NOTIFY_TO": "a@example.com, b@example.com",
}


def _result(company: str = "Acme") -> TriageResult:
    deal = Deal(company=company, one_liner="does things", website="https://acme.example.com")
    sc = Scorecard(
        dimensions=[DimensionScore(name="team", score=4, weight=0.2, rationale="strong")]
    )
    return TriageResult(deal=deal, scorecard=sc, memo="memo body")


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key in (
        "ANGELTRIAGE_SMTP_HOST",
        "ANGELTRIAGE_SMTP_PORT",
        "ANGELTRIAGE_SMTP_USER",
        "ANGELTRIAGE_SMTP_PASSWORD",
        "ANGELTRIAGE_SMTP_FROM",
        "ANGELTRIAGE_NOTIFY_TO",
        "ANGELTRIAGE_SMTP_STARTTLS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, val in env.items():
        monkeypatch.setenv(key, val)


class _FakeSMTP:
    """Records send_message / login calls; usable as a context manager."""

    instances: list[_FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: int = 0) -> None:
        self.host = host
        self.port = port
        self.sent: list = []
        self.logged_in: tuple | None = None
        self.started_tls = False
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, msg) -> None:
        self.sent.append(msg)


class TestConfigFromEnv:
    def test_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_env(monkeypatch, _SMTP_ENV)
        cfg = notify_config_from_env()
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 465
        assert cfg.recipients == ["a@example.com", "b@example.com"]
        assert cfg.sender == "sender@example.com"
        assert cfg.use_ssl is True

    def test_missing_host_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = dict(_SMTP_ENV)
        del env["ANGELTRIAGE_SMTP_HOST"]
        _set_env(monkeypatch, env)
        with pytest.raises(NotifyError, match="ANGELTRIAGE_SMTP_HOST"):
            notify_config_from_env()

    def test_missing_recipients_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = dict(_SMTP_ENV)
        del env["ANGELTRIAGE_NOTIFY_TO"]
        _set_env(monkeypatch, env)
        with pytest.raises(NotifyError, match="ANGELTRIAGE_NOTIFY_TO"):
            notify_config_from_env()

    def test_bad_port_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = dict(_SMTP_ENV, ANGELTRIAGE_SMTP_PORT="notaport")
        _set_env(monkeypatch, env)
        with pytest.raises(NotifyError, match="must be an integer"):
            notify_config_from_env()

    def test_starttls_flag_disables_ssl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = dict(_SMTP_ENV, ANGELTRIAGE_SMTP_PORT="587", ANGELTRIAGE_SMTP_STARTTLS="1")
        _set_env(monkeypatch, env)
        cfg = notify_config_from_env()
        assert cfg.use_ssl is False


class TestBuildMessage:
    def test_headers_and_body(self) -> None:
        cfg = NotifyConfig(host="h", port=465, sender="from@x", recipients=["a@x", "b@x"])
        msg = build_message(cfg, _result("Nimbus"))
        assert msg["To"] == "a@x, b@x"
        assert "Nimbus" in msg["Subject"]
        body = msg.get_content()
        assert "does things" in body
        assert "memo body" in body
        assert "acme.example.com" in body


class TestSendNotifications:
    def test_sends_each_via_ssl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeSMTP.instances.clear()
        monkeypatch.setattr("presidio_angellist.notify.smtplib.SMTP_SSL", _FakeSMTP)
        cfg = NotifyConfig(
            host="h",
            port=465,
            sender="from@x",
            recipients=["a@x"],
            user="u",
            password="p",  # noqa: S106 - test stub
            use_ssl=True,
        )
        sent = send_notifications(cfg, [_result("A"), _result("B")])
        assert sent == 2
        smtp = _FakeSMTP.instances[0]
        assert len(smtp.sent) == 2
        assert smtp.logged_in == ("u", "p")
        assert smtp.started_tls is False

    def test_starttls_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeSMTP.instances.clear()
        monkeypatch.setattr("presidio_angellist.notify.smtplib.SMTP", _FakeSMTP)
        cfg = NotifyConfig(host="h", port=587, sender="from@x", recipients=["a@x"], use_ssl=False)
        send_notifications(cfg, [_result("A")])
        assert _FakeSMTP.instances[0].started_tls is True

    def test_empty_is_noop(self) -> None:
        cfg = NotifyConfig(host="h", port=465, sender="from@x", recipients=["a@x"])
        assert send_notifications(cfg, []) == 0

    def test_smtp_failure_raises_notifyerror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import smtplib

        def boom(*a: object, **k: object):
            raise smtplib.SMTPException("server down")

        monkeypatch.setattr("presidio_angellist.notify.smtplib.SMTP_SSL", boom)
        cfg = NotifyConfig(host="h", port=465, sender="from@x", recipients=["a@x"])
        with pytest.raises(NotifyError, match="failed to send"):
            send_notifications(cfg, [_result("A")])
