"""
invoice_pipeline
================
Enterprise invoice extraction pipeline for SAP FICO/MM.

Pieces
------
1. DocumentPreprocessor — PDF/image → 300 DPI PNGs
2. InferenceWorker      — PNG pages → extracted entities (via GPT-4o)
3. DocumentMapper       — entities → validated InvoicePayload

Quick start
-----------
    from pipeline.orchestrator import run_pipeline

    result = run_pipeline("invoice.pdf", doc_id="INV-001")
"""

from .document_preprocessor import DocumentPreprocessor, ProcessedPage, SourceType
from .inference_worker import InferenceWorker
from .mapper_parser import DocumentMapper, InvoicePayload, ProcessingStatus
from .orchestrator import run_pipeline

__all__ = [
    "DocumentPreprocessor",
    "ProcessedPage",
    "SourceType",
    "InferenceWorker",
    "DocumentMapper",
    "InvoicePayload",
    "ProcessingStatus",
    "run_pipeline",
]
