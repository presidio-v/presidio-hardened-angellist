"""Tests for deterministic email intake."""

from __future__ import annotations

from pathlib import Path

from presidio_angellist.intake.email import (
    is_complete,
    parse_email,
    parse_money,
    read_email,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseMoney:
    def test_millions(self) -> None:
        assert parse_money("1.2", "M") == 1_200_000

    def test_thousands(self) -> None:
        assert parse_money("250", "k") == 250_000

    def test_billions_word(self) -> None:
        assert parse_money("2", "billion") == 2_000_000_000

    def test_plain_with_commas(self) -> None:
        assert parse_money("10,000,000", None) == 10_000_000

    def test_invalid(self) -> None:
        assert parse_money("abc", "M") is None


class TestParseCompleteEmail:
    def test_extracts_core_fields(self) -> None:
        deal = parse_email(FIXTURES / "deal_complete.eml")
        assert deal.company == "Nimbus Robotics"
        assert deal.stage == "pre-seed"
        assert deal.instrument == "SAFE"

    def test_money_fields_associate_to_right_keyword(self) -> None:
        deal = parse_email(FIXTURES / "deal_complete.eml")
        assert deal.valuation_cap == 10_000_000
        assert deal.round_size == 1_200_000
        assert deal.allocation == 250_000

    def test_extracts_lead_and_deadline(self) -> None:
        deal = parse_email(FIXTURES / "deal_complete.eml")
        assert deal.lead == "Jane Okafor"
        assert "June 16" in (deal.deadline or "")

    def test_extracts_founders_without_trailing_words(self) -> None:
        deal = parse_email(FIXTURES / "deal_complete.eml")
        names = [f.name for f in deal.founders]
        assert "Marcus Lee" in names
        assert "Priya Nair" in names
        assert all("previously" not in n for n in names)

    def test_picks_company_website_over_skip_hosts(self) -> None:
        deal = parse_email(FIXTURES / "deal_complete.eml")
        assert deal.website == "https://nimbusrobotics.example.com"

    def test_complete_deal_is_complete(self) -> None:
        assert is_complete(parse_email(FIXTURES / "deal_complete.eml")) is True

    def test_extraction_method_default(self) -> None:
        assert parse_email(FIXTURES / "deal_complete.eml").extraction_method == "deterministic"


class TestParseSparseEmail:
    def test_sparse_email_is_incomplete(self) -> None:
        deal = parse_email(FIXTURES / "deal_sparse.eml")
        assert is_complete(deal) is False

    def test_no_cap_extracted(self) -> None:
        deal = parse_email(FIXTURES / "deal_sparse.eml")
        assert deal.valuation_cap is None


class TestReadEmailFormats:
    def test_pasted_text_without_headers(self) -> None:
        subject, body = read_email("Acme builds widgets for plumbers.")
        assert subject == "Acme builds widgets for plumbers."
        assert "widgets" in body

    def test_raw_text_with_headers(self) -> None:
        raw = "Subject: Deal: Foo\nFrom: a@b.com\n\nFoo does bar. raising $500k on a SAFE."
        deal = parse_email(raw)
        assert deal.company == "Foo"
        assert deal.round_size == 500_000

    def test_bytes_source(self) -> None:
        raw = b"Subject: Bar Inc\n\nseed round, $2M cap, SAFE. https://bar.example.com"
        deal = parse_email(raw)
        assert deal.company == "Bar Inc"
        assert deal.valuation_cap == 2_000_000

    def test_html_body_is_stripped(self) -> None:
        raw = (
            "Subject: Html Co\n"
            "Content-Type: text/html\n\n"
            "<html><body><p>Html Co raises $1M seed on a SAFE.</p>"
            '<a href="https://htmlco.example.com">site</a></body></html>'
        )
        subject, body = read_email(raw)
        assert "<p>" not in body
        assert "Html Co raises" in body


class TestCompanyExtraction:
    def test_strips_forward_and_deal_prefixes(self) -> None:
        deal = parse_email("Subject: Fwd: New Deal: Zeta - the future\n\nbody $1M cap SAFE")
        assert deal.company == "Zeta"

    def test_unknown_when_no_subject_or_body(self) -> None:
        subject, body = read_email("Subject: \n\n")
        # empty subject + empty body -> Unknown company
        deal = parse_email("Subject:\n\n   ")
        assert deal.company == "Unknown"


class TestHtmlRobustness:
    def test_script_and_style_dropped_entities_decoded(self) -> None:
        raw = (
            "Subject: Html Co\n"
            "Content-Type: text/html\n\n"
            "<html><head><style>.x{color:red}</style><title>ignored</title></head>"
            "<body><script>var s=1;</script><h1>Html Co</h1>"
            "<p>Builds AI&amp;ML tools.</p><p>Raising $2M on a SAFE.</p></body></html>"
        )
        subject, body = read_email(raw)
        assert "var s" not in body
        assert "color:red" not in body
        assert "ignored" not in body
        assert "AI&ML tools" in body

    def test_html_block_tags_separate_lines(self) -> None:
        raw = (
            "Subject: X\nContent-Type: text/html\n\n"
            "<p>Acme builds widgets.</p><p>Raising $1M on a SAFE.</p>"
        )
        deal = parse_email(raw)
        assert deal.round_size == 1_000_000
