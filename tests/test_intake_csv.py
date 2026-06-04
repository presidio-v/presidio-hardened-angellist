"""Tests for CSV batch intake."""

from __future__ import annotations

from pathlib import Path

from presidio_angellist.intake.csv import parse_csv

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseCsv:
    def test_row_count_skips_empty_company(self) -> None:
        deals = parse_csv(FIXTURES / "deals.csv")
        # 3 data rows, but the one with a blank company is skipped
        assert len(deals) == 2
        assert deals[0].company == "Nimbus Robotics"
        assert deals[1].company == "Solo Stealth"

    def test_alias_and_case_insensitive_headers(self) -> None:
        # "Valuation Cap" and "Syndicate Lead" headers map to fields
        deal = parse_csv(FIXTURES / "deals.csv")[0]
        assert deal.valuation_cap == 10_000_000
        assert deal.lead == "Jane Okafor"

    def test_money_cell_with_commas_and_suffix(self) -> None:
        deal = parse_csv(FIXTURES / "deals.csv")[0]
        assert deal.round_size == 1_200_000

    def test_founders_split_on_semicolon(self) -> None:
        deal = parse_csv(FIXTURES / "deals.csv")[0]
        assert [f.name for f in deal.founders] == ["Marcus Lee", "Priya Nair"]

    def test_stage_normalized(self) -> None:
        deal = parse_csv(FIXTURES / "deals.csv")[0]
        assert deal.stage == "pre-seed"

    def test_extraction_method_and_raw_text(self) -> None:
        deal = parse_csv(FIXTURES / "deals.csv")[0]
        assert deal.extraction_method == "csv"
        # raw_text is populated so the rubric keyword scan has something to read
        assert "MRR" in (deal.raw_text or "")

    def test_missing_optional_fields_are_none(self) -> None:
        deal = parse_csv(FIXTURES / "deals.csv")[1]  # Solo Stealth
        assert deal.valuation_cap is None
        assert deal.website is None
        assert [f.name for f in deal.founders] == ["Dana Quartz"]

    def test_tolerates_bom_and_quoted_amounts(self, tmp_path: Path) -> None:
        f = tmp_path / "b.csv"
        f.write_text('﻿company,cap\nAcme,"$5,000,000"\n', encoding="utf-8")
        deal = parse_csv(f)[0]
        assert deal.company == "Acme"
        assert deal.valuation_cap == 5_000_000
