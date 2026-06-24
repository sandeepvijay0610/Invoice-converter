package com.kaavian.invoice_api.sap;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kaavian.invoice_api.entity.Invoice;
import org.springframework.stereotype.Component;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * Translates the flat Invoice entity (populated by Python AI workers) into
 * the deeply nested SAP OData V2 JSON structure required by
 * API_SUPPLIERINVOICE_PROCESS_SRV / POST /A_SupplierInvoice.
 *
 * Strategy:
 *   1. Use structured fields on Invoice entity first (invoiceNumber, vendorName, etc.)
 *   2. Fall back to extractedPayload JSON for any field not promoted to a column
 *   3. Apply SAP-safe defaults for required fields the AI didn't extract
 */
@Component
public class SAPInvoiceMapper {

    private static final DateTimeFormatter SAP_DATE = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");
    private static final String DEFAULT_CURRENCY = "INR";
    private static final String DEFAULT_COMPANY_CODE = "1000";
    private static final String DEFAULT_TAX_CODE = "V1";
    private static final String DEFAULT_PO_ITEM = "10";

    private final ObjectMapper objectMapper;

    public SAPInvoiceMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public SAPInvoicePayload map(Invoice invoice) {
        // Parse the raw JSON blob the Python worker stored
        JsonNode payload = parsePayload(invoice.getExtractedPayload());

        String today = LocalDate.now().atStartOfDay().format(SAP_DATE);
        String documentDate = extractDate(payload, "invoice_date", today);

        // Line items — try to map extracted items, fall back to a single derived line
        List<SAPInvoicePayload.SAPLineItem> lineItems = buildLineItems(invoice, payload);

        return SAPInvoicePayload.builder()
                // CompanyCode: prefer entity field, fall back to payload, then default
                .companyCode(firstNonBlank(
                        invoice.getCompanyCode(),
                        textOrNull(payload, "company_code"),
                        DEFAULT_COMPANY_CODE))

                // DocumentDate: date printed on the invoice
                .documentDate(documentDate)

                // PostingDate: today (when we're posting to SAP)
                .postingDate(today)

                // SAP's vendor invoice reference number
                .supplierInvoiceIDByInvcgParty(firstNonBlank(
                        invoice.getInvoiceNumber(),
                        textOrNull(payload, "invoice_number"),
                        invoice.getDocId()))   // our internal ID as last resort

                // Vendor GSTIN / SAP supplier ID
                .invoicingParty(firstNonBlank(
                        invoice.getVendorName(),
                        textOrNull(payload, "vendor_gstin"),
                        textOrNull(payload, "vendor_name"),
                        "UNKNOWN_VENDOR"))

                // Currency
                .documentCurrency(firstNonBlank(
                        textOrNull(payload, "currency"),
                        DEFAULT_CURRENCY))

                // Gross amount — BigDecimal → plain string, no scientific notation
                .invoiceGrossAmount(invoice.getTotalAmount() != null
                        ? invoice.getTotalAmount().toPlainString()
                        : firstNonBlank(textOrNull(payload, "total_amount"), "0.00"))

                .taxDeterminationDate(documentDate)
                .lineItems(lineItems)
                .build();
    }

    // -------------------------------------------------------------------------
    // Line item construction
    // -------------------------------------------------------------------------

    private List<SAPInvoicePayload.SAPLineItem> buildLineItems(Invoice invoice, JsonNode payload) {
        List<SAPInvoicePayload.SAPLineItem> items = new ArrayList<>();

        // Try to read line_items array from the AI-extracted payload
        JsonNode lineItemsNode = payload != null ? payload.get("line_items") : null;

        if (lineItemsNode != null && lineItemsNode.isArray() && !lineItemsNode.isEmpty()) {
            int itemIndex = 1;
            for (JsonNode item : lineItemsNode) {
                items.add(SAPInvoicePayload.SAPLineItem.builder()
                        .supplierInvoiceItem(String.valueOf(itemIndex++))
                        .purchaseOrder(firstNonBlank(
                                textOrNull(item, "purchase_order"),
                                textOrNull(item, "po_number"),
                                "NO-PO"))
                        .purchaseOrderItem(firstNonBlank(
                                textOrNull(item, "purchase_order_item"),
                                DEFAULT_PO_ITEM))
                        .documentCurrency(firstNonBlank(
                                textOrNull(item, "currency"),
                                textOrNull(payload, "currency"),
                                DEFAULT_CURRENCY))
                        .supplierInvoiceItemAmount(firstNonBlank(
                                textOrNull(item, "amount"),
                                textOrNull(item, "line_total"),
                                "0.00"))
                        .taxCode(firstNonBlank(
                                textOrNull(item, "tax_code"),
                                DEFAULT_TAX_CODE))
                        .build());
            }
        } else {
            // No line items extracted — create a single line from the invoice total
            // SAP requires at least one line item to create a supplier invoice
            items.add(SAPInvoicePayload.SAPLineItem.builder()
                    .supplierInvoiceItem("1")
                    .purchaseOrder(firstNonBlank(textOrNull(payload, "purchase_order"), "NO-PO"))
                    .purchaseOrderItem(DEFAULT_PO_ITEM)
                    .documentCurrency(firstNonBlank(textOrNull(payload, "currency"), DEFAULT_CURRENCY))
                    .supplierInvoiceItemAmount(invoice.getTotalAmount() != null
                            ? invoice.getTotalAmount().toPlainString()
                            : "0.00")
                    .taxCode(DEFAULT_TAX_CODE)
                    .build());
        }

        return items;
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private JsonNode parsePayload(String rawJson) {
        if (rawJson == null || rawJson.isBlank()) return null;
        try {
            return objectMapper.readTree(rawJson);
        } catch (Exception e) {
            return null;
        }
    }

    private String textOrNull(JsonNode node, String field) {
        if (node == null) return null;
        JsonNode child = node.get(field);
        if (child == null || child.isNull() || child.asText().isBlank()) return null;
        return child.asText().trim();
    }

    private String extractDate(JsonNode payload, String field, String fallback) {
        String raw = textOrNull(payload, field);
        if (raw == null) return fallback;
        // If it already looks like an ISO datetime, return as-is
        if (raw.contains("T")) return raw;
        // Try to parse common date formats and convert to SAP format
        try {
            // e.g. "2026-05-15" → "2026-05-15T00:00:00"
            return LocalDate.parse(raw).atStartOfDay().format(SAP_DATE);
        } catch (Exception e) {
            return fallback;
        }
    }

    /** Returns the first non-null, non-blank string from the candidates. */
    private String firstNonBlank(String... candidates) {
        for (String s : candidates) {
            if (s != null && !s.isBlank()) return s;
        }
        return "";
    }
}