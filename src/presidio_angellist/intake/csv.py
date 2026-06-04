"""
Batch intake: turn a CSV of deals into a list of normalized Deals.

Each row becomes one :class:`Deal`. Headers are matched case-insensitively
against a set of aliases, so exports from different trackers work without
re-mapping. Money cells accept ``$1.2M`` / ``1,200,000`` / ``500k`` forms.
"""

from __future__ import annotations

import csv as _csv
import re
from pathlib import Path

from presidio_angellist.intake.email import parse_money
from presidio_angellist.models import Deal, Founder

# Deal field -> accepted header aliases (normalized: lowercased, non-alnum -> _).
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "company": ("company", "name", "startup", "company_name"),
    "one_liner": ("one_liner", "oneliner", "description", "tagline", "summary", "pitch"),
    "sector": ("sector", "market", "vertical", "industry", "category"),
    "stage": ("stage", "round_stage"),
    "instrument": ("instrument", "security", "round_type"),
    "valuation_cap": ("valuation_cap", "cap", "valuation", "post_money_cap"),
    "round_size": ("round_size", "raising", "round", "target", "raise"),
    "allocation": ("allocation", "alloc", "syndicate_allocation"),
    "lead": ("lead", "syndicate_lead", "gp"),
    "deadline": ("deadline", "close_date", "closes", "closing"),
    "location": ("location", "hq", "city"),
    "traction": ("traction", "metrics"),
    "website": ("website", "url", "site", "link", "homepage"),
    "founders": ("founders", "founder", "team"),
    "links": ("links", "urls"),
}

_MONEY_FIELDS = ("valuation_cap", "round_size", "allocation")
_AMOUNT_RE = re.compile(r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmMbB]|thousand|million|billion)?")
_SPLIT_RE = re.compile(r"[;,]")


def parse_csv(source: str | Path) -> list[Deal]:
    """Parse a CSV file into a list of :class:`Deal`, one per non-empty row."""
    path = Path(source)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = _csv.DictReader(fh)
        # Map each Deal field to the actual header present in this CSV.
        present = {_normalize_key(h): h for h in (reader.fieldnames or [])}
        resolved = _resolve_columns(present)
        deals: list[Deal] = []
        for i, row in enumerate(reader, start=1):
            deal = _row_to_deal(row, resolved, source_name=f"{path.name}#row{i}")
            if deal is not None:
                deals.append(deal)
    return deals


def _normalize_key(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _resolve_columns(present: dict[str, str]) -> dict[str, str]:
    """Map Deal field name -> the CSV header that supplies it."""
    resolved: dict[str, str] = {}
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in present:
                resolved[field] = present[alias]
                break
    return resolved


def _cell(row: dict[str, str], resolved: dict[str, str], field: str) -> str:
    header = resolved.get(field)
    if header is None:
        return ""
    return (row.get(header) or "").strip()


def _row_to_deal(
    row: dict[str, str],
    resolved: dict[str, str],
    source_name: str,
) -> Deal | None:
    company = _cell(row, resolved, "company")
    if not company:
        return None

    deal = Deal(
        company=company,
        one_liner=_cell(row, resolved, "one_liner") or None,
        sector=_cell(row, resolved, "sector") or None,
        stage=_normalize_stage(_cell(row, resolved, "stage")),
        instrument=_cell(row, resolved, "instrument") or None,
        valuation_cap=_parse_amount(_cell(row, resolved, "valuation_cap")),
        round_size=_parse_amount(_cell(row, resolved, "round_size")),
        allocation=_parse_amount(_cell(row, resolved, "allocation")),
        lead=_cell(row, resolved, "lead") or None,
        deadline=_cell(row, resolved, "deadline") or None,
        location=_cell(row, resolved, "location") or None,
        traction=_cell(row, resolved, "traction") or None,
        website=_cell(row, resolved, "website") or None,
        founders=_parse_founders(_cell(row, resolved, "founders")),
        links=_split(_cell(row, resolved, "links")),
        source=source_name,
        extraction_method="csv",
    )
    # Give the rubric's keyword scan something to read (credentials, traction).
    deal.raw_text = " ".join(v for v in row.values() if v)
    return deal


def _normalize_stage(value: str) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "-").replace("preseed", "pre-seed")


def _parse_amount(cell: str) -> float | None:
    if not cell:
        return None
    m = _AMOUNT_RE.search(cell)
    if not m:
        return None
    return parse_money(m.group(1), m.group(2))


def _parse_founders(cell: str) -> list[Founder]:
    return [Founder(name=name) for name in _split(cell)]


def _split(cell: str) -> list[str]:
    if not cell:
        return []
    return [part.strip() for part in _SPLIT_RE.split(cell) if part.strip()]
