package com.kaavian.invoice_api.repository;

import com.kaavian.invoice_api.entity.Invoice;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    Invoice findByDocId(String docId);

    // Used by GET /api/invoices for the dashboard list view, with optional
    // status filtering (PENDING, PROCESSING, READY_FOR_SAP,
    // REQUIRES_MANUAL_REVIEW, RATE_LIMITED, FAILED) and pagination so the
    // frontend doesn't have to pull every row at once as volume grows.
    Page<Invoice> findByStatus(String status, Pageable pageable);

    Page<Invoice> findAllByOrderByCreatedAtDesc(Pageable pageable);
}