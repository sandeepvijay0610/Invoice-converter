"""
inference_worker.py
===================
Piece 2 — AI Worker Node: Multimodal invoice extraction via GitHub Models
(GPT-4o / GPT-4o-mini).

Supports single-page and multi-page documents. All pages are sent to the
model in a single API call and the result is returned as a flat entity list
compatible with the Mapper/Parser (Piece 3).
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from .config import (
    API_DELAY_SECONDS,
    GITHUB_ENDPOINT,
    GITHUB_TOKEN,
    MAX_RETRIES,
    MODEL_NAME,
    TIMEOUT_SECONDS,
)
from .document_preprocessor import ProcessedPage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema — structured output contract with the model
# ---------------------------------------------------------------------------

class _HeaderData(BaseModel):
    vendor_name: Optional[str] = Field(None, description="Company name of the vendor/seller")
    vendor_gstin: Optional[str] = Field(None, description="GSTIN of the vendor (15 characters)")
    buyer_name: Optional[str] = Field(None, description="Company name of the buyer")
    buyer_gstin: Optional[str] = Field(None, description="GSTIN of the buyer (15 characters)")
    invoice_number: Optional[str] = Field(None, description="Invoice number or bill number")
    invoice_date: Optional[str] = Field(None, description="Invoice date in YYYY-MM-DD format")
    po_number: Optional[str] = Field(None, description="Purchase Order number if present")


class _FinancialData(BaseModel):
    tax_regime: Optional[str] = Field(None, description="Tax regime: 'GST', 'EXCISE', 'INTERNATIONAL', or 'NONE'")
    base_amount: Optional[float] = Field(None, description="Taxable base amount before tax")
    cgst_amount: Optional[float] = Field(None, description="Central GST amount (intra-state)")
    sgst_amount: Optional[float] = Field(None, description="State GST amount (intra-state)")
    igst_amount: Optional[float] = Field(None, description="Integrated GST amount (inter-state)")
    other_tax_amount: Optional[float] = Field(None, description="Sum of non-GST tax/duty lines: Excise, CST, VAT, service tax, international VAT/sales tax")
    total_invoice_amount: Optional[float] = Field(None, description="Grand total including all taxes")


class _LineItem(BaseModel):
    item_description: Optional[str] = Field(None, description="Description of goods or services")
    hsn_sac_code: Optional[str] = Field(None, description="HSN or SAC commodity code")
    quantity: Optional[float] = Field(None, description="Quantity of items")
    unit_price: Optional[float] = Field(None, description="Price per unit in INR")
    line_amount: Optional[float] = Field(None, description="Total for this line (quantity * unit_price)")


class _InvoiceSchema(BaseModel):
    header_data: _HeaderData = Field(default_factory=_HeaderData)
    financial_data: _FinancialData = Field(default_factory=_FinancialData)
    line_items: list[_LineItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SINGLE_PAGE_SYSTEM_PROMPT = (
    "You are an invoice extraction system that handles both modern Indian GST "
    "invoices and legacy/non-GST invoices (pre-2017 Central Excise Duty + CST/VAT, "
    "service tax, or international invoices with VAT/sales tax). "
    "First identify the tax_regime: 'GST' if you see CGST/SGST/IGST line items, "
    "'EXCISE' if you see Excise Duty/CST/VAT/service tax (typically pre-2017 Indian "
    "invoices), 'INTERNATIONAL' for non-Indian VAT/sales tax, or 'NONE' if there is "
    "no tax shown at all. "
    "If tax_regime is 'GST', populate cgst_amount/sgst_amount/igst_amount and leave "
    "other_tax_amount null. If tax_regime is 'EXCISE' or 'INTERNATIONAL', add all "
    "non-GST tax/duty line amounts together into other_tax_amount and leave "
    "cgst_amount/sgst_amount/igst_amount null. "
    "Extract all header fields, financial totals, and line items from the invoice image. "
    "For dates, always use YYYY-MM-DD format. If you see a 2-digit year, "
    "expand it to the full 4-digit year based on context. "
    "For amounts, extract the numeric value without currency symbols. "
    "If a field is not present, leave it null. "
    "For GSTIN fields, extract the 15-character alphanumeric code; leave null if "
    "this is a pre-GST or international invoice with no GSTIN. "
    "Vendor (seller) tax ID is usually at the top or top-left; "
    "buyer tax ID is in the 'Bill To' section."
)

_MULTI_PAGE_SYSTEM_PROMPT = (
    "You are an invoice extraction system that handles both modern Indian GST "
    "invoices and legacy/non-GST invoices (pre-2017 Central Excise Duty + CST/VAT, "
    "service tax, or international invoices with VAT/sales tax). "
    "You will receive multiple page images from a SINGLE invoice document. "
    "Combine information from all pages into ONE invoice extraction. "
    "First identify the tax_regime: 'GST' if you see CGST/SGST/IGST line items, "
    "'EXCISE' if you see Excise Duty/CST/VAT/service tax (typically pre-2017 Indian "
    "invoices), 'INTERNATIONAL' for non-Indian VAT/sales tax, or 'NONE' if there is "
    "no tax shown at all. "
    "If tax_regime is 'GST', populate cgst_amount/sgst_amount/igst_amount and leave "
    "other_tax_amount null. If tax_regime is 'EXCISE' or 'INTERNATIONAL', add all "
    "non-GST tax/duty line amounts together into other_tax_amount and leave "
    "cgst_amount/sgst_amount/igst_amount null. "
    "If the same field appears on multiple pages, use the most complete version. "
    "For line items, include ALL items from ALL pages. "
    "For financial totals, use the values from the LAST page (the summary page). "
    "For dates, always use YYYY-MM-DD format. "
    "For amounts, extract numeric values without currency symbols. "
    "If a field is not present on any page, leave it null."
)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class InferenceWorker:
    """
    Piece 2: GitHub Models GPT-4o/Mini multimodal invoice extraction.

    Parameters
    ----------
    endpoint : str
        Azure inference endpoint URL.
    api_key : str
        GitHub Models PAT.
    model : str
        Model name (gpt-4o or gpt-4o-mini).
    max_retries : int
        Number of retries the OpenAI client will attempt.
    timeout : int
        Request timeout in seconds.
    """

    def __init__(
        self,
        endpoint: str = GITHUB_ENDPOINT,
        api_key: str = GITHUB_TOKEN,
        model: str = MODEL_NAME,
        max_retries: int = MAX_RETRIES,
        timeout: int = TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._delay = API_DELAY_SECONDS
        self._call_count = 0

        self._client = OpenAI(
            base_url=endpoint,
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
        )

        logger.info("InferenceWorker ready | model=%s", model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_document(self, pages: list[ProcessedPage]) -> dict:
        """
        Extract invoice data from one or more pages.

        Sends all pages to the model in a single API call.
        Returns a dict with ``doc_metadata`` and ``extracted_entities``
        compatible with DocumentMapper.process_document().

        Parameters
        ----------
        pages : list[ProcessedPage]
            Sorted list of pages from DocumentPreprocessor.process().
            Must all share the same doc_id in their metadata.

        Returns
        -------
        dict
            ``{"doc_metadata": {...}, "extracted_entities": [...]}``.
            On extraction failure returns the same shape with an empty
            entity list rather than raising, so the pipeline can continue
            and mark the document for manual review.
        """
        if not pages:
            return self._empty_result("UNKNOWN", 1, "UNKNOWN", 0)

        doc_id = str(pages[0].metadata.get("doc_id", "UNKNOWN"))
        total_pages = len(pages)

        logger.info("Extracting | doc_id=%s pages=%d model=%s", doc_id, total_pages, self._model)

        for page in pages:
            if not Path(page.image_path).exists():
                raise FileNotFoundError(f"Image not found: {page.image_path}")

        self._rate_limit()

        t0 = time.perf_counter()
        try:
            image_b64_list = [self._encode_image(page.image_path) for page in pages]

            if total_pages == 1:
                invoice = self._call_model_single(image_b64_list[0])
            else:
                invoice = self._call_model_multi(image_b64_list)

            entities = self._schema_to_entities(invoice)
            elapsed = time.perf_counter() - t0

            logger.info(
                "Extraction complete | doc_id=%s pages=%d entities=%d elapsed=%.2fs",
                doc_id, total_pages, len(entities), elapsed,
            )

            return {
                "doc_metadata": {
                    "doc_id": doc_id,
                    "page_num": pages[0].page_number,
                    "source_type": pages[0].source_type.name,
                    "total_pages": total_pages,
                },
                "extracted_entities": entities,
            }

        except Exception as exc:
            logger.error(
                "Extraction failed | doc_id=%s error=%s", doc_id, exc, exc_info=True
            )
            return self._empty_result(
                doc_id, pages[0].page_number, pages[0].source_type.name, total_pages
            )

    # ------------------------------------------------------------------
    # Private — rate limiting
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        self._call_count += 1
        if self._call_count > 1:
            time.sleep(self._delay)

    # ------------------------------------------------------------------
    # Private — model calls
    # ------------------------------------------------------------------
    @staticmethod
    def _encode_image(image_path: str) -> str:
        """Read an image file and encode it as base64 data URL."""
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        
        suffix = Path(image_path).suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".tiff": "image/tiff", ".bmp": "image/bmp",
        }.get(suffix, "image/png")
        
        return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

    def _call_model_single(self, image_b64: str) -> _InvoiceSchema:
        response = self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SINGLE_PAGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the invoice data from this image."},
                        {"type": "image_url", "image_url": {"url": image_b64, "detail": "high"}},
                    ],
                },
            ],
            response_format=_InvoiceSchema,
            max_tokens=4096,
            temperature=0.0,
        )
        invoice = response.choices[0].message.parsed
        if invoice is None:
            raise ValueError("Model returned None for parsed response")
        logger.debug("Token usage: %s", response.usage)
        return invoice

    def _call_model_multi(self, image_b64_list: list[str]) -> _InvoiceSchema:
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"This invoice has {len(image_b64_list)} pages. "
                    "Extract all data from all pages into one invoice."
                ),
            }
        ]
        for b64 in image_b64_list:
            content.append({
                "type": "image_url",
                "image_url": {"url": b64, "detail": "high"},
            })

        response = self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _MULTI_PAGE_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format=_InvoiceSchema,
            max_tokens=4096,
            temperature=0.0,
        )
        invoice = response.choices[0].message.parsed
        if invoice is None:
            raise ValueError("Model returned None for parsed response (multi-page)")
        logger.debug("Multi-page token usage: %s", response.usage)
        return invoice

    # ------------------------------------------------------------------
    # Private — schema → entity list
    # ------------------------------------------------------------------

    def _schema_to_entities(self, invoice: _InvoiceSchema) -> list[dict]:
        """
        Flatten the structured Pydantic schema into the entity list format
        expected by DocumentMapper (Piece 3).

        Date validation: if the model returns a date outside the plausible
        range (2020–2030), we log a warning and keep the value so the mapper
        can flag it for manual review rather than silently discarding data.
        """
        from datetime import datetime

        entities: list[dict] = []
        hd = invoice.header_data
        fd = invoice.financial_data

        # Validate date — warn but don't silently correct or discard
        invoice_date = hd.invoice_date
        if invoice_date:
            try:
                dt = datetime.strptime(invoice_date, "%Y-%m-%d")
                if not (2020 <= dt.year <= 2030):
                    logger.warning(
                        "Suspicious invoice date year: %s — passing through for manual review",
                        invoice_date,
                    )
            except ValueError:
                logger.warning("Unparseable date from model: '%s' — dropping", invoice_date)
                invoice_date = None

        header_fields = [
            ("vendor_name",    hd.vendor_name),
            ("vendor_gstin",   hd.vendor_gstin),
            ("buyer_name",     hd.buyer_name),
            ("buyer_gstin",    hd.buyer_gstin),
            ("invoice_number", hd.invoice_number),
            ("invoice_date",   invoice_date),
            ("po_number",      hd.po_number),
        ]
        for label, value in header_fields:
            if value is not None:
                entities.append(self._entity(label, str(value), confidence=0.95))

        financial_fields = [
            ("tax_regime",            fd.tax_regime),
            ("base_amount",           fd.base_amount),
            ("cgst_amount",           fd.cgst_amount),
            ("sgst_amount",           fd.sgst_amount),
            ("igst_amount",           fd.igst_amount),
            ("other_tax_amount",      fd.other_tax_amount),
            ("total_invoice_amount",  fd.total_invoice_amount),
        ]
        for label, value in financial_fields:
            if value is not None:
                entities.append(self._entity(label, str(value), confidence=0.95))

        for i, item in enumerate(invoice.line_items):
            item_fields = [
                ("item_description", item.item_description),
                ("hsn_sac_code",     item.hsn_sac_code),
                ("item_quantity",    None if item.quantity is None else str(item.quantity)),
                ("item_unit_price",  None if item.unit_price is None else str(item.unit_price)),
                ("item_line_amount", None if item.line_amount is None else str(item.line_amount)),
            ]
            for label, value in item_fields:
                if value is not None:
                    entities.append(self._entity(label, value, confidence=0.90, item_index=i))

        return entities

    @staticmethod
    def _entity(
        label: str,
        text: str,
        confidence: float,
        item_index: Optional[int] = None,
    ) -> dict:
        return {
            "label": label,
            "text": text,
            "box": [0.0, 0.0, 0.0, 0.0],
            "confidence": confidence,
            "item_index": item_index,
        }

    @staticmethod
    def _empty_result(
        doc_id: str, page_num: int, source_type: str, total_pages: int
    ) -> dict:
        return {
            "doc_metadata": {
                "doc_id": doc_id,
                "page_num": page_num,
                "source_type": source_type,
                "total_pages": total_pages,
            },
            "extracted_entities": [],
        }