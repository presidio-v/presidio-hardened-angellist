"""Lightweight, hardened enrichment of a Deal from public sources."""

from __future__ import annotations

from presidio_angellist.enrich.web import enrich_from_website

__all__ = ["enrich_from_website"]
