"""
SQLite-backed persistent deal queue.

Turns one-shot triage into a workflow you can work over time: triaged deals are
saved, deduped across runs, given a workflow status, and ranked. Uses the stdlib
``sqlite3`` module -- no extra dependencies.

Dedup key: the website domain (lowercased, ``www.`` stripped) when present,
otherwise the normalized company name. The same deal arriving from two syndicates
collapses to one row -- ``times_seen`` increments and the existing status is
preserved (re-triaging a ``passed`` deal will not reset it to ``new``).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from presidio_angellist.models import TriageResult

# Workflow statuses, in pipeline order.
STATUSES: tuple[str, ...] = ("new", "tracking", "passed", "committed")

_ENV_DB = "ANGELTRIAGE_DB"
_DEFAULT_DB = Path.home() / ".angeltriage" / "deals.db"

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    key            TEXT UNIQUE NOT NULL,
    company        TEXT NOT NULL,
    tier           TEXT NOT NULL,
    composite      REAL NOT NULL,
    status         TEXT NOT NULL DEFAULT 'new',
    stage          TEXT,
    instrument     TEXT,
    valuation_cap  REAL,
    lead           TEXT,
    website        TEXT,
    source         TEXT,
    deal_json      TEXT NOT NULL,
    scorecard_json TEXT NOT NULL,
    memo           TEXT,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    times_seen     INTEGER NOT NULL DEFAULT 1
);
"""


class DealStoreError(RuntimeError):
    """Raised on invalid store operations (e.g. an unknown status)."""


@dataclass
class SavedDeal:
    """A row from the deal store."""

    id: int
    key: str
    company: str
    tier: str
    composite: float
    status: str
    stage: str | None
    instrument: str | None
    valuation_cap: float | None
    lead: str | None
    website: str | None
    source: str | None
    memo: str | None
    first_seen: str
    last_seen: str
    times_seen: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "company": self.company,
            "tier": self.tier,
            "composite": self.composite,
            "status": self.status,
            "stage": self.stage,
            "instrument": self.instrument,
            "valuation_cap": self.valuation_cap,
            "lead": self.lead,
            "website": self.website,
            "source": self.source,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "times_seen": self.times_seen,
        }


def default_db_path() -> Path:
    """Resolve the store path: ``$ANGELTRIAGE_DB`` or ``~/.angeltriage/deals.db``."""
    env = os.environ.get(_ENV_DB)
    return Path(env) if env else _DEFAULT_DB


def dedup_key(company: str, website: str | None) -> str:
    """Stable identity for a deal: website domain if present, else company name."""
    if website:
        host = urlparse(website if "://" in website else f"https://{website}").netloc.lower()
        host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        if host:
            return f"domain:{host}"
    normalized = _NON_ALNUM_RE.sub(" ", company.lower()).strip()
    normalized = _WS_RE.sub(" ", normalized)
    return f"name:{normalized}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DealStore:
    """A persistent, ranked queue of triaged deals."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- context manager -------------------------------------------------

    def __enter__(self) -> DealStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # -- writes ----------------------------------------------------------

    def save(self, result: TriageResult) -> tuple[SavedDeal, bool]:
        """
        Upsert a triage result. Returns ``(saved_deal, is_new)``.

        On a dedup-key hit, refreshes the scorecard/memo and bumps ``times_seen``
        and ``last_seen`` while preserving the existing ``status`` and
        ``first_seen``.
        """
        deal = result.deal
        sc = result.scorecard
        key = dedup_key(deal.company, deal.website)
        now = _now()
        deal_json = json.dumps(deal.to_dict(), sort_keys=True)
        scorecard_json = json.dumps(sc.to_dict(), sort_keys=True)

        existing = self._conn.execute("SELECT id FROM deals WHERE key = ?", (key,)).fetchone()
        if existing is None:
            cur = self._conn.execute(
                """
                INSERT INTO deals (key, company, tier, composite, status, stage,
                    instrument, valuation_cap, lead, website, source, deal_json,
                    scorecard_json, memo, first_seen, last_seen, times_seen)
                VALUES (?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    key,
                    deal.company,
                    sc.tier,
                    sc.composite,
                    deal.stage,
                    deal.instrument,
                    deal.valuation_cap,
                    deal.lead,
                    deal.website,
                    deal.source,
                    deal_json,
                    scorecard_json,
                    result.memo,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            row_id = int(cur.lastrowid or 0)
            is_new = True
        else:
            row_id = int(existing["id"])
            self._conn.execute(
                """
                UPDATE deals SET company = ?, tier = ?, composite = ?, stage = ?,
                    instrument = ?, valuation_cap = ?, lead = ?, website = ?,
                    source = ?, deal_json = ?, scorecard_json = ?, memo = ?,
                    last_seen = ?, times_seen = times_seen + 1
                WHERE id = ?
                """,
                (
                    deal.company,
                    sc.tier,
                    sc.composite,
                    deal.stage,
                    deal.instrument,
                    deal.valuation_cap,
                    deal.lead,
                    deal.website,
                    deal.source,
                    deal_json,
                    scorecard_json,
                    result.memo,
                    now,
                    row_id,
                ),
            )
            self._conn.commit()
            is_new = False

        saved = self.get(row_id)
        assert saved is not None  # just written
        return saved, is_new

    def set_status(self, deal_id: int, status: str) -> SavedDeal:
        """Set the workflow status of a deal. Raises on unknown id or status."""
        if status not in STATUSES:
            raise DealStoreError(f"unknown status '{status}'; valid: {', '.join(STATUSES)}")
        cur = self._conn.execute("UPDATE deals SET status = ? WHERE id = ?", (status, deal_id))
        self._conn.commit()
        if cur.rowcount == 0:
            raise DealStoreError(f"no deal with id {deal_id}")
        saved = self.get(deal_id)
        assert saved is not None
        return saved

    # -- reads -----------------------------------------------------------

    def get(self, deal_id: int) -> SavedDeal | None:
        row = self._conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        return _row_to_saved(row) if row is not None else None

    def list(
        self,
        status: str | None = None,
        tier: str | None = None,
        limit: int | None = None,
    ) -> list[SavedDeal]:
        """Return deals ranked by composite (highest first), with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            if status not in STATUSES:
                raise DealStoreError(f"unknown status '{status}'; valid: {', '.join(STATUSES)}")
            clauses.append("status = ?")
            params.append(status)
        if tier is not None:
            clauses.append("tier = ?")
            params.append(tier)
        # The interpolated `where` is built only from fixed, parameterized clause
        # strings ("status = ?" / "tier = ?"); all values are bound, never
        # interpolated -- so this is not an injection vector.
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM deals {where} ORDER BY composite DESC, id ASC"  # noqa: S608
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_saved(r) for r in rows]


def _row_to_saved(row: sqlite3.Row) -> SavedDeal:
    return SavedDeal(
        id=row["id"],
        key=row["key"],
        company=row["company"],
        tier=row["tier"],
        composite=row["composite"],
        status=row["status"],
        stage=row["stage"],
        instrument=row["instrument"],
        valuation_cap=row["valuation_cap"],
        lead=row["lead"],
        website=row["website"],
        source=row["source"],
        memo=row["memo"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        times_seen=row["times_seen"],
    )
