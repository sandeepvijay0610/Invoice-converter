"""
inference_worker.py
===================
Piece 2 — AI Worker Node: Multimodal invoice extraction via GitHub Models
(GPT-4o / GPT-4o-mini) or local Ollama models (Phi-3.5-Vision, Llama 3.2-Vision).

Supports single-page and multi-page documents. All pages are sent to the
model in a single API call and the result is returned as a flat entity list
compatible with the Mapper/Parser (Piece 3).
"""

from __future__ import annotations

import base64
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

import requests
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, Field

from .config import (
    API_DELAY_SECONDS,
    GITHUB_ENDPOINT,
    GITHUB_TOKEN,
    MAX_RETRIES,
    MODEL_NAME,
    MODEL_PROVIDER,        # "github" or "ollama"
    OLLAMA_BASE_URL,        # "http://localhost:11434/v1"
    OLLAMA_MODEL_NAME,       # "phi3.5:vision" or "llama3.2-vision:11b"
    TIMEOUT_SECONDS,
)
from .document_preprocessor import ProcessedPage

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """
    Raised when the model API rejects a request due to rate limiting and
    all configured retries (SDK-level + our own backoff loop) are exhausted.

    ANOMALY FIX: orchestrator.py imports this exact class from this module
    (`from .inference_worker import InferenceWorker, RateLimitExceeded`),
    but it didn't exist here — every worker container would fail at import
    time with ImportError before processing a single message. This class
    is intentionally distinct from generic extraction failures (corrupt
    PDF, model returned malformed JSON) so the orchestrator can route it to
    a RATE_LIMITED status instead of silently bucketing it with
    REQUIRES_MANUAL_REVIEW — a rate-limited invoice has nothing wrong with
    it and should be retried, not sent to a human.
    """
    pass


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
    Piece 2: Multimodal invoice extraction via GitHub Models or local Ollama.

    Parameters
    ----------
    endpoint : str
        Azure inference endpoint URL (GitHub) or Ollama base URL.
    api_key : str
        GitHub Models PAT (ignored for Ollama).
    model : str
        Model name (gpt-4o, gpt-4o-mini, or Ollama model name).
    provider : str
        "github" or "ollama".
    max_retries : int
        Number of retries the client will attempt.
    timeout : int
        Request timeout in seconds.
    """

    def __init__(
        self,
        endpoint: str = GITHUB_ENDPOINT,
        api_key: str = GITHUB_TOKEN,
        model: str = MODEL_NAME,
        provider: str = MODEL_PROVIDER,
        max_retries: int = MAX_RETRIES,
        timeout: int = TIMEOUT_SECONDS,
        max_backoff_attempts: int = 5,
    ) -> None:
        self._model = model
        self._provider = provider
        self._delay = API_DELAY_SECONDS
        self._call_count = 0
        self._max_backoff_attempts = max_backoff_attempts

        if provider == "ollama":
            self._ollama_url = endpoint or OLLAMA_BASE_URL
            self._client = None  # Ollama uses raw HTTP, not OpenAI client
        else:
            self._client = OpenAI(
                base_url=endpoint,
                api_key=api_key,
                max_retries=max_retries,
                timeout=timeout,
            )

        logger.info("InferenceWorker ready | provider=%s model=%s", provider, model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_document(self, pages: list[ProcessedPage]) -> dict:
        """Extract invoice data from one or more pages."""
        if not pages:
            return self._empty_result("UNKNOWN", 1, "UNKNOWN", 0)

        doc_id = str(pages[0].metadata.get("doc_id", "UNKNOWN"))
        total_pages = len(pages)

        logger.info("Extracting | doc_id=%s pages=%d model=%s provider=%s",
                     doc_id, total_pages, self._model, self._provider)

        for page in pages:
            if not Path(page.image_path).exists():
                raise FileNotFoundError(f"Image not found: {page.image_path}")

        self._rate_limit()

        t0 = time.perf_counter()
        try:
            image_b64_list = [self._encode_image(page.image_path) for page in pages]

            if self._provider == "ollama":
                if total_pages == 1:
                    invoice = self._call_with_backoff(self._call_ollama_single, image_b64_list[0])
                else:
                    invoice = self._call_with_backoff(self._call_ollama_multi, image_b64_list)
            else:
                if total_pages == 1:
                    invoice = self._call_with_backoff(self._call_model_single, image_b64_list[0])
                else:
                    invoice = self._call_with_backoff(self._call_model_multi, image_b64_list)

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

        except RateLimitExceeded:
            logger.error("Rate limit exhausted | doc_id=%s pages=%d", doc_id, total_pages)
            raise

        except Exception as exc:
            logger.error("Extraction failed | doc_id=%s error=%s", doc_id, exc, exc_info=True)
            return self._empty_result(
                doc_id, pages[0].page_number, pages[0].source_type.name, total_pages
            )

    # ------------------------------------------------------------------
    # Private — rate limiting
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Small fixed pacing delay between calls within this worker process."""
        self._call_count += 1
        if self._call_count > 1:
            time.sleep(self._delay)

    def _call_with_backoff(self, fn, *args, **kwargs):
        """Exponential backoff + jitter for transient/rate-limit errors."""
        last_exc: Exception | None = None
        for attempt in range(self._max_backoff_attempts):
            try:
                return fn(*args, **kwargs)
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                last_exc = exc
                if attempt == self._max_backoff_attempts - 1:
                    break
                base_delay = min(2 ** (attempt + 1), 60)
                jitter = base_delay * random.uniform(-0.25, 0.25)
                delay = max(0.5, base_delay + jitter)
                logger.warning(
                    "Transient API error (attempt %d/%d), backing off %.1fs: %s",
                    attempt + 1, self._max_backoff_attempts, delay, exc,
                )
                time.sleep(delay)
            except APIStatusError:
                raise

        raise RateLimitExceeded(
            f"Exhausted {self._max_backoff_attempts} attempts against rate limiting "
            f"or transient errors: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Private — GitHub Models API calls
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
    # Private — Ollama API calls (local model, no rate limits, no auth)
    # ------------------------------------------------------------------

    def _call_ollama_single(self, image_b64: str) -> _InvoiceSchema:
        """Call local Ollama model with a single page image."""
        return self._call_ollama(image_b64, _SINGLE_PAGE_SYSTEM_PROMPT)

    def _call_ollama_multi(self, image_b64_list: list[str]) -> _InvoiceSchema:
        """Call local Ollama model with multiple page images."""
        return self._call_ollama(image_b64_list, _MULTI_PAGE_SYSTEM_PROMPT)

    def _call_ollama(self, images, system_prompt: str) -> _InvoiceSchema:
        """
        Generic Ollama chat completions call.

        Ollama's API is OpenAI-compatible at /v1/chat/completions.
        We use requests directly (no SDK needed) with the schema passed
        as JSON in the prompt since Ollama doesn't support response_format.
        """
        schema_json = json.dumps(_InvoiceSchema.model_json_schema(), indent=2)

        user_content: list[dict] = [
            {
                "type": "text",
                "text": (
                    "Extract the invoice data from the image(s) into this exact JSON schema:\n"
                    f"```json\n{schema_json}\n```\n"
                    "Return ONLY valid JSON matching this schema. No other text."
                ),
            }
        ]

        # Handle single image (str) or multiple images (list)
        image_list = images if isinstance(images, list) else [images]
        for b64 in image_list:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": b64, "detail": "high"},
            })

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "max_tokens": 4096,
            "stream": False,
        }

        response = requests.post(
            f"{self._ollama_url}/chat/completions",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        body = response.json()
        raw_text = body["choices"][0]["message"]["content"]

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```json", 1)[-1]
            raw_text = raw_text.split("```", 1)[0]

        invoice = _InvoiceSchema.model_validate_json(raw_text.strip())
        return invoice

    # ------------------------------------------------------------------
    # Private — schema → entity list
    # ------------------------------------------------------------------

    def _schema_to_entities(self, invoice: _InvoiceSchema) -> list[dict]:
        """Flatten the structured Pydantic schema into entity list format."""
        from datetime import datetime

        entities: list[dict] = []
        hd = invoice.header_data
        fd = invoice.financial_data

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