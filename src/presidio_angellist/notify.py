"""
Email notification of newly-saved deals.

When ``angeltriage`` runs with ``--notify``, each deal that is *new to the store*
this run is emailed to the configured recipients over SMTP. Configuration is
environment-only (never the command line), consistent with the IMAP / API-key
handling elsewhere:

    ANGELTRIAGE_SMTP_HOST       SMTP server host (required)
    ANGELTRIAGE_SMTP_PORT       port (default 465)
    ANGELTRIAGE_SMTP_USER       login (required for authenticated relays)
    ANGELTRIAGE_SMTP_PASSWORD   password (required for authenticated relays)
    ANGELTRIAGE_SMTP_FROM       From address (default: the SMTP user)
    ANGELTRIAGE_NOTIFY_TO       comma-separated recipient list (required)
    ANGELTRIAGE_SMTP_STARTTLS   "1" to force STARTTLS; otherwise port 465 => SSL

Failures are loud: :class:`NotifyError` propagates so an unattended run exits
non-zero rather than silently dropping a deal.
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from presidio_angellist.models import TriageResult

_log = logging.getLogger("presidio_angellist")


class NotifyError(RuntimeError):
    """Raised on notification configuration or send failure."""


@dataclass
class NotifyConfig:
    """SMTP settings + recipients for deal notifications."""

    host: str
    port: int
    sender: str
    recipients: list[str]
    user: str | None = None
    password: str | None = None
    use_ssl: bool = True


def _split_recipients(raw: str | None) -> list[str]:
    return [addr.strip() for addr in (raw or "").split(",") if addr.strip()]


def notify_config_from_env() -> NotifyConfig:
    """Build a :class:`NotifyConfig` from ``ANGELTRIAGE_SMTP_*`` / ``ANGELTRIAGE_NOTIFY_TO``.

    Raises :class:`NotifyError` if required settings (host, recipients) are absent.
    """
    host = os.environ.get("ANGELTRIAGE_SMTP_HOST")
    recipients = _split_recipients(os.environ.get("ANGELTRIAGE_NOTIFY_TO"))
    user = os.environ.get("ANGELTRIAGE_SMTP_USER")
    sender = os.environ.get("ANGELTRIAGE_SMTP_FROM") or user

    missing = [
        name
        for name, val in (
            ("ANGELTRIAGE_SMTP_HOST", host),
            ("ANGELTRIAGE_NOTIFY_TO", recipients),
            ("ANGELTRIAGE_SMTP_FROM/USER", sender),
        )
        if not val
    ]
    if missing:
        raise NotifyError(
            f"--notify is missing required config: {', '.join(missing)} "
            "(set the ANGELTRIAGE_SMTP_* / ANGELTRIAGE_NOTIFY_TO env vars)"
        )

    raw_port = os.environ.get("ANGELTRIAGE_SMTP_PORT")
    try:
        port = int(raw_port) if raw_port else 465
    except ValueError as exc:
        raise NotifyError(f"ANGELTRIAGE_SMTP_PORT must be an integer, got '{raw_port}'") from exc

    starttls = os.environ.get("ANGELTRIAGE_SMTP_STARTTLS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return NotifyConfig(
        host=host,  # type: ignore[arg-type]  -- guarded above
        port=port,
        sender=sender,  # type: ignore[arg-type]
        recipients=recipients,
        user=user,
        password=os.environ.get("ANGELTRIAGE_SMTP_PASSWORD"),
        use_ssl=not starttls and port == 465,
    )


def _format_subject(result: TriageResult) -> str:
    sc = result.scorecard
    return f"[angeltriage] New deal: {result.deal.company} — {sc.tier} · {sc.composite}/100"


def _format_body(result: TriageResult) -> str:
    deal = result.deal
    sc = result.scorecard
    lines = [f"{deal.company}  [{sc.tier} · {sc.composite}/100]"]
    if sc.scope_note:
        lines.append(f"⚠ {sc.scope_note}")
    meta = []
    if deal.stage:
        meta.append(deal.stage)
    if deal.instrument:
        meta.append(deal.instrument)
    if deal.valuation_cap:
        meta.append(f"${deal.valuation_cap:,.0f} cap")
    if deal.lead:
        meta.append(f"lead: {deal.lead}")
    if meta:
        lines.append(" · ".join(meta))
    if deal.one_liner:
        lines.append("")
        lines.append(deal.one_liner)
    lines.append("")
    lines.append("Scorecard:")
    for d in sc.dimensions:
        lines.append(f"  {d.name.title():<10} {d.score:>3}/5   {d.rationale}")
    if sc.risk_flags:
        lines.append("Risk flags:")
        for flag in sc.risk_flags:
            lines.append(f"  ⚠ {flag}")
    if deal.website:
        lines.append("")
        lines.append(f"Website: {deal.website}")
    if deal.source:
        lines.append(f"Source: {deal.source}")
    if result.memo:
        lines.append("")
        lines.append("-" * 60)
        lines.append(result.memo)
    return "\n".join(lines)


def build_message(config: NotifyConfig, result: TriageResult) -> EmailMessage:
    """Construct the notification email for one triaged deal."""
    msg = EmailMessage()
    msg["From"] = config.sender
    msg["To"] = ", ".join(config.recipients)
    msg["Subject"] = _format_subject(result)
    msg.set_content(_format_body(result))
    return msg


def send_notifications(config: NotifyConfig, results: list[TriageResult]) -> int:
    """Email each result to the configured recipients. Returns the count sent.

    Opens a single SMTP connection for the batch. Raises :class:`NotifyError` on
    any connection/auth/send failure so the caller can surface it loudly.
    """
    if not results:
        return 0
    try:
        smtp = (
            smtplib.SMTP_SSL(config.host, config.port, timeout=30)
            if config.use_ssl
            else smtplib.SMTP(config.host, config.port, timeout=30)
        )
        with smtp:
            if not config.use_ssl:
                smtp.starttls()
            if config.user and config.password:
                smtp.login(config.user, config.password)
            for result in results:
                smtp.send_message(build_message(config, result))
                _log.info(
                    "presidio_angellist: notified %d recipient(s) of deal %s",
                    len(config.recipients),
                    result.deal.company,
                )
    except (smtplib.SMTPException, OSError) as exc:
        raise NotifyError(f"failed to send deal notification(s): {exc}") from exc
    return len(results)
