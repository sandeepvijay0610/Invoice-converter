package com.kaavian.invoice_api.controller;

import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import com.kaavian.invoice_api.service.BlobStorageService;
import com.kaavian.invoice_api.messaging.MessageProducer;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/invoices")
@CrossOrigin(origins = "*")
public class InvoiceController {

    private final InvoiceRepository repository;
    private final BlobStorageService storageService;
    private final MessageProducer messageProducer;

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
    public ResponseEntity<String> triggerProcessing(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }

        // invoice.getFilePath() is now just the blob name (e.g.
        // "550e8400-...-clean.pdf"), not a URL — the worker resolves it via
        // the Azure SDK using its own connection string.
        messageProducer.sendExtractionRequest(invoice.getDocId(), invoice.getFilePath());

        invoice.setStatus("PROCESSING");
        repository.save(invoice);

        return ResponseEntity.ok("Processing started for " + id);
    }
}