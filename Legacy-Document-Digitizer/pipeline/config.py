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
MODEL_PROVIDER = _get("MODEL_PROVIDER", "github")  # "github", "azure", "ollama", or "gemini"

# GitHub Models
GITHUB_TOKEN: str = _get("GITHUB_TOKEN", "")
GITHUB_ENDPOINT: str = _get("GITHUB_ENDPOINT", "https://models.inference.ai.azure.com")

# Azure OpenAI
AZURE_OPENAI_ENDPOINT: str = _get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY: str = _get("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_DEPLOYMENT: str = _get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
AZURE_OPENAI_API_VERSION: str = _get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "phi3.5:vision")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

# Model name (used as fallback)
MODEL_NAME: str = _get("MODEL_NAME", "gpt-4o-mini")

# Rate limiting
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
GST_EFFECTIVE_DATE: str = "2017-07-01"
MIN_PLAUSIBLE_INVOICE_DATE: str = "1990-01-01"
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

REQUIRED_FIELDS: frozenset[str] = frozenset({"total_invoice_amount"})
REQUIRED_FIELDS_GST_ONLY: frozenset[str] = frozenset({"vendor_gstin"})