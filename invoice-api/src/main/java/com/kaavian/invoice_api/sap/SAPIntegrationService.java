package com.kaavian.invoice_api.sap;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.util.Map;

@Service
public class SAPIntegrationService {

    private static final Logger log = LoggerFactory.getLogger(SAPIntegrationService.class);

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

        this.webClient = webClientBuilder
                .baseUrl(sapBaseUrl)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                // SAP OData V2 requires this to return JSON instead of XML
                .defaultHeader("sap-client", "100")
                .build();
    }

    public Map<String, String> exportToSAP(Invoice invoice) {
        SAPInvoicePayload payload = mapper.map(invoice);
        log.info("Exporting invoice {} to SAP endpoint {}", invoice.getDocId(), sapApiPath);

        try {
            String responseBody = webClient.post()
                    .uri(sapApiPath)
                    .headers(headers -> {
                        if (sapApiKey != null && !sapApiKey.isBlank()) {
                            // Postman mock and SAP API Hub both use x-api-key
                            headers.set("x-api-key", sapApiKey);
                        }
                    })
                    .bodyValue(payload)
                    .retrieve()
                    .bodyToMono(String.class)
                    // Blocking is intentional — this is a user-triggered action, not a background task
                    .block();

            String sapDocumentId = extractSapDocumentId(responseBody);
            log.info("SAP export successful for invoice {}. SAP document: {}", invoice.getDocId(), sapDocumentId);

            // SNAKE_CASE status — consistent with all other statuses in the system
            invoice.setStatus("SAP_EXPORTED");
            invoice.setSapDocumentId(sapDocumentId);
            invoiceRepository.save(invoice);

            return Map.of(
                    "sapDocumentId", sapDocumentId,
                    "status", "SAP_EXPORTED",
                    "message", "Successfully exported to SAP. Document: " + sapDocumentId
            );

        } catch (WebClientResponseException e) {
            log.error("SAP rejected invoice {}: HTTP {} — {}",
                    invoice.getDocId(), e.getStatusCode(), e.getResponseBodyAsString());
            throw new SAPExportException(
                    "SAP rejected the invoice: HTTP " + e.getStatusCode() + " — " + e.getResponseBodyAsString(), e);
        } catch (Exception e) {
            log.error("Failed to connect to SAP for invoice {}: {}", invoice.getDocId(), e.getMessage());
            throw new SAPExportException("Failed to connect to SAP: " + e.getMessage(), e);
        }
    }

    // SAP OData V2 wraps the response in a "d" envelope:
    // { "d": { "SupplierInvoice": "5105609876", ... } }
    // Postman mock may return a flat shape. Falls back to "UNKNOWN" if neither matches.
    private String extractSapDocumentId(String responseBody) {
        if (responseBody == null || responseBody.isBlank()) return "UNKNOWN";
        try {
            JsonNode root = objectMapper.readTree(responseBody);
            JsonNode d = root.path("d");
            if (!d.isMissingNode()) {
                String id = d.path("SupplierInvoice").asText(null);
                if (id != null && !id.isBlank()) return id;
            }
            String id = root.path("SupplierInvoice").asText(null);
            if (id != null && !id.isBlank()) return id;
            return "UNKNOWN";
        } catch (Exception e) {
            log.warn("Could not parse SAP document ID from response: {}", e.getMessage());
            return "UNKNOWN";
        }
    }

    public static class SAPExportException extends RuntimeException {
        public SAPExportException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}