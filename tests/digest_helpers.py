"""Shared fixtures for the digest tests (synthetic data only)."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "digest"
CSV = FIXTURES / "example_angellist_investments_2026_11_01.csv"
GATE = FIXTURES / "gate.json"
BRAND = FIXTURES / "brand.toml"
VINTAGE_CONTENT = FIXTURES / "vintage-2026.json"
AGG_CONTENT = FIXTURES / "agg-2017-2020.json"

HEADER = (
    "Company/Fund,Status,Invest Date,Invested,Unrealized Value,Realized Value,Net Value,"
    "Multiple,Investment Entity,Lead,Investment Type,Source,Round,Market,Fund Name,Allocation,"
    "Instrument,Round Size,Valuation or Cap Type,Valuation or Cap,Discount,Carry,Share Class"
)


def csv_text(*rows: str) -> str:
    return "Do not disclose. Example disclaimer line\n" + HEADER + "\n" + "\n".join(rows) + "\n"


def fake_xelatex(tmp: Path, *, fail: bool = False) -> str:
    """A stand-in xelatex that records its argv/env and writes d.pdf (or fails)."""
    script = tmp / "fake-xelatex"
    body = [
        f"#!{sys.executable}",
        "import json, sys",
        "open('argv.json', 'w').write(json.dumps(sys.argv[1:]))",
    ]
    if fail:
        body += [
            "open('d.log', 'w').write('! Undefined control sequence.\\nl.3 boom')",
            "sys.exit(1)",
        ]
    else:
        body += ["open('d.pdf', 'wb').write(b'%PDF-1.4 fake')"]
    script.write_text("\n".join(body) + "\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)
