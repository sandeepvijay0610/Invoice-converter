package com.kaavian.invoice_api.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "invoices")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "doc_id", unique = true, nullable = false)
    private String docId;

    @Column(name = "file_path", nullable = false)
    private String filePath;

    @Column(nullable = false)
    private String status = "PENDING";

    @Column(name = "vendor_name")
    private String vendorName;

    @Column(name = "invoice_number")
    private String invoiceNumber;

    @Column(name = "total_amount")
    private BigDecimal totalAmount;

    @Column(name = "company_code")
    private String companyCode;

    @Column(name = "user_id")
    private UUID userId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "extracted_payload", columnDefinition = "jsonb")
    private String extractedPayload;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt = LocalDateTime.now();
}