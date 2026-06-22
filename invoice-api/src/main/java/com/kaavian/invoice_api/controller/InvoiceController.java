package com.kaavian.invoice_api.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.entity.User;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import com.kaavian.invoice_api.repository.UserRepository;
import com.kaavian.invoice_api.service.BlobStorageService;
import com.kaavian.invoice_api.messaging.MessageProducer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.server.ResponseStatusException;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.Base64;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "http://localhost:5173", methods = {RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT, RequestMethod.DELETE, RequestMethod.OPTIONS})
public class InvoiceController {

    private final InvoiceRepository repository;
    private final UserRepository userRepository;
    private final BlobStorageService storageService;
    private final MessageProducer messageProducer;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public InvoiceController(InvoiceRepository repository, UserRepository userRepository,
                             BlobStorageService storageService, MessageProducer messageProducer) {
        this.repository = repository;
        this.userRepository = userRepository;
        this.storageService = storageService;
        this.messageProducer = messageProducer;
    }

    private UUID getCurrentUserId() {
        var request = ((ServletRequestAttributes) RequestContextHolder.currentRequestAttributes()).getRequest();
        User user = (User) request.getAttribute("authenticatedUser");
        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Not authenticated");
        }
        return user.getId();
    }

    private boolean isAdmin() {
        var request = ((ServletRequestAttributes) RequestContextHolder.currentRequestAttributes()).getRequest();
        User user = (User) request.getAttribute("authenticatedUser");
        return user != null && "admin".equals(user.getRole());
    }

    @PostMapping("/auth/login")
    public ResponseEntity<Map<String, String>> login(@RequestHeader(value = "Authorization", required = false) String authHeader) {
        if (authHeader == null || !authHeader.startsWith("Basic ")) {
            return ResponseEntity.status(401).body(Map.of("error", "Missing credentials"));
        }

        String base64Credentials = authHeader.substring(6);
        String credentials = new String(Base64.getDecoder().decode(base64Credentials));
        String[] parts = credentials.split(":", 2);

        if (parts.length != 2) {
            return ResponseEntity.status(401).body(Map.of("error", "Invalid credentials format"));
        }

        var userOpt = userRepository.findByUsername(parts[0]);
        if (userOpt.isEmpty() || !userOpt.get().getPassword().equals(parts[1])) {
            return ResponseEntity.status(401).body(Map.of("error", "Invalid username or password"));
        }

        User user = userOpt.get();
        return ResponseEntity.ok(Map.of(
            "username", user.getUsername(),
            "tenantName", user.getTenantName(),
            "role", user.getRole()
        ));
    }

    @PostMapping("/invoices/request-upload")
    public ResponseEntity<Map<String, String>> requestUpload(@RequestBody Map<String, String> body) {
        String filename = body.get("filename");
        if (filename == null || filename.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "filename is required"));
        }

        BlobStorageService.UploadTarget target = storageService.generateUploadTarget(filename);

        Invoice invoice = new Invoice();
        invoice.setDocId("INV-" + UUID.randomUUID().toString().substring(0, 8));
        invoice.setFilePath(target.blobName());
        invoice.setStatus("PENDING");
        invoice.setUserId(getCurrentUserId());
        repository.save(invoice);

        return ResponseEntity.ok(Map.of(
                "id", invoice.getDocId(),
                "uploadUrl", target.uploadUrl()
        ));
    }

    @PostMapping("/invoices/{id}/process")
    public ResponseEntity<?> triggerProcessing(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }

        if (!storageService.blobExists(invoice.getFilePath())) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "Upload not found in storage. Please try uploading again."
            ));
        }

        messageProducer.sendExtractionRequest(invoice.getDocId(), invoice.getFilePath());
        invoice.setStatus("PROCESSING");
        repository.save(invoice);

        return ResponseEntity.ok(Map.of("message", "Processing started for " + id));
    }

    @GetMapping("/invoices")
    public ResponseEntity<Map<String, Object>> listInvoices(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        int safeSize = Math.min(Math.max(size, 1), 100);
        Pageable pageable = PageRequest.of(Math.max(page, 0), safeSize, Sort.by("createdAt").descending());

        UUID userId = getCurrentUserId();
        Page<Invoice> result;

        if (isAdmin() && (status == null || status.isBlank())) {
            result = repository.findAllByOrderByCreatedAtDesc(pageable);
        } else if (isAdmin()) {
            result = repository.findByStatus(status, pageable);
        } else if (status != null && !status.isBlank()) {
            result = repository.findByUserIdAndStatus(userId, status, pageable);
        } else {
            result = repository.findAllByUserId(userId, pageable);
        }

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

    @GetMapping("/invoices/{id}")
    public ResponseEntity<Map<String, Object>> getInvoice(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(toDetailDto(invoice));
    }

    @PostMapping("/invoices/{id}/retry")
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

    @DeleteMapping("/invoices/{id}")
    public ResponseEntity<Map<String, String>> deleteInvoice(@PathVariable String id) {
        Invoice invoice = repository.findByDocId(id);
        if (invoice == null) {
            return ResponseEntity.notFound().build();
        }

        if (invoice.getFilePath() != null && !invoice.getFilePath().isBlank()) {
            storageService.deleteBlob(invoice.getFilePath());
        }

        repository.delete(invoice);

        return ResponseEntity.ok(Map.of(
            "id", id,
            "message", "Invoice deleted successfully"
        ));
    }

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
                parsedPayload = null;
            }
        }
        dto.put("extractedPayload", parsedPayload);

        return dto;
    }
}