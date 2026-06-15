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

    def test_requires_review_missing_gstin(self, mapper):
        entities = [
            {"label": "total_invoice_amount", "text": "1180.0", "confidence": 0.95, "item_index": None},
            {"label": "base_amount",          "text": "1000.0", "confidence": 0.95, "item_index": None},
            {"label": "cgst_amount",          "text": "90.0",   "confidence": 0.95, "item_index": None},
            {"label": "sgst_amount",          "text": "90.0",   "confidence": 0.95, "item_index": None},
        ]
        result = mapper.process_document([self._make_page("DOC-002", entities)])
        assert result["status"] == ProcessingStatus.REQUIRES_MANUAL_REVIEW.value

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
