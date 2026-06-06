"""
IMAP intake: pull deal emails from a mailbox over IMAP.

Runs wherever you run it (your laptop, a server) -- not on a phone. Credentials
come from the environment only (``IMAP_HOST`` / ``IMAP_USER`` / ``IMAP_PASSWORD``,
plus optional ``IMAP_PORT`` / ``IMAP_FOLDER`` / ``IMAP_SSL``) and are never passed
on the command line or logged. Use an app-specific password (iCloud, Gmail with
2FA), not your account password.

The folder is opened **read-only**, so fetched messages are not marked as read --
re-polling re-fetches them, and the deal store dedups by deal identity.

For testability, :func:`fetch_imap` accepts a ``connection_factory`` so tests can
inject a fake IMAP client; the default builds an ``imaplib.IMAP4_SSL``.
"""

from __future__ import annotations

import contextlib
import imaplib
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

_log = logging.getLogger("presidio_angellist")


class ImapError(RuntimeError):
    """Raised on IMAP configuration or connection/fetch failures."""


@dataclass
class ImapConfig:
    """Connection + query settings for an IMAP fetch."""

    host: str
    user: str
    password: str
    port: int = 993
    folder: str = "INBOX"
    use_ssl: bool = True
    unseen: bool = True
    from_addr: str | None = None
    since: str | None = None  # IMAP date, e.g. "01-Jun-2026"
    limit: int | None = None


@dataclass
class FetchedMessage:
    """A raw message pulled from IMAP."""

    uid: str
    raw: bytes


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off")


def imap_config_from_env(
    *,
    folder: str | None = None,
    unseen: bool = True,
    from_addr: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> ImapConfig:
    """
    Build an :class:`ImapConfig` from ``IMAP_*`` environment variables.

    Required: ``IMAP_HOST``, ``IMAP_USER``, ``IMAP_PASSWORD``. Optional:
    ``IMAP_PORT`` (default 993), ``IMAP_FOLDER`` (default ``INBOX``), ``IMAP_SSL``
    (default true). Query options (folder/unseen/from/since/limit) come from the
    caller, not the environment.

    Raises
    ------
    ImapError
        If any required credential env var is missing, or ``IMAP_PORT`` is not an
        integer.
    """
    host = os.environ.get("IMAP_HOST")
    user = os.environ.get("IMAP_USER")
    password = os.environ.get("IMAP_PASSWORD")
    missing = [
        name
        for name, val in (("IMAP_HOST", host), ("IMAP_USER", user), ("IMAP_PASSWORD", password))
        if not val
    ]
    if missing:
        raise ImapError(
            f"missing IMAP credentials: {', '.join(missing)} "
            "(set the env vars; use an app-specific password)"
        )

    raw_port = os.environ.get("IMAP_PORT")
    try:
        port = int(raw_port) if raw_port else 993
    except ValueError as exc:
        raise ImapError(f"IMAP_PORT must be an integer, got '{raw_port}'") from exc

    return ImapConfig(
        host=host,  # type: ignore[arg-type]  -- guarded by missing check above
        user=user,  # type: ignore[arg-type]
        password=password,  # type: ignore[arg-type]
        port=port,
        folder=folder or os.environ.get("IMAP_FOLDER") or "INBOX",
        use_ssl=_env_bool("IMAP_SSL", default=True),
        unseen=unseen,
        from_addr=from_addr,
        since=since,
        limit=limit,
    )


def _default_factory(config: ImapConfig) -> Callable[[], Any]:
    def make() -> Any:
        if config.use_ssl:
            return imaplib.IMAP4_SSL(config.host, config.port)
        # Plaintext IMAP would send IMAP_USER/IMAP_PASSWORD in clear over the
        # network. Refuse unless the operator explicitly opts in.
        if not _env_bool("IMAP_ALLOW_INSECURE", default=False):
            raise ImapError(
                "refusing plaintext IMAP: credentials would be sent unencrypted. "
                "Use IMAP_SSL=1 (recommended), or set IMAP_ALLOW_INSECURE=1 to override."
            )
        _log.warning(
            "presidio_angellist: connecting to %s:%s over PLAINTEXT IMAP — "
            "credentials are sent unencrypted (IMAP_ALLOW_INSECURE is set)",
            config.host,
            config.port,
        )
        return imaplib.IMAP4(config.host, config.port)

    return make


def _criteria(config: ImapConfig) -> list[str]:
    crit: list[str] = ["UNSEEN" if config.unseen else "ALL"]
    if config.from_addr:
        crit += ["FROM", config.from_addr]
    if config.since:
        crit += ["SINCE", config.since]
    return crit


def _first_rfc822(msg_data: Any) -> bytes | None:
    """Pull the raw message bytes out of imaplib's nested fetch response."""
    for part in msg_data or []:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
            return bytes(part[1])
    return None


def fetch_imap(
    config: ImapConfig,
    *,
    connection_factory: Callable[[], Any] | None = None,
) -> list[FetchedMessage]:
    """
    Fetch raw deal emails from an IMAP mailbox.

    Returns one :class:`FetchedMessage` per matching message. The folder is opened
    read-only (messages stay unread). Pass ``connection_factory`` to inject a
    client (tests); by default an ``imaplib.IMAP4_SSL`` is built from ``config``.

    Raises
    ------
    ImapError
        On connection, login, folder-select, or search failures.
    """
    make = connection_factory or _default_factory(config)
    try:
        conn = make()
    except (OSError, imaplib.IMAP4.error) as exc:
        raise ImapError(f"could not connect to {config.host}:{config.port}: {exc}") from exc

    try:
        conn.login(config.user, config.password)
        typ, _ = conn.select(config.folder, readonly=True)
        if typ != "OK":
            raise ImapError(f"could not open folder '{config.folder}'")
        typ, data = conn.search(None, *_criteria(config))
        if typ != "OK":
            raise ImapError("IMAP search failed")

        ids = data[0].split() if data and data[0] else []
        if config.limit is not None:
            ids = ids[-config.limit :]

        messages: list[FetchedMessage] = []
        for num in ids:
            typ, msg_data = conn.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            raw = _first_rfc822(msg_data)
            if raw is not None:
                uid = num.decode() if isinstance(num, (bytes, bytearray)) else str(num)
                messages.append(FetchedMessage(uid=uid, raw=raw))
        return messages
    except imaplib.IMAP4.error as exc:
        raise ImapError(f"IMAP error: {exc}") from exc
    finally:
        _safe_disconnect(conn)


def _safe_disconnect(conn: Any) -> None:
    for method in ("close", "logout"):
        with contextlib.suppress(Exception):  # best-effort teardown
            getattr(conn, method)()
