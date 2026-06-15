package com.kaavian.invoice_api.repository;

import com.kaavian.invoice_api.entity.Invoice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    Invoice findByDocId(String docId);
}