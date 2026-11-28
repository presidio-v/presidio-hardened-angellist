"""
VC market benchmarks for the Market Comparison digest.

An operator supplies a private JSON file of published market figures (vintage TVPI
quartiles, stage round sizes and valuations, graduation rates, sector and regional
shares of dollars/deals) plus a company -> location map and editorial commentary.
Every row names a ``source`` id from the file's ``sources`` list; the PDF cites that
id under each chart or table and prints the numbered sources list at the end.

Validation fails closed (:class:`MarketError`) on an unknown source id, a share or
rate outside 0..1, quartiles out of order (p25 <= median <= p75), an unknown stage or
scope, or a malformed period. A ``company_geo`` name that is not in the export only
warns (see :func:`market_warnings`).

**Period matching.** Market periods are labels such as ``"2017-2020"``. A segment
(a vintage or a band, labelled as requested, e.g. ``"2015-2020"``) is compared with
the market period that shares the most calendar years with it; ties go to the
period whose span is closest to the segment's, then to the earlier period.

Nothing in this module touches the network; the file is a local input only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING, Any

from presidio_angellist.digest.config import (
    DigestConfigError,
    load_structured,
    parse_band,
)
from presidio_angellist.digest.latex import safe_url, short_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from presidio_angellist.digest.csvload import Position

MARKET_STAGES = ("pre-seed", "seed", "series a")
SCOPES = ("global", "US")
COMMENTARY_KEYS = ("overall", "geographic", "sectoral", "stage", "implications")
ENTRY_STAGES = ("pre-seed", "seed", "seed+", "series a", "later", "fund", "other")
US_NAMES = {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}
UNKNOWN_REGION = "Unknown"


class MarketError(DigestConfigError):
    """Raised when a market benchmark file is malformed."""


@dataclass
class Source:
    id: str
    label: str
    url: str | None = None
    period: str = ""


@dataclass
class VintageBenchmark:
    vintage: int
    p25: float
    median: float
    p75: float
    dpi_median: float | None
    source: str


@dataclass
class StageBenchmark:
    stage: str
    year: int
    region: str
    median_round: float | None
    median_post: float | None
    source: str


@dataclass
class Graduation:
    cohort: str
    from_stage: str
    to_stage: str
    window_months: int | None
    rate: float
    source: str


@dataclass
class ShareRow:
    key: str  # bucket or region
    period: str
    scope: str
    share_dollars: float | None
    share_deals: float | None
    source: str


@dataclass
class CompanyGeo:
    country: str
    region: str
    city: str = ""
    confidence: str = ""
    basis: str = ""


@dataclass
class Market:
    as_of: str = ""
    sources: list[Source] = field(default_factory=list)
    vintage_basis: str = ""
    vintages: dict[int, VintageBenchmark] = field(default_factory=dict)
    stages: list[StageBenchmark] = field(default_factory=list)
    graduation: list[Graduation] = field(default_factory=list)
    sectors: list[ShareRow] = field(default_factory=list)
    geo: list[ShareRow] = field(default_factory=list)
    company_geo: dict[str, CompanyGeo] = field(default_factory=dict)
    headline: str = ""
    commentary: dict[str, list[str]] = field(default_factory=dict)

    # ---- citations
    def source_number(self, sid: str) -> int:
        for i, s in enumerate(self.sources, 1):
            if s.id == sid:
                return i
        return 0  # pragma: no cover - ids are validated on load

    def cite(self, ids: Iterable[str]) -> str:
        """``"[1] id-a; [3] id-c"`` for the distinct ids, in list order."""
        uniq = sorted({i for i in ids if i}, key=self.source_number)
        return "; ".join(f"[{self.source_number(i)}] {i}" for i in uniq)

    # ---- lookups
    def geo_for(self, p: Position) -> CompanyGeo | None:
        hit = self.company_geo.get(p.name)
        if hit is not None:
            return hit
        key = short_name(p.name).strip().lower()
        for name, g in self.company_geo.items():
            if short_name(name).strip().lower() == key:
                return g
        return None

    def region_of(self, p: Position) -> str:
        g = self.geo_for(p)
        return g.region if g and g.region else UNKNOWN_REGION

    def stage_benchmark(self, stage: str, year: int, region: str) -> StageBenchmark | None:
        """Same stage and year; prefer the company's region, then global, then US."""
        rows = [r for r in self.stages if r.stage == stage and r.year == year]
        for want in (region, "global", "Global", "US"):
            for r in rows:
                if r.region.lower() == want.lower() and r.median_post:
                    return r
        return next((r for r in rows if r.median_post), None)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _num(v: Any, what: str, *, allow_none: bool = False) -> float | None:
    if v is None and allow_none:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise MarketError(f"market file: {what} must be a number")
    return float(v)


def _share(v: Any, what: str) -> float | None:
    x = _num(v, what, allow_none=True)
    if x is not None and not 0.0 <= x <= 1.0:
        raise MarketError(f"market file: {what} must be between 0 and 1")
    return x


