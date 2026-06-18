"""
config.py — Single source of truth for all pipeline configuration.
All runtime values read from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
import tempfile


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Set it via docker run -e or a .env file."
        )
    return value


def _get(key: str, default: str) -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# API / Model
# ---------------------------------------------------------------------------
GITHUB_TOKEN: str = _require("GITHUB_TOKEN")
MODEL_NAME: str = _get("MODEL_NAME", "gpt-4o-mini")
GITHUB_ENDPOINT: str = _get("GITHUB_ENDPOINT", "https://models.inference.ai.azure.com")
API_DELAY_SECONDS: int = int(_get("API_DELAY_SECONDS", "4"))
MAX_RETRIES: int = int(_get("MAX_RETRIES", "3"))
TIMEOUT_SECONDS: int = int(_get("TIMEOUT_SECONDS", "120"))

# ---------------------------------------------------------------------------
# Ingestor (Piece 1)
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = _get("OUTPUT_DIR", os.path.join(tempfile.gettempdir(), "ingestor"))
TARGET_DPI: int = int(_get("TARGET_DPI", "300"))
NATIVE_TEXT_MIN_CHARS: int = int(_get("NATIVE_TEXT_MIN_CHARS", "10"))
TARGET_FORMAT: str = "PNG"

SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp"}
)
SUPPORTED_PDF_EXTENSION: str = ".pdf"

# ---------------------------------------------------------------------------
# Mapper / Parser (Piece 3)
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD: float = float(_get("CONFIDENCE_THRESHOLD", "0.72"))
MATH_TOLERANCE: float = float(_get("MATH_TOLERANCE", "0.05"))

# ---------------------------------------------------------------------------
# SAP defaults (Piece 3)
# ---------------------------------------------------------------------------
SAP_COMPANY_CODE: str = _get("SAP_COMPANY_CODE", "1000")
SAP_DOC_TYPE: str = _get("SAP_DOC_TYPE", "RE")
SAP_CURRENCY: str = _get("SAP_CURRENCY", "INR")

# ---------------------------------------------------------------------------
# Date plausibility bounds
# ---------------------------------------------------------------------------
# ANOMALY FIX: the date parser previously accepted any syntactically valid
# date with zero real-world plausibility check. A vision model misreading a
# year digit (e.g. "2025" -> "2013") produced a perfectly well-formed
# YYYY-MM-DD string that sailed straight through to READY_FOR_SAP — the
# math validation only checks arithmetic, never date sanity. GPT-4o-mini in
# particular was observed doing this consistently on real invoices.
#
# GST_EFFECTIVE_DATE: India's GST regime took legal effect on 2017-07-01.
# Any invoice claiming tax_regime="GST" dated before this is definitionally
# impossible — GST didn't exist yet. This is a hard, deterministic fact, not
# a model judgment call, so it's enforced in code rather than left to the AI.
GST_EFFECTIVE_DATE: str = "2017-07-01"

# MIN_PLAUSIBLE_INVOICE_DATE: a generous floor for ANY invoice regardless of
# regime, to catch wildly wrong OCR/vision misreads (e.g. a 1900s date from
# a garbled year). Not regime-specific, just a sanity floor.
MIN_PLAUSIBLE_INVOICE_DATE: str = "1990-01-01"

# MAX_FUTURE_DAYS: invoices dated more than this many days in the future are
# almost certainly a misread (e.g. month/day swapped, or a digit transposed)
# rather than a real future-dated document.
MAX_FUTURE_DAYS: int = 30

# ---------------------------------------------------------------------------
# Label sets shared between Piece 2 and Piece 3
# ---------------------------------------------------------------------------
FINANCIAL_LABELS: frozenset[str] = frozenset({
    "tax_regime", "base_amount", "cgst_amount", "sgst_amount", "igst_amount",
    "other_tax_amount", "total_invoice_amount",
})

HEADER_LABELS: frozenset[str] = frozenset({
    "vendor_name", "vendor_gstin", "buyer_name", "buyer_gstin",
    "invoice_number", "invoice_date", "po_number",
})

LINE_ITEM_LABELS: frozenset[str] = frozenset({
    "item_description", "hsn_sac_code", "item_quantity", "item_unit_price", "item_line_amount",
})

# FIX (vulnerability C): vendor_gstin is only required when tax_regime == "GST".
# Pre-2017 Excise invoices and international invoices legitimately have no
# GSTIN at all — DocumentMapper._determine_status applies this conditionally
# rather than as a blanket requirement (see mapper_parser.py).
REQUIRED_FIELDS: frozenset[str] = frozenset({"total_invoice_amount"})
REQUIRED_FIELDS_GST_ONLY: frozenset[str] = frozenset({"vendor_gstin"})