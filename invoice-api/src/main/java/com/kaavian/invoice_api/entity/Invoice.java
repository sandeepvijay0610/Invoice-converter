package com.kaavian.invoice_api.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "invoices")
@Data // Lombok automatically generates Getters, Setters, and toString() for us
@NoArgsConstructor
@AllArgsConstructor
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "doc_id", unique = true, nullable = false)
    private String docId; // e.g., INV-2026-00123

    @Column(name = "file_path", nullable = false)
    private String filePath; // The Azurite Object Storage URL

    @Column(nullable = false)
    private String status = "PENDING"; // PENDING, PROCESSING, READY_FOR_SAP, REQUIRES_MANUAL_REVIEW

    // Quick query fields so your React Dashboard can filter and sort fast
    @Column(name = "vendor_name")
    private String vendorName;

    @Column(name = "invoice_number")
    private String invoiceNumber;

    @Column(name = "total_amount")
    private BigDecimal totalAmount;

    @Column(name = "company_code")
    private String companyCode;

    // The "Goated" PostgreSQL feature: Native JSONB storage
    // This holds the exact dictionary your Python worker spits out
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "extracted_payload", columnDefinition = "jsonb")
    private String extractedPayload; 

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt = LocalDateTime.now();
}