def _list(data: dict, key: str) -> list:
    v = data.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
        raise MarketError(f"market file: '{key}' must be a list of objects")
    return v


def _period(v: Any) -> str:
    s = str(v or "")
    parse_period(s)
    return s


def parse_period(label: str) -> tuple[int, int]:
    try:
        return parse_band(label)
    except DigestConfigError as exc:
        raise MarketError(f"market file: bad period {label!r}") from exc


def parse_market(data: Any) -> Market:
    if not isinstance(data, dict):
        raise MarketError("market file must be a JSON object")
    m = Market(as_of=str(data.get("as_of") or ""))
    for s in _list(data, "sources"):
        sid = str(s.get("id") or "").strip()
        if not sid or any(x.id == sid for x in m.sources):
            raise MarketError("market file: every source needs a unique, non-empty id")
        m.sources.append(
            Source(
                sid, str(s.get("label") or sid), safe_url(s.get("url")), str(s.get("period") or "")
            )
        )
    ids = {s.id for s in m.sources}

    def src(row: dict, where: str) -> str:
        sid = str(row.get("source") or "")
        if sid not in ids:
            raise MarketError(f"market file: {where} cites unknown source id {sid!r}")
        return sid

    vb = data.get("vintage_benchmarks")
    vb = {} if vb is None else vb
    if not isinstance(vb, dict):
        raise MarketError("market file: 'vintage_benchmarks' must be an object")
    m.vintage_basis = str(vb.get("basis") or "")
    for r in _list(vb, "rows"):
        try:
            year = int(r.get("vintage"))
        except (TypeError, ValueError) as exc:
            raise MarketError("market file: vintage must be a year") from exc
        p25, med, p75 = (_num(r.get(k), k) for k in ("tvpi_p25", "tvpi_median", "tvpi_p75"))
        if not (0 <= p25 <= med <= p75):  # type: ignore[operator]
            raise MarketError(f"market file: vintage {year} needs 0 <= p25 <= median <= p75")
        dpi = _num(r.get("dpi_median"), "dpi_median", allow_none=True)
        if dpi is not None and dpi < 0:
            raise MarketError("market file: dpi_median must not be negative")
        m.vintages[year] = VintageBenchmark(year, p25, med, p75, dpi, src(r, f"vintage {year}"))  # type: ignore[arg-type]
    for r in _list(data, "stage_benchmarks"):
        stage = str(r.get("stage") or "").lower()
        if stage not in MARKET_STAGES:
            raise MarketError(f"market file: stage must be one of {', '.join(MARKET_STAGES)}")
        try:
            year = int(r.get("year"))
        except (TypeError, ValueError) as exc:
            raise MarketError("market file: stage benchmark year must be a year") from exc
        rnd = _num(r.get("median_round_usd"), "median_round_usd", allow_none=True)
        post = _num(r.get("median_post_money_usd"), "median_post_money_usd", allow_none=True)
        if (rnd is not None and rnd < 0) or (post is not None and post <= 0):
            raise MarketError("market file: stage medians must be positive")
        m.stages.append(
            StageBenchmark(
                stage,
                year,
                str(r.get("region") or "global"),
                rnd,
                post,
                src(r, f"stage {stage} {year}"),
            )  # fmt: skip
        )
    for r in _list(data, "graduation"):
        rate = _share(r.get("rate"), "graduation rate")
        if rate is None:
            raise MarketError("market file: graduation rate is required")
        wm = r.get("window_months")
        m.graduation.append(
            Graduation(
                str(r.get("cohort") or ""),
                str(r.get("from") or ""),
                str(r.get("to") or ""),
                int(wm) if isinstance(wm, int) and not isinstance(wm, bool) else None,
                rate,
                src(r, "graduation"),
            )
        )
    for key, coll, target in (
        ("bucket", "sector_market", m.sectors),
        ("region", "geo_market", m.geo),
    ):
        for r in _list(data, coll):
            scope = str(r.get("scope") or "global")
            if scope not in SCOPES:
                raise MarketError(f"market file: scope must be one of {', '.join(SCOPES)}")
            name = str(r.get(key) or "").strip()
            if not name:
                raise MarketError(f"market file: every {coll} row needs a {key}")
            target.append(
                ShareRow(
                    name,
                    _period(r.get("period")),
                    scope,
                    _share(r.get("share_dollars"), f"{coll} share_dollars"),
                    _share(r.get("share_deals"), f"{coll} share_deals"),
                    src(r, coll),
                )
            )
    cg = data.get("company_geo")
    cg = {} if cg is None else cg
    if not isinstance(cg, dict) or not all(isinstance(v, dict) for v in cg.values()):
        raise MarketError("market file: 'company_geo' must map names to objects")
    for name, g in cg.items():
        m.company_geo[str(name)] = CompanyGeo(
            country=str(g.get("country") or ""),
            region=str(g.get("region") or "") or UNKNOWN_REGION,
            city=str(g.get("city") or ""),
            confidence=str(g.get("confidence") or ""),
            basis=str(g.get("basis") or ""),
        )
    com = data.get("commentary")
    com = {} if com is None else com
    if not isinstance(com, dict):
        raise MarketError("market file: 'commentary' must be an object")
    m.headline = str(com.get("headline") or data.get("headline") or "")
    for k in COMMENTARY_KEYS:
        v = com.get(k, [])
        m.commentary[k] = (
            [str(x) for x in v if isinstance(x, (str, int, float))] if isinstance(v, list) else []
        )
    return m


