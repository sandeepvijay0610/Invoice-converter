package com.kaavian.invoice_api.sap;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.util.Map;

/**
 * Handles the HTTP call to SAP OData V2 API_SUPPLIERINVOICE_PROCESS_SRV.
 *
 * Currently targets the Postman Mock Server. Switching to real S/4HANA Cloud
 * only requires changing sap.base-url and sap.api-key in application.properties
 * — no code changes needed.
 *
 * Flow:
 *   1. Map Invoice → SAPInvoicePayload (via SAPInvoiceMapper)
 *   2. POST to configured SAP API Path
 *   3. Parse SAP's response to extract the created SupplierInvoice document number
 *   4. Update Invoice status → SAP_EXPORTED and store the SAP document ID
 */
@Service
public class SAPIntegrationService {

    private final WebClient webClient;
    private final SAPInvoiceMapper mapper;
    private final InvoiceRepository invoiceRepository;
    private final ObjectMapper objectMapper;
    private final String sapApiPath;
    private final String sapApiKey;

    public SAPIntegrationService(
            WebClient.Builder webClientBuilder,
            SAPInvoiceMapper mapper,
            InvoiceRepository invoiceRepository,
            ObjectMapper objectMapper,
            @Value("${sap.base-url}") String sapBaseUrl,
            @Value("${sap.api-path:/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice}") String sapApiPath,
            @Value("${sap.api-key:}") String sapApiKey) {

        this.mapper = mapper;
        this.invoiceRepository = invoiceRepository;
        this.objectMapper = objectMapper;
        this.sapApiPath = sapApiPath;
        this.sapApiKey = sapApiKey;

        // Build the WebClient pointed at the SAP base URL
        this.webClient = webClientBuilder
                .baseUrl(sapBaseUrl)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                // SAP OData V2 requires this header to get JSON back instead of XML
                .defaultHeader("sap-client", "100")
                .build();
    }

    /**
     * Exports the invoice to SAP and returns a result map with:
     *   - sapDocumentId: the SupplierInvoice number SAP assigned
     *   - status: "SAP_EXPORTED"
     *   - message: human-readable summary
     */
    public Map<String, String> exportToSAP(Invoice invoice) {
        // Step 1: Map to SAP payload
        SAPInvoicePayload payload = mapper.map(invoice);

        try {
            // Step 2: POST to SAP OData endpoint
            String responseBody = webClient.post()
                    .uri(sapApiPath)
                    .headers(headers -> {
                        if (sapApiKey != null && !sapApiKey.isBlank()) {
                            headers.set("APIKey", sapApiKey);
                        }
                    })
                    .bodyValue(payload)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(); // blocking is fine here — this is a triggered, user-initiated action

            // Step 3: Parse SAP response to get the document number
            String sapDocumentId = extractSapDocumentId(responseBody);

            // Step 4: Update the invoice record
            invoice.setStatus("SAP_EXPORTED");
            invoice.setSapDocumentId(sapDocumentId);
            invoiceRepository.save(invoice);

            return Map.of(
                    "sapDocumentId", sapDocumentId,
                    "status", "SAP_EXPORTED",
                    "message", "Successfully exported to SAP. Document: " + sapDocumentId
            );

        } catch (WebClientResponseException e) {
            // SAP returned a 4xx/5xx — surface the SAP error body for debugging
            String sapError = e.getResponseBodyAsString();
            throw new SAPExportException(
                    "SAP rejected the invoice: HTTP " + e.getStatusCode() + " — " + sapError, e);

        } catch (Exception e) {
            throw new SAPExportException("Failed to connect to SAP: " + e.getMessage(), e);
        }
    }

    // -------------------------------------------------------------------------
    // Parse the SAP response
    // -------------------------------------------------------------------------

    /**
     * SAP OData V2 wraps responses in a "d" envelope:
     * { "d": { "SupplierInvoice": "5105609876", ... } }
     *
     * Postman mock returns the same shape. Falls back to "UNKNOWN" if parsing fails.
     */
    private String extractSapDocumentId(String responseBody) {
        if (responseBody == null || responseBody.isBlank()) return "UNKNOWN";
        try {
            JsonNode root = objectMapper.readTree(responseBody);
            
            // Try SAP OData V2 envelope first
            JsonNode d = root.path("d");
            if (!d.isMissingNode()) {
                String id = d.path("SupplierInvoice").asText(null);
                if (id != null && !id.isBlank()) return id;
            }
            
            // Try flat response (Postman mock may return this)
            String id = root.path("SupplierInvoice").asText(null);
            if (id != null && !id.isBlank()) return id;

            return "UNKNOWN";
        } catch (Exception e) {
            return "UNKNOWN";
        }
    }

    // -------------------------------------------------------------------------
    // Custom exception
    // -------------------------------------------------------------------------

    public static class SAPExportException extends RuntimeException {
        public SAPExportException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}