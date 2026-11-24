"""
Quarterly portfolio digest: an AngelList investments export -> branded PDF.

Two modes:

- **vintage**: one investment year, with per-company cards, entry-cap and lead
  charts, an outlook chart and a per-position gate retro-check;
- **aggregate**: a band of years (e.g. 2017-2020), with KPI tiles (TVPI, DPI,
  concentration), invested vs value by year, the multiple distribution, top
  positions, per-lead and per-thesis-bucket tables, and an aggregated gate
  retro-check ("would the gate have helped?");
- **portfolio** (``--portfolio``): every requested vintage and band side by side,
  plus a total.

Optional advisor estimates value locked positions (:mod:`estimates`).

The core is stdlib-only; the PDF is produced by an external ``xelatex`` run with
``-no-shell-escape`` in a temporary directory. Every string from the CSV, the
content JSON, the gate config or the brand config is LaTeX-escaped. Branding,
gate parameters and editorial content are supplied at runtime from private
files; the package ships only neutral examples (``contrib/digest/``).

The optional advisor refresh (:mod:`presidio_angellist.digest.refresh`, ``[llm]``
extra) sends a model only the company name, its sector and stage labels, and
scrubbed prior editorial text.
"""

from __future__ import annotations

from presidio_angellist.digest.build import DigestBuildError, compile_pdf
from presidio_angellist.digest.config import (
    Brand,
    DigestConfigError,
    load_brand,
    load_content,
)
from presidio_angellist.digest.csvload import (
    DigestDataError,
    Position,
    load_positions,
    newest_export,
    parse_positions,
)
from presidio_angellist.digest.estimates import Estimates, EstimatesError, load_estimates
from presidio_angellist.digest.gate import (
    GateConfig,
    GateConfigError,
    GateResult,
    gate_retro,
    load_gate_config,
)
from presidio_angellist.digest.metrics import AggregateMetrics, aggregate
from presidio_angellist.digest.render import (
    DocMeta,
    Segment,
    build_aggregate_tex,
    build_portfolio_tex,
    build_vintage_tex,
)

__all__ = [
    "AggregateMetrics",
    "Brand",
    "DigestBuildError",
    "DigestConfigError",
    "DigestDataError",
    "DocMeta",
    "Estimates",
    "EstimatesError",
    "GateConfig",
    "GateConfigError",
    "GateResult",
    "Position",
    "Segment",
    "aggregate",
    "build_aggregate_tex",
    "build_portfolio_tex",
    "build_vintage_tex",
    "compile_pdf",
    "gate_retro",
    "load_brand",
    "load_content",
    "load_estimates",
    "load_gate_config",
    "load_positions",
    "newest_export",
    "parse_positions",
]