def load_market(path: str | Path | None) -> Market | None:
    if path is None:
        return None
    return parse_market(load_structured(Path(path).expanduser()))


def market_warnings(m: Market | None, positions: list[Position]) -> list[str]:
    """Non-fatal problems: company_geo names not in the export."""
    if m is None:
        return []
    names = {p.name for p in positions}
    shorts = {short_name(n).strip().lower() for n in names}
    return [
        f"market company_geo names a company not in the export: {n}"
        for n in sorted(m.company_geo)
        if n not in names and short_name(n).strip().lower() not in shorts
    ]


# ---------------------------------------------------------------------------
# Derived figures
# ---------------------------------------------------------------------------


def best_period(periods: Iterable[str], first: int, last: int) -> str | None:
    """The period with the most calendar years in common with ``first..last``."""
    best: tuple[int, int, int, str] | None = None
    for label in set(periods):
        a, b = parse_period(label)
        overlap = max(0, min(b, last) - max(a, first) + 1)
        if not overlap:
            continue
        key = (-overlap, abs((b - a) - (last - first)), a, label)
        if best is None or key < best:
            best = key
    return best[3] if best else None


def _scope_rows(rows: list[ShareRow], period: str) -> list[ShareRow]:
    """Rows for a period, global scope preferred over US when both exist."""
    in_period = [r for r in rows if r.period == period]
    glob = [r for r in in_period if r.scope == "global"]
    return glob or in_period


def market_shares(
    rows: list[ShareRow], first: int, last: int
) -> tuple[str | None, dict[str, ShareRow]]:
    period = best_period((r.period for r in rows), first, last)
    if period is None:
        return None, {}
    return period, {r.key: r for r in _scope_rows(rows, period)}


def normalise_stage(p: Position) -> str:
    """Entry stage from the CSV Round label (and Investment Type for funds)."""
    if p.investment_type.strip().lower() == "fund":
        return "fund"
    s = re.sub(r"\s+", " ", p.stage.strip().lower())
    if s in ("pre-seed", "preseed", "pre seed"):
        return "pre-seed"
    if s == "seed":
        return "seed"
    if s in ("seed+", "seed plus", "post-seed", "seed extension"):
        return "seed+"
    if s in ("series a", "series a+", "series a extension"):
        return "series a"
    if re.match(r"series [b-z]", s) or s in ("growth", "late stage", "later"):
        return "later"
    return "other"


def benchmark_stage(stage: str) -> str | None:
    """Market stage used for an entry stage (seed+ compares with seed)."""
    return {"pre-seed": "pre-seed", "seed": "seed", "seed+": "seed", "series a": "series a"}.get(
        stage
    )


@dataclass
class EntryRatio:
    position: Position
    stage: str
    ratio: float
    benchmark: StageBenchmark


def entry_ratios(m: Market, positions: list[Position]) -> tuple[list[EntryRatio], int]:
    """Entry post-money / market median post-money (same stage and year). Returns
    (ratios, excluded) where excluded counts positions without a cap or benchmark."""
    out: list[EntryRatio] = []
    excluded = 0
    for p in positions:
        stage = normalise_stage(p)
        bstage = benchmark_stage(stage)
        pc = p.post_cap
        bench = m.stage_benchmark(bstage, p.year, m.region_of(p)) if bstage else None
        if (
            pc is None
            or bench is None
            or not bench.median_post
            or (p.cap_currency and p.cap_currency != "USD")
        ):
            excluded += 1
            continue
        out.append(EntryRatio(p, stage, pc / bench.median_post, bench))
    return out, excluded


def median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def weighted_market_tvpi(m: Market, positions: list[Position]) -> tuple[float | None, list[str]]:
    """Market median TVPI for the portfolio's vintage mix (weights: capital per year)."""
    by_year: dict[int, float] = {}
    for p in positions:
        by_year[p.year] = by_year.get(p.year, 0.0) + p.invested
    num = den = 0.0
    used: list[str] = []
    for year, inv in by_year.items():
        b = m.vintages.get(year)
        if b is None:
            continue
        num += b.median * inv
        den += inv
        used.append(b.source)
    return (num / den if den else None), used


def is_us(g: CompanyGeo | None) -> bool | None:
    if g is None:
        return None
    return g.country.strip().upper() in US_NAMES or g.region.strip().upper() in US_NAMES
