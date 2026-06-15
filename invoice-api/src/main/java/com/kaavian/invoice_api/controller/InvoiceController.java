package com.kaavian.invoice_api.controller;

import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import com.kaavian.invoice_api.service.BlobStorageService;
import com.kaavian.invoice_api.messaging.MessageProducer;
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
    public Map<String, String> requestUpload(@RequestBody Map<String, String> body) {
        String filename = body.get("filename");
        
        // Generate the secure SAS token URL
        String uploadUrl = storageService.generateUploadUrl(filename);
        
        // Save the pending invoice in PostgreSQL
        // Store the FULL URL with SAS token so the Python worker can download it
        Invoice invoice = new Invoice();
        invoice.setDocId("INV-" + UUID.randomUUID().toString().substring(0, 8));
        invoice.setFilePath(uploadUrl);  // Full URL with SAS token
        invoice.setStatus("PENDING");
        repository.save(invoice);

        return Map.of("id", invoice.getDocId(), "uploadUrl", uploadUrl);
    }

    // 2. Endpoint: Trigger the AI processing after React finishes the upload
    @PostMapping("/{id}/process")
    public String triggerProcessing(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        
        // Send the full URL (with SAS token) to RabbitMQ so Python can download
        messageProducer.sendExtractionRequest(invoice.getDocId(), invoice.getFilePath());
        
        invoice.setStatus("PROCESSING");
        repository.save(invoice);
        
        return "Processing started for " + id;
    }
}