package com.kaavian.invoice_api.sap;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Data;

import java.util.List;

/**
 * Exact JSON shape expected by SAP OData V2 API_SUPPLIERINVOICE_PROCESS_SRV.
 * Field names must match SAP's OData property names exactly (PascalCase).
 * Used for both the Postman mock and real S/4HANA Cloud.
 */
@Data
@Builder
public class SAPInvoicePayload {

    @JsonProperty("CompanyCode")
    private String companyCode;

    @JsonProperty("DocumentDate")
    private String documentDate;

    @JsonProperty("PostingDate")
    private String postingDate;

    @JsonProperty("SupplierInvoiceIDByInvcgParty")
    private String supplierInvoiceIDByInvcgParty;

    @JsonProperty("InvoicingParty")
    private String invoicingParty;

    @JsonProperty("DocumentCurrency")
    private String documentCurrency;

    @JsonProperty("InvoiceGrossAmount")
    private String invoiceGrossAmount;

    @JsonProperty("TaxDeterminationDate")
    private String taxDeterminationDate;

    @JsonProperty("to_SuplrInvcItemPurOrdRef")
    private List<SAPLineItem> lineItems;

    @Data
    @Builder
    public static class SAPLineItem {

        @JsonProperty("SupplierInvoiceItem")
        private String supplierInvoiceItem;

        @JsonProperty("PurchaseOrder")
        private String purchaseOrder;

        @JsonProperty("PurchaseOrderItem")
        private String purchaseOrderItem;

        @JsonProperty("DocumentCurrency")
        private String documentCurrency;

        @JsonProperty("SupplierInvoiceItemAmount")
        private String supplierInvoiceItemAmount;

        @JsonProperty("TaxCode")
        private String taxCode;
    }
}