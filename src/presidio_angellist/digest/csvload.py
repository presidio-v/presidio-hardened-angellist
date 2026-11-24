"""
Loader for the AngelList investments export (the "Portfolio" CSV download).

The export is not a clean CSV: the first line is a confidentiality disclaimer, the
header row starts with ``Company/Fund,``, money columns are formatted strings
(``"$1,000"``, occasionally another currency symbol), unrealized values can read
``Locked``, and caps or round sizes may be empty. This module tolerates all of
that and returns typed :class:`Position` records. It never executes or renders
anything from the file; values only populate dataclass fields.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

HEADER_PREFIX = "Company/Fund,"
_EXPORT_GLOB = "*_angellist_investments_*.csv"
_MAX_EXPORT_BYTES = 20 * 1024 * 1024
_MONEY_RE = re.compile(r"-?\d+(?:\.\d+)?")
_CURRENCY_CHARS = "$£€¥"


class DigestDataError(ValueError):
    """Raised when an investments export cannot be read."""


def parse_money(raw: str | None) -> float | None:
    """Parse ``"$1,234.50"`` -> 1234.5. ``Locked``, empty and junk -> ``None``."""
    s = (raw or "").strip()
    if not s:
        return None
    for ch in _CURRENCY_CHARS + ", ":
        s = s.replace(ch, "")
    if not _MONEY_RE.fullmatch(s):
        return None
    return float(s)


def _currency(raw: str | None) -> str:
    s = (raw or "").strip()
    for ch in _CURRENCY_CHARS:
        if ch in s:
            return {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}[ch]
    return ""


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class Position:
    """One row of the investments export."""

    name: str
    invest_date: date
    invested: float
    unrealized: float | None  # None = locked
    realized: float
    status: str = ""
    lead: str = ""
    stage: str = ""
    market: str = ""
    instrument: str = ""
    round_size: float | None = None
    cap_type: str = ""  # "Pre-money" / "Post-money" / ""
    cap: float | None = None
    cap_currency: str = ""
    discount: str = ""
    carry: str = ""
    entity: str = ""
    fund_name: str = ""
    investment_type: str = ""  # "Syndicate" / "Fund"

    @property
    def year(self) -> int:
        return self.invest_date.year

    @property
    def locked(self) -> bool:
        return self.unrealized is None

    @property
    def net(self) -> float | None:
        """Realized + unrealized; ``None`` while the mark is locked."""
        if self.unrealized is None:
            return None
        return self.realized + self.unrealized

    @property
    def net_at_cost(self) -> float:
        """Net value with a locked position carried at cost (plus any cash already paid out)."""
        net = self.net
        return self.invested + self.realized if net is None else net

    @property
    def multiple(self) -> float | None:
        net = self.net
        if net is None or not self.invested:
            return None
        return net / self.invested

    @property
    def post_cap(self) -> float | None:
        """Post-money cap. A pre-money cap counts as pre + round size."""
        if self.cap is None:
            return None
        if self.cap_type.strip().lower().startswith("pre"):
            return self.cap + (self.round_size or 0.0)
        return self.cap


def _rows_from_text(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(HEADER_PREFIX)), None)
    if start is None:
        raise DigestDataError(f"no header row starting with '{HEADER_PREFIX}' found")
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def _cell(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def parse_positions(text: str) -> list[Position]:
    """Parse the export's text into positions, oldest first. Undated rows are skipped."""
    out: list[Position] = []
    for row in _rows_from_text(text):
        name = _cell(row, "Company/Fund")
        when = _parse_date(_cell(row, "Invest Date"))
        if not name or when is None:
            continue
        out.append(
            Position(
                name=name,
                invest_date=when,
                invested=parse_money(row.get("Invested")) or 0.0,
                unrealized=parse_money(row.get("Unrealized Value")),
                realized=parse_money(row.get("Realized Value")) or 0.0,
                status=_cell(row, "Status"),
                lead=_cell(row, "Lead"),
                stage=_cell(row, "Round"),
                market=_cell(row, "Market"),
                instrument=_cell(row, "Instrument"),
                round_size=parse_money(row.get("Round Size")),
                cap_type=_cell(row, "Valuation or Cap Type"),
                cap=parse_money(row.get("Valuation or Cap")),
                cap_currency=_currency(row.get("Valuation or Cap")),
                discount=_cell(row, "Discount"),
                carry=_cell(row, "Carry"),
                entity=_cell(row, "Investment Entity"),
                fund_name=_cell(row, "Fund Name"),
                investment_type=_cell(row, "Investment Type"),
            )
        )
    return sorted(out, key=lambda p: (p.invest_date, p.name))


def load_positions(path: str | Path) -> list[Position]:
    """Read and parse an investments export from disk."""
    p = Path(path)
    if not p.is_file():
        raise DigestDataError(f"no such investments export: {p}")
    if p.stat().st_size > _MAX_EXPORT_BYTES:
        raise DigestDataError(f"investments export too large: {p}")
    return parse_positions(p.read_text(encoding="utf-8-sig"))


_EXPORT_DATE_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})\.csv$")


def _export_key(p: Path) -> tuple[str, float, str]:
    m = _EXPORT_DATE_RE.search(p.name)
    return ("".join(m.groups()) if m else "", p.stat().st_mtime, p.name)


def newest_export(csv_dir: str | Path) -> Path:
    """Newest ``*_angellist_investments_YYYY_MM_DD.csv`` in a directory.

    Ordered by the export date in the file name, then by modification time.
    """
    d = Path(csv_dir)
    found = list(d.glob(_EXPORT_GLOB)) if d.is_dir() else []
    if not found:
        raise DigestDataError(f"no AngelList investments export in {d}")
    return max(found, key=_export_key)


def in_years(positions: list[Position], first: int, last: int | None = None) -> list[Position]:
    """Positions whose invest year lies in ``[first, last]`` (inclusive)."""
    last = first if last is None else last
    return [p for p in positions if first <= p.year <= last]
