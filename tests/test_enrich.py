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


class TestEnrichFallbacks:
    @rsps_lib.activate
    def test_og_description_fallback(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://acme.example.com",
            body='<meta property="og:description" content="OG tagline here.">',
            status=200,
        )
        deal = Deal(company="Acme", website="https://acme.example.com")
        enrich_from_website(deal)
        assert deal.one_liner == "OG tagline here."

    @rsps_lib.activate
    def test_title_fallback(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://acme.example.com",
            body="<html><head><title>Acme — robots</title></head><body>hi</body></html>",
            status=200,
        )
        deal = Deal(company="Acme", website="https://acme.example.com")
        enrich_from_website(deal)
        assert deal.one_liner == "Acme — robots"


class TestEnrichSSRFAndBodyLimits:
    """Audit F-01 / F-02 at the consumer boundary."""

    @rsps_lib.activate(assert_all_requests_are_fired=False)
    def test_redirect_to_metadata_endpoint_leaves_deal_untouched(self) -> None:
        """A refused redirect must fail closed and stay non-fatal for triage."""
        rsps_lib.add(
            rsps_lib.GET,
            "https://startup.example/",
            status=302,
            headers={"Location": "https://169.254.169.254/latest/meta-data/"},
        )
        rsps_lib.add(
            rsps_lib.GET,
            "https://169.254.169.254/latest/meta-data/",
            body="<title>ami-12345</title>",
            status=200,
        )
        deal = Deal(company="X", website="https://startup.example/")
        assert enrich_from_website(deal) is deal
        assert deal.one_liner is None  # never populated from the internal host

    @rsps_lib.activate
    def test_oversized_body_is_truncated_not_loaded_whole(self) -> None:
        from presidio_angellist.enrich.web import MAX_BODY_BYTES

        # Title first, then far more padding than the cap allows.
        body = "<title>Capped Co</title>" + ("x" * (MAX_BODY_BYTES * 3))
        rsps_lib.add(
            rsps_lib.GET,
            "https://big.example",
            body=body,
            status=200,
            headers={"Content-Type": "text/html"},
        )
        deal = Deal(company="Big", website="https://big.example")
        enrich_from_website(deal)
        assert deal.one_liner == "Capped Co"

    @rsps_lib.activate
    def test_non_text_content_type_is_skipped(self) -> None:
        rsps_lib.add(
            rsps_lib.GET,
            "https://binary.example",
            body=b"\x00\x01\x02<title>nope</title>",
            status=200,
            headers={"Content-Type": "application/octet-stream"},
        )
        deal = Deal(company="Bin", website="https://binary.example")
        enrich_from_website(deal)
        assert deal.one_liner is None
