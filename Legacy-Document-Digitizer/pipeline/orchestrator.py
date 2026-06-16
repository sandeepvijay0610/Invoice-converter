"""
orchestrator.py
===============
Thin wiring layer that connects Piece 1 → Piece 2 → Piece 3.

Each piece remains ignorant of the others; this module is the only
place that knows the full call sequence.

Typical usage
-------------
    from pipeline.orchestrator import run_pipeline

    result = run_pipeline(
        file_path="invoice.pdf",
        doc_id="INV-2026-00123",
        tenant_id="ACME",
    )
    # result is an InvoicePayload dict ready for SAP or manual review queue
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from .config import OUTPUT_DIR
from .document_preprocessor import DocumentPreprocessor
from .inference_worker import InferenceWorker, RateLimitExceeded
from .mapper_parser import (
    DocumentMapper,
    FinancialData,
    HeaderData,
    ProcessingStatus,
)

logger = logging.getLogger(__name__)

# FIX #1: Lazy singletons — NOT instantiated at import time.
# Previously, InferenceWorker() was called at module level, which triggered
# _require("GITHUB_TOKEN") before env vars were injected (crashing pytest
# and any Docker start before env is ready). Now they are created on first call.
_worker: InferenceWorker | None = None
_mapper: DocumentMapper | None = None


def _get_worker() -> InferenceWorker:
    global _worker
    if _worker is None:
        _worker = InferenceWorker()
    return _worker


def _get_mapper() -> DocumentMapper:
    global _mapper
    if _mapper is None:
        _mapper = DocumentMapper()
    return _mapper


def run_pipeline(
    file_path: str | Path,
    doc_id: str,
    output_dir: str | Path = OUTPUT_DIR,
    sap_overrides: Optional[dict[str, str]] = None,
    **extra_metadata: Any,
) -> dict[str, Any]:
    """
    Run the full invoice extraction pipeline on a single file.

    Parameters
    ----------
    file_path : str | Path
        Path to the PDF or image file to process.
    doc_id : str
        Unique document identifier (e.g. "INV-2026-00123").
        Injected into all ProcessedPage metadata and propagated to the
        final InvoicePayload.
    output_dir : str | Path
        Where normalized PNG files are written. Defaults to OUTPUT_DIR
        from config (controlled by OUTPUT_DIR env var).
    sap_overrides : dict | None
        Optional SAP metadata overrides (company_code, doc_type, currency).
    **extra_metadata
        Any additional key/value pairs forwarded to ProcessedPage.metadata
        (e.g. tenant_id="ACME", batch_id="BATCH-001").

    Returns
    -------
    dict
        Serialized InvoicePayload. Always returned — on failure the payload
        will have status=REQUIRES_MANUAL_REVIEW and empty fields.
    """
    file_path = Path(file_path)
    metadata = {"doc_id": doc_id, **extra_metadata}

    logger.info("Pipeline start | doc_id=%s file=%s", doc_id, file_path.name)

    # Piece 1 — Normalize to PNG pages
    preprocessor = DocumentPreprocessor(output_dir=output_dir)
    pages = preprocessor.process(file_path, metadata=metadata)

    logger.info("Preprocessed %d page(s) | doc_id=%s", len(pages), doc_id)

    # Piece 2 — Extract entities via vision model
    try:
        extraction_result = _get_worker().process_document(pages)
    except RateLimitExceeded as exc:
        # Don't run this through the mapper at all — there's no extraction
        # to map, and forcing it through would either crash on missing
        # required fields or get coerced into REQUIRES_MANUAL_REVIEW, which
        # would misleadingly suggest something is wrong with the document
        # itself rather than with provider capacity at this moment.
        logger.warning(
            "Pipeline rate-limited | doc_id=%s — returning RATE_LIMITED for retry. %s",
            doc_id, exc,
        )
        payload = {
            "doc_id": doc_id,
            "status": ProcessingStatus.RATE_LIMITED.value,
            "overall_confidence": 0.0,
            "sap_metadata": {
                "company_code": (sap_overrides or {}).get("company_code", ""),
                "doc_type": (sap_overrides or {}).get("doc_type", ""),
                "currency": (sap_overrides or {}).get("currency", ""),
            },
            "header_data": HeaderData().model_dump(mode="json"),
            "financial_data": FinancialData().model_dump(mode="json"),
            "line_item_data": [],
        }
        logger.info(
            "Pipeline complete | doc_id=%s status=%s",
            doc_id, payload.get("status"),
        )
        return payload

    # Piece 3 — Map and validate into SAP payload
    payload = _get_mapper().process_document(
        [extraction_result],
        sap_overrides=sap_overrides,
    )

    logger.info(
        "Pipeline complete | doc_id=%s status=%s",
        doc_id, payload.get("status"),
    )
    return payload