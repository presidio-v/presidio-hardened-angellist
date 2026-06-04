"""Deal intake: turn forwarded syndicate emails into normalized Deals."""

from __future__ import annotations

from presidio_angellist.intake.csv import parse_csv
from presidio_angellist.intake.email import is_complete, parse_email, read_email

__all__ = ["parse_email", "read_email", "is_complete", "parse_csv"]
