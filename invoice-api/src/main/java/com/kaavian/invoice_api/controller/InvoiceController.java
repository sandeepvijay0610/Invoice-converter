package com.kaavian.invoice_api.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import com.kaavian.invoice_api.service.BlobStorageService;
import com.kaavian.invoice_api.messaging.MessageProducer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/invoices")
@CrossOrigin(origins = "http://localhost:5173")
public class InvoiceController {

    private final InvoiceRepository repository;
    private final BlobStorageService storageService;
    private final MessageProducer messageProducer;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public InvoiceController(InvoiceRepository repository, BlobStorageService storageService, MessageProducer messageProducer) {
        this.repository = repository;
        this.storageService = storageService;
        this.messageProducer = messageProducer;
    }

    // 1. Endpoint: Request a secure upload URL
    @PostMapping("/request-upload")
    public ResponseEntity<Map<String, String>> requestUpload(@RequestBody Map<String, String> body) {
        String filename = body.get("filename");
        if (filename == null || filename.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "filename is required"));
        }

        BlobStorageService.UploadTarget target = storageService.generateUploadTarget(filename);

        Invoice invoice = new Invoice();
        invoice.setDocId("INV-" + UUID.randomUUID().toString().substring(0, 8));

        // FIX (vulnerability A): persist only the bare blob name, never the
        // SAS-tokened URL. The token is handed to the browser in the response
        // below and is never written to the DB or queued — so it can't expire
        // out from under a backlogged worker.
        invoice.setFilePath(target.blobName());
        invoice.setStatus("PENDING");
        repository.save(invoice);

        return ResponseEntity.ok(Map.of(
                "id", invoice.getDocId(),
                "uploadUrl", target.uploadUrl()
        ));
    }

    // 2. Endpoint: Trigger the AI processing after the frontend finishes uploading
    @PostMapping("/{id}/process")
    public ResponseEntity<?> triggerProcessing(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }

        // FIX: the browser's upload PUT is sent with mode:'no-cors' (see
        // BlobStorageService.blobExists' javadoc), so a failed upload never
        // throws on the frontend and this endpoint used to get called
        // regardless. Verify the blob actually landed before queueing —
        // this is the first point in the flow that can reliably tell.
        if (!storageService.blobExists(invoice.getFilePath())) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "Upload not found in storage — the file may not have finished uploading. Please try uploading again."
            ));
        }

        // invoice.getFilePath() is now just the blob name (e.g.
        // "550e8400-...-clean.pdf"), not a URL — the worker resolves it via
        // the Azure SDK using its own connection string.
        messageProducer.sendExtractionRequest(invoice.getDocId(), invoice.getFilePath());

        invoice.setStatus("PROCESSING");
        repository.save(invoice);

        return ResponseEntity.ok(Map.of("message", "Processing started for " + id));
    }

    // 3. Endpoint: List invoices for the dashboard, with optional status
    // filter and pagination. Without this, the frontend has no way to show
    // a table of invoices at all — it would otherwise need direct DB access.
    @GetMapping
    public ResponseEntity<Map<String, Object>> listInvoices(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        // Cap page size so a frontend bug or malicious query can't force a
        // huge unpaginated pull from the DB.
        int safeSize = Math.min(Math.max(size, 1), 100);
        Pageable pageable = PageRequest.of(Math.max(page, 0), safeSize, Sort.by("createdAt").descending());

        Page<Invoice> result = (status != null && !status.isBlank())
                ? repository.findByStatus(status, pageable)
                : repository.findAllByOrderByCreatedAtDesc(pageable);

        List<Map<String, Object>> items = result.getContent().stream()
                .map(this::toSummaryDto)
                .toList();

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("items", items);
        response.put("page", result.getNumber());
        response.put("size", result.getSize());
        response.put("totalItems", result.getTotalElements());
        response.put("totalPages", result.getTotalPages());

        return ResponseEntity.ok(response);
    }

    // 4. Endpoint: Get a single invoice's full detail, including the parsed
    // extracted_payload (header/financial/line-item data from the AI
    // pipeline). Needed for an invoice detail view and for the frontend to
    // poll status after upload instead of guessing when processing is done.
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> getInvoice(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(toDetailDto(invoice));
    }

    // 5. Endpoint: Retry a stuck invoice. Useful for RATE_LIMITED invoices
    // that exhausted the worker's own requeue budget (see
    // MAX_RATE_LIMIT_REQUEUES in main.py) and for FAILED invoices a human
    // wants to re-attempt after fixing whatever caused the failure (e.g. a
    // transient Azurite/network blip). This is just triggerProcessing under
    // a clearer name for this use case — same underlying action.
    @PostMapping("/{id}/retry")
    public ResponseEntity<Map<String, String>> retryInvoice(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }

        if (invoice.getFilePath() == null || invoice.getFilePath().isBlank()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "Invoice has no associated file_path to reprocess"
            ));
        }

        messageProducer.sendExtractionRequest(invoice.getDocId(), invoice.getFilePath());
        invoice.setStatus("PROCESSING");
        repository.save(invoice);

        return ResponseEntity.ok(Map.of(
                "id", invoice.getDocId(),
                "status", "PROCESSING",
                "message", "Retry triggered for " + id
        ));
    }

    // ------------------------------------------------------------------
    // DTO helpers
    // ------------------------------------------------------------------

    /**
     * Lightweight shape for the list view — omits the full extracted_payload
     * JSON to keep list responses small, since a dashboard table doesn't
     * need line items, just headline fields.
     */
    private Map<String, Object> toSummaryDto(Invoice invoice) {
        Map<String, Object> dto = new LinkedHashMap<>();
        dto.put("id", invoice.getDocId());
        dto.put("status", invoice.getStatus());
        dto.put("vendorName", invoice.getVendorName());
        dto.put("invoiceNumber", invoice.getInvoiceNumber());
        dto.put("totalAmount", invoice.getTotalAmount());
        dto.put("companyCode", invoice.getCompanyCode());
        dto.put("createdAt", invoice.getCreatedAt());
        return dto;
    }

    /**
     * Full shape for the detail view — includes the parsed extracted_payload
     * as a real JSON object (not a string) so the frontend doesn't need to
     * JSON.parse() it client-side.
     */
    private Map<String, Object> toDetailDto(Invoice invoice) {
        Map<String, Object> dto = new LinkedHashMap<>();
        dto.put("id", invoice.getDocId());
        dto.put("status", invoice.getStatus());
        dto.put("filePath", invoice.getFilePath());
        dto.put("vendorName", invoice.getVendorName());
        dto.put("invoiceNumber", invoice.getInvoiceNumber());
        dto.put("totalAmount", invoice.getTotalAmount());
        dto.put("companyCode", invoice.getCompanyCode());
        dto.put("createdAt", invoice.getCreatedAt());

        JsonNode parsedPayload = null;
        String rawPayload = invoice.getExtractedPayload();
        if (rawPayload != null && !rawPayload.isBlank()) {
            try {
                parsedPayload = objectMapper.readTree(rawPayload);
            } catch (Exception e) {
                // Malformed JSON in the column shouldn't crash the whole
                // response — surface it as null and let the frontend show
                // "no extraction data available" rather than a 500.
                parsedPayload = null;
            }
        }
        dto.put("extractedPayload", parsedPayload);

        return dto;
    }
}