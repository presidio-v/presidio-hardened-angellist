"""
Deterministic portfolio metrics for the aggregate (band-of-years) digest.

Definitions, so the numbers in the PDF are reproducible:

- *invested*: sum of ``Invested`` over all positions in the band.
- *realized*: sum of ``Realized Value`` (cash returned) over all positions.
- *unrealized*: sum of ``Unrealized Value`` over positions that carry a mark.
- *TVPI (locked at cost)*: (net value of marked positions + cost of locked
  positions) / invested.
- *TVPI (marked only)*: net value / invested, over marked positions only.
- *DPI*: realized / invested, over all positions.
- *0x share*: positions marked at exactly zero, as a share of marked positions.
- *top-1 / top-3 share*: the largest one / three net values as a share of the
  band's total net value (locked at cost).
- *TVPI incl. locked estimates*: as "locked at cost", but a locked position with an
  advisor estimate (:mod:`estimates`) is carried at its estimated net (or gross)
  value instead of cost. Locked positions without an estimate stay at cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from presidio_angellist.digest.estimates import has_estimate, value_incl_estimates

if TYPE_CHECKING:
    from presidio_angellist.digest.csvload import Position
    from presidio_angellist.digest.estimates import Estimates
    from presidio_angellist.digest.gate import GateResult

MULTIPLE_BUCKETS = ("0x", "0-1x", "1-3x", "3-10x", ">10x", "locked")


def multiple_bucket(p: Position) -> str:
    m = p.multiple
    if m is None:
        return "locked"
    if m <= 0:
        return "0x"
    if m < 1:
        return "0-1x"
    if m < 3:
        return "1-3x"
    if m < 10:
        return "3-10x"
    return ">10x"


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


@dataclass
class Group:
    """Totals for any subset of positions (a lead, a year, a bucket, a verdict)."""

    n: int = 0
    n_marked: int = 0
    invested: float = 0.0
    invested_marked: float = 0.0
    net_marked: float = 0.0
    net_at_cost: float = 0.0
    realized: float = 0.0
    net_est: float = 0.0
    net_est_gross: float = 0.0
    n_estimated: int = 0

    def add(self, p: Position, est: Estimates | None = None) -> None:
        self.n += 1
        self.net_est += value_incl_estimates(p, est)
        self.net_est_gross += value_incl_estimates(p, est, gross=True)
        self.n_estimated += int(has_estimate(p, est))
        self.invested += p.invested
        self.realized += p.realized
        self.net_at_cost += p.net_at_cost
        if p.net is not None:
            self.n_marked += 1
            self.invested_marked += p.invested
            self.net_marked += p.net

    @property
    def tvpi(self) -> float | None:
        """TVPI with locked positions carried at cost."""
        return _ratio(self.net_at_cost, self.invested)

    @property
    def tvpi_marked(self) -> float | None:
        return _ratio(self.net_marked, self.invested_marked)

    @property
    def tvpi_est(self) -> float | None:
        """TVPI with locked positions at their estimated net value (else at cost)."""
        return _ratio(self.net_est, self.invested)

    @property
    def tvpi_est_gross(self) -> float | None:
        return _ratio(self.net_est_gross, self.invested)

    @property
    def dpi(self) -> float | None:
        return _ratio(self.realized, self.invested)

    def merge(self, other: Group) -> Group:
        out = Group()
        for f in (
            "n",
            "n_marked",
            "invested",
            "invested_marked",
            "net_marked",
            "net_at_cost",
            "realized",
            "net_est",
            "net_est_gross",
            "n_estimated",
        ):
            setattr(out, f, getattr(self, f) + getattr(other, f))
        return out


def group_by(
    positions: list[Position],
    key,  # noqa: ANN001
    est: Estimates | None = None,
) -> dict[str, Group]:
    out: dict[str, Group] = {}
    for p in positions:
        out.setdefault(key(p), Group()).add(p, est)
    return out


@dataclass
class AggregateMetrics:
    total: Group
    unrealized: float
    locked: int
    invested_locked: float
    zeros: int
    zero_share: float | None
    dpi: float | None
    top1_share: float | None
    top3_share: float | None
    by_year: dict[int, Group]
    by_bucket_multiple: dict[str, Group]
    by_lead: dict[str, Group]
    by_thesis: dict[str, Group]
    by_verdict: dict[str, Group]
    top_positions: list[Position] = field(default_factory=list)


def aggregate(
    positions: list[Position],
    gate: list[GateResult],
    *,
    top_n: int = 10,
    estimates: Estimates | None = None,
) -> AggregateMetrics:
    est = estimates
    total = Group()
    for p in positions:
        total.add(p, est)
    marked = [p for p in positions if p.net is not None]
    zeros = sum(1 for p in marked if (p.multiple or 0.0) <= 0)
    ranked = sorted(positions, key=lambda p: -p.net_at_cost)
    values = [p.net_at_cost for p in ranked]
    tot_val = sum(values)
    by_year: dict[int, Group] = {}
    for p in positions:
        by_year.setdefault(p.year, Group()).add(p, est)
    by_mult = {b: Group() for b in MULTIPLE_BUCKETS}
    for p in positions:
        by_mult[multiple_bucket(p)].add(p, est)
    by_verdict: dict[str, Group] = {v: Group() for v in ("Pass", "Borderline", "Fail")}
    by_thesis: dict[str, Group] = {}
    for p, g in zip(positions, gate, strict=True):
        by_verdict[g.verdict].add(p, est)
        by_thesis.setdefault(g.bucket, Group()).add(p, est)
    return AggregateMetrics(
        total=total,
        unrealized=sum(p.unrealized or 0.0 for p in marked),
        locked=len(positions) - len(marked),
        invested_locked=sum(p.invested for p in positions if p.net is None),
        zeros=zeros,
        zero_share=_ratio(zeros, len(marked)),
        dpi=_ratio(total.realized, total.invested),
        top1_share=_ratio(sum(values[:1]), tot_val),
        top3_share=_ratio(sum(values[:3]), tot_val),
        by_year=dict(sorted(by_year.items())),
        by_bucket_multiple=by_mult,
        by_lead=group_by(positions, lambda p: p.lead or "(no lead)", est),
        by_thesis=by_thesis,
        by_verdict=by_verdict,
        top_positions=[p for p in ranked if p.net is not None][:top_n],
    )


def gate_verdict_sentence(m: AggregateMetrics) -> str:
    """Plain-language answer to "would the gate have helped?" from the verdict groups."""
    keep = m.by_verdict["Pass"].merge(m.by_verdict["Borderline"])
    cut = m.by_verdict["Fail"]
    if not keep.n or not cut.n:
        who = "every" if not keep.n else "no"
        return (
            f"The gate would have rejected {who} position in this band, so there is no comparison."
        )
    k, c = keep.tvpi, cut.tvpi
    if k is None or c is None:
        return "Too few marked positions to compare the groups."
    if k > c * 1.1:
        verdict = "would have helped"
    elif c > k * 1.1:
        verdict = "would have hurt"
    else:
        verdict = "would have made little difference"
    return (
        f"Positions the gate keeps (pass or borderline, {keep.n}) return {k:.2f}x; the {cut.n} "
        f"it rejects return {c:.2f}x (locked at cost). On these facts the gate {verdict}."
    )
