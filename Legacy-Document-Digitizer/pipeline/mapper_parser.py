"""
mapper_parser.py
================
Piece 3 — Mapper / Parser: Normalizes extracted entities into a structured
InvoicePayload ready for SAP FICO/MM posting.

Responsibilities
----------------
- Stitch entities from one or more page dicts into the best single value
  per field (highest confidence wins for header/financial fields).
- Parse and validate field values (dates, amounts, GSTINs).
- Run FICO math check (base + tax components == total).
- Determine processing status: READY_FOR_SAP or REQUIRES_MANUAL_REVIEW.
- Assemble and return a validated InvoicePayload as a plain dict.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import (
    CONFIDENCE_THRESHOLD,
    FINANCIAL_LABELS,
    GST_EFFECTIVE_DATE,
    HEADER_LABELS,
    LINE_ITEM_LABELS,
    MATH_TOLERANCE,
    MAX_FUTURE_DAYS,
    MIN_PLAUSIBLE_INVOICE_DATE,
    REQUIRED_FIELDS,
    REQUIRED_FIELDS_GST_ONLY,
    SAP_COMPANY_CODE,
    SAP_CURRENCY,
    SAP_DOC_TYPE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_DISTRACTOR_LABELS: frozenset[str] = frozenset({"base_amount_label"})

_ALL_VALID_LABELS: frozenset[str] = (
    HEADER_LABELS | FINANCIAL_LABELS | LINE_ITEM_LABELS | _DISTRACTOR_LABELS
)

_GSTIN_RE = re.compile(
    r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b', re.IGNORECASE
)
_INVOICE_RE = re.compile(
    r'(INV[/\-]?\d{4,}[/\-]?\d{3,}'
    r'|ACM[/\-]\d{2}[/\-]\d{2}[/\-]\d{3,}'
    r'|\d{4}/INV/\d{4}'
    r'|BILL[/\-]\d{4}[/\-]\d{3,}'
    r'|INV\d{5,})',
    re.IGNORECASE,
)
_PO_RE = re.compile(
    r'(?:PO[/\-]?\s*(?:No\.?|Number|#)?\s*[:\-]?\s*)(\d{4,8})', re.IGNORECASE
)
_DATE_RE = re.compile(
    r'(\d{4}-\d{2}-\d{2}'
    r'|\d{2}[-/\.]\d{2}[-/\.]\d{2,4}'
    r'|\d{2}\s+[A-Za-z]+\s+\d{4}'
    r'|\d{2}-[A-Za-z]{3}-\d{4})',
    re.IGNORECASE,
)
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
    "%d-%m-%y", "%d/%m/%y", "%d.%m.%y",
    "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y",
    "%d-%B-%Y", "%d %B %Y",
    "%m/%d/%Y",
    "%Y%m%d",
    "%d %m %Y", "%d %m %y",
]


# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------

class ProcessingStatus(str, Enum):
    READY_FOR_SAP = "READY_FOR_SAP"
    REQUIRES_MANUAL_REVIEW = "REQUIRES_MANUAL_REVIEW"
    # ANOMALY FIX: orchestrator.py already references
    # ProcessingStatus.RATE_LIMITED.value when InferenceWorker exhausts its
    # retry/backoff attempts against a 429. That enum member didn't exist
    # here, so the very first real rate-limit event would raise
    # AttributeError mid-pipeline. Distinct from REQUIRES_MANUAL_REVIEW on
    # purpose: a rate-limited invoice has nothing wrong with the document
    # itself, it just needs to be retried once the provider's quota
    # recovers — routing it to manual review would put it in front of a
    # human for no reason.
    RATE_LIMITED = "RATE_LIMITED"


class SapMetadata(BaseModel):
    company_code: str = Field(SAP_COMPANY_CODE)
    doc_type: str = Field(SAP_DOC_TYPE)
    currency: str = Field(SAP_CURRENCY)


class HeaderData(BaseModel):
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    po_number: str | None = None

    @field_validator("invoice_date", mode="before")
    @classmethod
    def _require_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            logger.warning(
                "HeaderData received non-ISO date '%s'; setting to None.", value
            )
            return None


class FinancialData(BaseModel):
    tax_regime: str | None = None
    base_amount: float | None = None
    cgst_amount: float | None = None
    sgst_amount: float | None = None
    igst_amount: float | None = None
    other_tax_amount: float | None = None
    total_invoice_amount: float | None = None
    tax_code: str | None = None


class SapMmFields(BaseModel):
    po_item_number: str | None = None


class SapFicoFields(BaseModel):
    gl_account: str | None = None
    cost_center: str | None = None


class LineItemData(BaseModel):
    invoice_item_text: str | None = None
    hsn_sac_code: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    line_amount: float | None = None
    sap_mm_fields: SapMmFields = Field(default_factory=SapMmFields)
    sap_fico_fields: SapFicoFields = Field(default_factory=SapFicoFields)


class InvoicePayload(BaseModel):
    doc_id: str
    status: ProcessingStatus
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    sap_metadata: SapMetadata = Field(default_factory=SapMetadata)
    header_data: HeaderData
    financial_data: FinancialData
    line_item_data: list[LineItemData] = Field(default_factory=list)

    @model_validator(mode="after")
    def _guard_ready_for_sap(self) -> "InvoicePayload":
        """Downgrade to REQUIRES_MANUAL_REVIEW if required fields are missing."""
        if self.status == ProcessingStatus.READY_FOR_SAP:
            missing = [
                f for f in REQUIRED_FIELDS
                if getattr(self.financial_data, f, None) is None
                and getattr(self.header_data, f, None) is None
            ]
            if missing:
                logger.error(
                    "doc_id='%s' marked READY_FOR_SAP but missing %s. Downgrading.",
                    self.doc_id, missing,
                )
                return self.model_copy(
                    update={"status": ProcessingStatus.REQUIRES_MANUAL_REVIEW}
                )
        return self


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------

class DocumentMapper:
    """
    Piece 3: Maps raw extracted entities into a validated InvoicePayload.

    Input
    -----
    A list containing a SINGLE dict produced by InferenceWorker.process_document():
        [{"doc_metadata": {...}, "extracted_entities": [...]}]

    Output
    ------
    dict — InvoicePayload serialized via model_dump(mode="json").
    """

    def process_document(
        self,
        pages: list[dict[str, Any]],
        *,
        sap_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not pages:
            raise ValueError("process_document received an empty pages list.")

        doc_id = self._extract_doc_id(pages)
        logger.info("Mapping doc_id='%s' (%d page dict(s)).", doc_id, len(pages))

        best_hf, best_li = self._collect_entities(pages)

        normalised = self._normalise_header_financial(best_hf)
        normalised_items = self._normalise_line_items(best_li)

        overall_confidence = self._compute_confidence(best_hf)
        math_ok, math_detail = self._validate_math(normalised)
        logger.debug("Math check: %s", math_detail)

        status = self._determine_status(normalised, overall_confidence, math_ok)
        logger.info("doc_id='%s' -> %s (confidence=%.3f)", doc_id, status.value, overall_confidence)

        payload = self._assemble(
            doc_id, status, overall_confidence,
            SapMetadata(**(sap_overrides or {})),
            normalised, normalised_items,
        )
        return payload.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Entity collection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_doc_id(pages: list[dict[str, Any]]) -> str:
        doc_ids: set[str] = set()
        for page in pages:
            try:
                doc_ids.add(page["doc_metadata"]["doc_id"])
            except (KeyError, TypeError) as exc:
                raise ValueError(
                    f"Malformed page dict missing doc_metadata.doc_id: {exc}"
                ) from exc
        if len(doc_ids) > 1:
            raise ValueError(f"Mixed doc_ids in page list: {doc_ids}")
        return doc_ids.pop()

    @staticmethod
    def _collect_entities(
        pages: list[dict[str, Any]],
    ) -> tuple[dict[str, dict], dict[int, dict[str, dict]]]:
        best_hf: dict[str, dict[str, Any]] = {}
        best_li: dict[int, dict[str, dict[str, Any]]] = {}

        for page in pages:
            page_num = page.get("doc_metadata", {}).get("page_num", "?")
            entities = page.get("extracted_entities", [])

            if not isinstance(entities, list):
                continue

            for entity in entities:
                label: str = entity.get("label", "")
                confidence: float = float(entity.get("confidence", 0.0))
                text: str = entity.get("text", "")

                if label in _DISTRACTOR_LABELS or label not in _ALL_VALID_LABELS:
                    continue

                if label in LINE_ITEM_LABELS:
                    idx = int(entity.get("item_index") or 0)
                    group = best_li.setdefault(idx, {})
                    if label not in group or confidence > group[label]["confidence"]:
                        group[label] = {
                            "label": label, "text": text,
                            "confidence": confidence, "source_page": page_num,
                        }
                else:
                    if label not in best_hf or confidence > best_hf[label]["confidence"]:
                        best_hf[label] = {
                            "label": label, "text": text,
                            "confidence": confidence, "source_page": page_num,
                        }

        return best_hf, best_li

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalise_header_financial(
        self, best_entities: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {lbl: None for lbl in HEADER_LABELS | FINANCIAL_LABELS}

        for label, entity in best_entities.items():
            if label not in result:
                continue

            raw: str = entity.get("text", "")

            if label == "tax_regime":
                normalized_regime = raw.strip().upper()
                result[label] = normalized_regime if normalized_regime in {
                    "GST", "EXCISE", "INTERNATIONAL", "NONE"
                } else None

            elif label in FINANCIAL_LABELS:
                result[label] = self.parse_amount(raw)

            elif label == "invoice_date":
                match = _DATE_RE.search(raw)
                result[label] = self.parse_date(match.group(1) if match else raw)

            elif label in ("vendor_gstin", "buyer_gstin"):
                m = _GSTIN_RE.search(raw.replace(" ", "").upper())
                result[label] = m.group(1) if m else (raw.strip() or None)

            elif label == "invoice_number":
                m = _INVOICE_RE.search(raw)
                result[label] = m.group(1).strip() if m else (raw.strip() or None)

            elif label == "po_number":
                m = _PO_RE.search(raw)
                if m:
                    result[label] = m.group(1)
                else:
                    cleaned = raw.strip().strip(":-, ")
                    result[label] = cleaned if re.match(r'^\d{4,8}$', cleaned) else (raw.strip() or None)

            else:
                result[label] = raw.strip() or None

        return result

    def _normalise_line_items(
        self, best_line_items: dict[int, dict[str, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for idx in sorted(best_line_items.keys()):
            group = best_line_items[idx]

            def _text(lbl: str) -> str:
                return group[lbl]["text"] if lbl in group else ""

            result.append({
                "invoice_item_text": _text("item_description").strip() or None,
                "hsn_sac_code":      _text("hsn_sac_code").strip() or None,
                "quantity":          self.parse_amount(_text("item_quantity")),
                "unit_price":        self.parse_amount(_text("item_unit_price")),
                "line_amount":       self.parse_amount(_text("item_line_amount")),
                "po_item_number":    f"{(idx + 1) * 10:05d}",
            })
        return result

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def parse_date(raw: str) -> str | None:
        if not raw or not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        cleaned = re.sub(r'^(Date\s*:?\s*|Dt\.?\s*)', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'[\s\-:;,.]+$', '', cleaned)

        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

        m = re.search(r'(\d{2})\s+(\d{2})\s+(\d{4})', cleaned)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

        logger.warning("parse_date: could not parse '%s'.", cleaned)
        return None

    @staticmethod
    def validate_date_plausibility(
        iso_date: str | None,
        tax_regime: str | None = None,
    ) -> tuple[bool, str]:
        """
        Deterministic sanity check on a parsed ISO date, independent of
        whatever confidence score the model attached to it.

        This exists because a vision model can misread a single digit
        (e.g. "2025" -> "2013") and still produce a perfectly well-formed
        YYYY-MM-DD string — there's nothing syntactically wrong with
        "2013-06-26", so the earlier strptime-based validator lets it
        through every time. Math validation doesn't catch this either,
        since arithmetic on amounts has nothing to do with the date field.
        This is a separate, explicit check against real-world constraints:

        1. The date must parse and fall within [MIN_PLAUSIBLE_INVOICE_DATE,
           today + MAX_FUTURE_DAYS].
        2. If tax_regime is "GST", the date must be on/after
           GST_EFFECTIVE_DATE (2017-07-01) — GST did not exist before that,
           so a GST-regime invoice with an earlier date is a deterministic
           contradiction, not a judgment call.

        Returns (is_plausible, reason) — reason is always populated for
        logging, even when plausible.
        """
        if iso_date is None:
            return False, "invoice_date is missing"

        try:
            parsed = datetime.strptime(iso_date, "%Y-%m-%d").date()
        except ValueError:
            return False, f"invoice_date '{iso_date}' is not valid ISO format"

        min_date = datetime.strptime(MIN_PLAUSIBLE_INVOICE_DATE, "%Y-%m-%d").date()
        if parsed < min_date:
            return False, f"invoice_date {iso_date} predates plausible floor {MIN_PLAUSIBLE_INVOICE_DATE}"

        max_date = (datetime.now() + timedelta(days=MAX_FUTURE_DAYS)).date()
        if parsed > max_date:
            return False, f"invoice_date {iso_date} is more than {MAX_FUTURE_DAYS} days in the future"

        if tax_regime == "GST":
            gst_start = datetime.strptime(GST_EFFECTIVE_DATE, "%Y-%m-%d").date()
            if parsed < gst_start:
                return False, (
                    f"invoice_date {iso_date} predates GST effective date "
                    f"{GST_EFFECTIVE_DATE} but tax_regime is GST — contradiction, "
                    f"likely a misread year"
                )

        return True, f"invoice_date {iso_date} is plausible"

    @staticmethod
    def parse_amount(raw: str) -> float | None:
        if not raw or not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        cleaned = re.sub(r'(Rs\.?|INR|USD|EUR|\$|₹|€|£)', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace(',', '').replace("'", '').strip()

        if re.search(r'\d \d{2}$', cleaned):
            cleaned = cleaned.replace(' ', '.')
        parts = cleaned.split('.')
        if len(parts) == 3:
            cleaned = ''.join(parts[:-1]) + '.' + parts[-1]

        cleaned = re.sub(r'[^\d.\-]', '', cleaned)
        if not cleaned or cleaned in ('.', '-', '-.'):
            return None
        try:
            return float(cleaned)
        except ValueError:
            logger.warning("parse_amount: failed for '%s' (cleaned='%s').", raw, cleaned)
            return None

    # ------------------------------------------------------------------
    # Scoring / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(best_entities: dict[str, dict[str, Any]]) -> float:
        if not best_entities:
            return 0.0
        scores = [e["confidence"] for e in best_entities.values()]
        return round(sum(scores) / len(scores), 6) if scores else 0.0

    @staticmethod
    def _validate_math(normalised: dict[str, Any]) -> tuple[bool, str]:
        total = normalised.get("total_invoice_amount")
        base = normalised.get("base_amount")

        if total is None:
            return False, "total_invoice_amount missing — cannot validate."
        if base is None:
            return False, "base_amount missing — cannot validate."

        cgst = normalised.get("cgst_amount") or 0.0
        sgst = normalised.get("sgst_amount") or 0.0
        igst = normalised.get("igst_amount") or 0.0
        # FIX (vulnerability C): other_tax_amount covers non-GST tax lines
        # (Central Excise Duty, CST, VAT, service tax, international VAT/sales
        # tax). Previously the math check only summed GST components, so any
        # pre-GST or international invoice with real tax on it would compute
        # calculated = base only, fail the total check, and get bounced to
        # manual review even when the AI extracted every figure correctly.
        other_tax = normalised.get("other_tax_amount") or 0.0
        calculated = base + cgst + sgst + igst + other_tax

        no_tax = (
            normalised.get("cgst_amount") is None
            and normalised.get("sgst_amount") is None
            and normalised.get("igst_amount") is None
            and normalised.get("other_tax_amount") is None
        )

        effective_tolerance = max(MATH_TOLERANCE, abs(total) * 0.001)

        if no_tax:
            ok = abs(calculated - total) <= effective_tolerance
            tag = "PASS (0% tax)" if ok else "FAIL (no tax fields)"
            return ok, f"{tag} | base={base:.2f} total={total:.2f}"

        delta = abs(calculated - total)
        if delta <= effective_tolerance:
            regime = normalised.get("tax_regime") or "UNKNOWN"
            return True, f"PASS ({regime}) | calculated={calculated:.2f} total={total:.2f} delta={delta:.4f}"
        return False, f"FAIL | calculated={calculated:.2f} total={total:.2f} delta={delta:.4f}"

    @staticmethod
    def _determine_status(
        normalised: dict[str, Any],
        overall_confidence: float,
        math_ok: bool,
    ) -> ProcessingStatus:
        if not math_ok:
            return ProcessingStatus.REQUIRES_MANUAL_REVIEW
        if overall_confidence < CONFIDENCE_THRESHOLD:
            return ProcessingStatus.REQUIRES_MANUAL_REVIEW
        for f in REQUIRED_FIELDS:
            if normalised.get(f) is None:
                return ProcessingStatus.REQUIRES_MANUAL_REVIEW
        # FIX (vulnerability C): vendor_gstin is only mandatory for GST-regime
        # invoices. Pre-2017 Excise invoices and international invoices have
        # no GSTIN by definition, so requiring it unconditionally bottlenecked
        # every non-GST document into manual review regardless of extraction
        # quality.
        if normalised.get("tax_regime") == "GST":
            for f in REQUIRED_FIELDS_GST_ONLY:
                if normalised.get(f) is None:
                    return ProcessingStatus.REQUIRES_MANUAL_REVIEW

        # ANOMALY FIX: the model (observed with GPT-4o-mini, but not
        # exclusive to it) can misread a year digit and produce a
        # well-formed but factually wrong date — e.g. "2013-06-26" on an
        # invoice referencing a 2025-era Amazon order ID, with tax_regime
        # GST despite GST not existing in 2013. Neither the math check nor
        # the confidence score catches this, since both are about
        # arithmetic/extraction-quality, not real-world date plausibility.
        # This is a deterministic, code-enforced cross-check rather than
        # something left to the model's own self-reported confidence.
        #
        # Deliberately scoped to "date is PRESENT but implausible", not
        # "date is missing" — invoice_date isn't in REQUIRED_FIELDS, so a
        # missing date is a separate, pre-existing policy decision this fix
        # doesn't change. This check only catches a date that IS there and
        # is wrong, which is the actual failure mode observed in production.
        invoice_date = normalised.get("invoice_date")
        if invoice_date is not None:
            date_ok, date_reason = DocumentMapper.validate_date_plausibility(
                invoice_date,
                tax_regime=normalised.get("tax_regime"),
            )
            if not date_ok:
                logger.warning("Date implausibility check failed: %s", date_reason)
                return ProcessingStatus.REQUIRES_MANUAL_REVIEW

        return ProcessingStatus.READY_FOR_SAP

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _assemble(
        doc_id: str,
        status: ProcessingStatus,
        overall_confidence: float,
        sap_meta: SapMetadata,
        normalised: dict[str, Any],
        normalised_items: list[dict[str, Any]],
    ) -> InvoicePayload:
        header = HeaderData(
            vendor_name=normalised.get("vendor_name"),
            vendor_gstin=normalised.get("vendor_gstin"),
            buyer_name=normalised.get("buyer_name"),
            buyer_gstin=normalised.get("buyer_gstin"),
            invoice_number=normalised.get("invoice_number"),
            invoice_date=normalised.get("invoice_date"),
            po_number=normalised.get("po_number"),
        )
        financial = FinancialData(
            tax_regime=normalised.get("tax_regime"),
            base_amount=normalised.get("base_amount"),
            cgst_amount=normalised.get("cgst_amount"),
            sgst_amount=normalised.get("sgst_amount"),
            igst_amount=normalised.get("igst_amount"),
            other_tax_amount=normalised.get("other_tax_amount"),
            total_invoice_amount=normalised.get("total_invoice_amount"),
            tax_code=normalised.get("tax_code"),
        )
        line_items = [
            LineItemData(
                invoice_item_text=item.get("invoice_item_text"),
                hsn_sac_code=item.get("hsn_sac_code"),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                line_amount=item.get("line_amount"),
                sap_mm_fields=SapMmFields(po_item_number=item.get("po_item_number")),
                sap_fico_fields=SapFicoFields(),
            )
            for item in normalised_items
        ]
        return InvoicePayload(
            doc_id=doc_id,
            status=status,
            overall_confidence=overall_confidence,
            sap_metadata=sap_meta,
            header_data=header,
            financial_data=financial,
            line_item_data=line_items,
        )