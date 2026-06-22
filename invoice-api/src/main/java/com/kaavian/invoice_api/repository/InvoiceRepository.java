package com.kaavian.invoice_api.repository;

import com.kaavian.invoice_api.entity.Invoice;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import java.util.UUID;

@Repository
public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    Invoice findByDocId(String docId);

    @Query("SELECT i FROM Invoice i WHERE i.userId = :userId ORDER BY i.createdAt DESC")
    Page<Invoice> findAllByUserId(@Param("userId") UUID userId, Pageable pageable);

    @Query("SELECT i FROM Invoice i WHERE i.userId = :userId AND i.status = :status ORDER BY i.createdAt DESC")
    Page<Invoice> findByUserIdAndStatus(@Param("userId") UUID userId, @Param("status") String status, Pageable pageable);

    Page<Invoice> findByStatus(String status, Pageable pageable);
    Page<Invoice> findAllByOrderByCreatedAtDesc(Pageable pageable);
}