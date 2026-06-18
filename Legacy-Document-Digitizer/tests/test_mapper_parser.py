"""
tests/test_mapper_parser.py
===========================
Unit tests for the Mapper/Parser (Piece 3).
Run with: pytest tests/ -v
"""

from __future__ import annotations

import os

# Provide required env var before importing config
os.environ.setdefault("GITHUB_TOKEN", "test_token")

import pytest
from pipeline.mapper_parser import DocumentMapper, ProcessingStatus


@pytest.fixture
def mapper() -> DocumentMapper:
    return DocumentMapper()


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_iso_passthrough(self, mapper):
        assert mapper.parse_date("2026-05-15") == "2026-05-15"

    def test_dd_mm_yyyy(self, mapper):
        assert mapper.parse_date("15/05/2026") == "2026-05-15"

    def test_dd_mm_yy(self, mapper):
        assert mapper.parse_date("15/05/26") == "2026-05-15"

    def test_dd_dot_mm_dot_yyyy(self, mapper):
        assert mapper.parse_date("15.05.2026") == "2026-05-15"

    def test_with_date_prefix(self, mapper):
        assert mapper.parse_date("Date: 15/05/2026") == "2026-05-15"

    def test_month_name(self, mapper):
        assert mapper.parse_date("15 May 2026") == "2026-05-15"

    def test_invalid_returns_none(self, mapper):
        assert mapper.parse_date("not a date") is None

    def test_none_returns_none(self, mapper):
        assert mapper.parse_date(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_amount
# ---------------------------------------------------------------------------

class TestParseAmount:
    def test_plain_float(self, mapper):
        assert mapper.parse_amount("1234.56") == 1234.56

    def test_with_inr_prefix(self, mapper):
        assert mapper.parse_amount("INR 1,234.56") == 1234.56

    def test_with_rupee_symbol(self, mapper):
        assert mapper.parse_amount("₹86,262.86") == 86262.86

    def test_comma_thousands(self, mapper):
        assert mapper.parse_amount("1,00,000.00") == 100000.0

    def test_none_returns_none(self, mapper):
        assert mapper.parse_amount(None) is None  # type: ignore[arg-type]

    def test_empty_string(self, mapper):
        assert mapper.parse_amount("") is None

    def test_non_numeric(self, mapper):
        assert mapper.parse_amount("N/A") is None


# ---------------------------------------------------------------------------
# validate_math
# ---------------------------------------------------------------------------

class TestValidateMath:
    def test_pass_with_cgst_sgst(self, mapper):
        normalised = {
            "base_amount": 1000.0,
            "cgst_amount": 90.0,
            "sgst_amount": 90.0,
            "igst_amount": None,
            "total_invoice_amount": 1180.0,
        }
        ok, detail = mapper._validate_math(normalised)
        assert ok, detail

    def test_fail_wrong_total(self, mapper):
        normalised = {
            "base_amount": 1000.0,
            "cgst_amount": 90.0,
            "sgst_amount": 90.0,
            "igst_amount": None,
            "total_invoice_amount": 1000.0,  # wrong
        }
        ok, _ = mapper._validate_math(normalised)
        assert not ok

    def test_missing_total(self, mapper):
        ok, detail = mapper._validate_math({"base_amount": 100.0, "total_invoice_amount": None})
        assert not ok

    def test_zero_tax_pass(self, mapper):
        normalised = {
            "base_amount": 500.0,
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": None,
            "total_invoice_amount": 500.0,
        }
        ok, detail = mapper._validate_math(normalised)
        assert ok

    def test_igst_only(self, mapper):
        normalised = {
            "base_amount": 1000.0,
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": 180.0,
            "total_invoice_amount": 1180.0,
        }
        ok, detail = mapper._validate_math(normalised)
        assert ok, detail


# ---------------------------------------------------------------------------
# Full process_document (no model call needed)
# ---------------------------------------------------------------------------

class TestProcessDocument:
    def _make_page(self, doc_id: str, entities: list[dict]) -> dict:
        return {
            "doc_metadata": {"doc_id": doc_id, "page_num": 1, "total_pages": 1},
            "extracted_entities": entities,
        }

    def test_ready_for_sap(self, mapper):
        entities = [
            {"label": "vendor_gstin",         "text": "27AAPFU0939F1ZV", "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount",  "text": "1180.0",          "confidence": 0.95, "item_index": None},
            {"label": "base_amount",           "text": "1000.0",          "confidence": 0.95, "item_index": None},
            {"label": "cgst_amount",           "text": "90.0",            "confidence": 0.95, "item_index": None},
            {"label": "sgst_amount",           "text": "90.0",            "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-001", entities)])
        assert result["status"] == ProcessingStatus.READY_FOR_SAP.value

    def test_requires_review_missing_gstin_when_gst_regime(self, mapper):
        """vendor_gstin is required only when tax_regime is explicitly GST."""
        entities = [
            {"label": "tax_regime",            "text": "GST",    "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount", "text": "1180.0", "confidence": 0.95, "item_index": None},
            {"label": "base_amount",          "text": "1000.0", "confidence": 0.95, "item_index": None},
            {"label": "cgst_amount",          "text": "90.0",   "confidence": 0.95, "item_index": None},
            {"label": "sgst_amount",          "text": "90.0",   "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-002", entities)])
        assert result["status"] == ProcessingStatus.REQUIRES_MANUAL_REVIEW.value

    def test_legacy_excise_invoice_ready_without_gstin(self, mapper):
        """Pre-GST/Excise invoices have no GSTIN by definition and should
        still reach READY_FOR_SAP via other_tax_amount, not be blocked."""
        entities = [
            {"label": "tax_regime",            "text": "EXCISE", "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount", "text": "1125.0", "confidence": 0.95, "item_index": None},
            {"label": "base_amount",          "text": "1000.0", "confidence": 0.95, "item_index": None},
            {"label": "other_tax_amount",     "text": "125.0",  "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-LEGACY-001", entities)])
        assert result["status"] == ProcessingStatus.READY_FOR_SAP.value
        assert result["financial_data"]["tax_regime"] == "EXCISE"
        assert result["header_data"]["vendor_gstin"] is None

    def test_empty_entities_requires_review(self, mapper):
        result = mapper.process_document([self._make_page("DOC-003", [])])
        assert result["status"] == ProcessingStatus.REQUIRES_MANUAL_REVIEW.value

    def test_line_items_parsed(self, mapper):
        entities = [
            {"label": "vendor_gstin",         "text": "27AAPFU0939F1ZV", "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount",  "text": "1180.0",          "confidence": 0.95, "item_index": None},
            {"label": "base_amount",           "text": "1000.0",          "confidence": 0.95, "item_index": None},
            {"label": "cgst_amount",           "text": "90.0",            "confidence": 0.95, "item_index": None},
            {"label": "sgst_amount",           "text": "90.0",            "confidence": 0.95, "item_index": None},
            {"label": "item_description",      "text": "Laptop",           "confidence": 0.90, "item_index": 0},
            {"label": "item_quantity",         "text": "2",               "confidence": 0.90, "item_index": 0},
            {"label": "item_unit_price",       "text": "500.0",           "confidence": 0.90, "item_index": 0},
            {"label": "item_line_amount",      "text": "1000.0",          "confidence": 0.90, "item_index": 0},
        ]
        result = mapper.process_document([self._make_page("DOC-004", entities)])
        assert len(result["line_item_data"]) == 1
        assert result["line_item_data"][0]["invoice_item_text"] == "Laptop"
        assert result["line_item_data"][0]["quantity"] == 2.0

    def test_gst_invoice_with_pre_gst_date_flagged_for_review(self, mapper):
        """Regression test for a real production bug: GPT-4o-mini misread
        a 2025-era invoice's year as 2013. The math passed and confidence
        was 0.95, so it sailed through to READY_FOR_SAP with zero warning
        despite GST not existing in 2013. Real invoice: Amazon order via
        Clicktech Retail, order ref 403-1684207-4037148."""
        entities = [
            {"label": "vendor_gstin",         "text": "33AAJCC9783E1ZE", "confidence": 0.95, "item_index": None},
            {"label": "invoice_date",         "text": "2013-06-26",      "confidence": 0.95, "item_index": None},
            {"label": "tax_regime",           "text": "GST",             "confidence": 0.95, "item_index": None},
            {"label": "base_amount",          "text": "372.04",          "confidence": 0.95, "item_index": None},
            {"label": "cgst_amount",          "text": "33.48",           "confidence": 0.95, "item_index": None},
            {"label": "sgst_amount",          "text": "33.48",           "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount", "text": "439.00",          "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-DATE-BUG", entities)])
        assert result["status"] == ProcessingStatus.REQUIRES_MANUAL_REVIEW.value
        # The date itself must NOT be silently dropped or further mangled —
        # a reviewer needs to see exactly what the model returned.
        assert result["header_data"]["invoice_date"] == "2013-06-26"

    def test_iso_date_not_truncated_by_date_regex(self, mapper):
        """Regression test: _DATE_RE previously matched 2-digit-first
        patterns before a full 4-digit-year ISO date, causing
        '2013-06-26' to be chopped into '13-06-26' and reparsed as
        '2026-06-13' — silently corrupting an already-correct-format date
        into a different, wrong one."""
        entities = [
            {"label": "invoice_date",         "text": "2025-06-26", "confidence": 0.95, "item_index": None},
            {"label": "tax_regime",           "text": "GST",        "confidence": 0.95, "item_index": None},
            {"label": "vendor_gstin",         "text": "33AAJCC9783E1ZE", "confidence": 0.95, "item_index": None},
            {"label": "base_amount",          "text": "372.04",     "confidence": 0.95, "item_index": None},
            {"label": "cgst_amount",          "text": "33.48",      "confidence": 0.95, "item_index": None},
            {"label": "sgst_amount",          "text": "33.48",      "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount", "text": "439.00",     "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-ISO-DATE", entities)])
        assert result["header_data"]["invoice_date"] == "2025-06-26"
        assert result["status"] == ProcessingStatus.READY_FOR_SAP.value

    def test_legacy_excise_predates_gst_without_contradiction(self, mapper):
        """A genuinely pre-GST invoice (tax_regime=EXCISE) dated before
        2017-07-01 is NOT a contradiction — GST didn't exist yet, which is
        exactly why it's EXCISE. The plausibility check must only fire when
        tax_regime is explicitly GST, not for every old date."""
        entities = [
            {"label": "invoice_date",     "text": "2015-04-10", "confidence": 0.95, "item_index": None},
            {"label": "tax_regime",       "text": "EXCISE",     "confidence": 0.95, "item_index": None},
            {"label": "base_amount",      "text": "1000.00",    "confidence": 0.95, "item_index": None},
            {"label": "other_tax_amount", "text": "125.00",     "confidence": 0.95, "item_index": None},
            {"label": "total_invoice_amount", "text": "1125.00", "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-LEGACY-DATE-OK", entities)])
        assert result["status"] == ProcessingStatus.READY_FOR_SAP.value