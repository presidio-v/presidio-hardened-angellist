"""Tests for hardened website enrichment."""

from __future__ import annotations

import responses as rsps_lib

from presidio_angellist.enrich.web import enrich_from_website
from presidio_angellist.models import Deal


class TestEnrich:
    def test_no_website_is_noop(self) -> None:
        deal = Deal(company="X")
        assert enrich_from_website(deal) is deal
        assert deal.one_liner is None

    @rsps_lib.activate
    def test_backfills_one_liner_from_meta_description(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://acme.example.com",
            body=(
                '<html><head><meta name="description" '
                'content="Acme builds delightful widgets."></head></html>'
            ),
            status=200,
        )
        deal = Deal(company="Acme", website="https://acme.example.com")
        enrich_from_website(deal)
        assert deal.one_liner == "Acme builds delightful widgets."

    @rsps_lib.activate
    def test_does_not_overwrite_existing_one_liner(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://acme.example.com",
            body='<meta name="description" content="from site">',
            status=200,
        )
        deal = Deal(company="Acme", website="https://acme.example.com", one_liner="from email")
        enrich_from_website(deal)
        assert deal.one_liner == "from email"

    @rsps_lib.activate
    def test_http_error_is_non_fatal(self) -> None:
        rsps_lib.add(rsps_lib.GET, "https://acme.example.com", status=500)
        deal = Deal(company="Acme", website="https://acme.example.com")
        enrich_from_website(deal)
        assert deal.one_liner is None

    @rsps_lib.activate
    def test_connection_error_is_non_fatal(self) -> None:
        import requests

        rsps_lib.add(
            rsps_lib.GET,
            "https://acme.example.com",
            body=requests.exceptions.ConnectionError("nope"),
        )
        deal = Deal(company="Acme", website="https://acme.example.com")
        enrich_from_website(deal)  # must not raise
        assert deal.one_liner is None
