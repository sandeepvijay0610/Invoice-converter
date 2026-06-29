package com.kaavian.invoice_api.controller;

import com.kaavian.invoice_api.entity.Invoice;
import com.kaavian.invoice_api.repository.InvoiceRepository;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.io.PrintWriter;
import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/odata/v4/Analytics")
public class SAPAnalyticsController {

    private final InvoiceRepository invoiceRepository;

    public SAPAnalyticsController(InvoiceRepository invoiceRepository) {
        this.invoiceRepository = invoiceRepository;
    }

    // 1. OData V2 Service Document
    @GetMapping(value = "", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> getServiceDocument() {
        Map<String, Object> response = new HashMap<>();
        Map<String, Object> entitySets = new HashMap<>();
        entitySets.put("EntitySets", List.of("Invoices"));
        response.put("d", entitySets);
        return response;
    }

    // 2. OData V2 Metadata XML (Using the exact namespaces SAP expects)
    @GetMapping(value = "/$metadata")
    public void getMetadata(HttpServletResponse response) throws IOException {
        String xml = "<?xml version=\"1.0\" encoding=\"utf-8\"?>" +
               "<edmx:Edmx Version=\"1.0\" xmlns:edmx=\"http://schemas.microsoft.com/ado/2007/06/edmx\">" +
               "  <edmx:DataServices m:DataServiceVersion=\"2.0\" xmlns:m=\"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata\">" +
               "    <Schema Namespace=\"Analytics\" xmlns=\"http://schemas.microsoft.com/ado/2008/09/edm\">" +
               "      <EntityType Name=\"Invoice\">" +
               "        <Key><PropertyRef Name=\"id\" /></Key>" +
               "        <Property Name=\"id\" Type=\"Edm.Int32  \" Nullable=\"false\" />" +
               "        <Property Name=\"docId\" Type=\"Edm.String\" />" +
               "        <Property Name=\"vendorName\" Type=\"Edm.String\" />" +
               "        <Property Name=\"invoiceNumber\" Type=\"Edm.String\" />" +
               "        <Property Name=\"totalAmount\" Type=\"Edm.Double\" />" +
               "        <Property Name=\"companyCode\" Type=\"Edm.String\" />" +
               "        <Property Name=\"status\" Type=\"Edm.String\" />" +
               "      </EntityType>" +
               "      <EntityContainer Name=\"Container\" m:IsDefaultEntityContainer=\"true\">" +
               "        <EntitySet Name=\"Invoices\" EntityType=\"Analytics.Invoice\" />" +
               "      </EntityContainer>" +
               "    </Schema>" +
               "  </edmx:DataServices>" +
               "</edmx:Edmx>";
        
        response.setContentType("application/xml;charset=utf-8");
        response.getWriter().write(xml);
    }
// 3. OData V2 JSON Data Array (Bulletproof Enterprise Version)
    @GetMapping(value = "/Invoices", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> getInvoices() {
        List<Invoice> invoices = invoiceRepository.findAll();
        
        List<Map<String, Object>> cleanInvoices = invoices.stream().map(inv -> {
            Map<String, Object> map = new HashMap<>();
            
            // SAP strictly requires type AND a unique URI to index the row
            Map<String, String> metadata = new HashMap<>();
            metadata.put("type", "Analytics.Invoice");
            metadata.put("uri", "Invoices(" + inv.getId() + ")"); // Tells SAP exactly where this row lives
            map.put("__metadata", metadata);
            
            // Map fields, providing safe fallbacks just in case Python left any nulls
            map.put("id", inv.getId());
            map.put("docId", inv.getDocId() != null ? inv.getDocId() : "");
            map.put("vendorName", inv.getVendorName() != null ? inv.getVendorName() : "Unknown");
            map.put("invoiceNumber", inv.getInvoiceNumber() != null ? inv.getInvoiceNumber() : "");
            map.put("totalAmount", inv.getTotalAmount() != null ? inv.getTotalAmount() : 0.0);
            map.put("companyCode", inv.getCompanyCode() != null ? inv.getCompanyCode() : "");
            map.put("status", inv.getStatus() != null ? inv.getStatus() : "");
            
            return map;
        }).toList();
        
        Map<String, Object> results = new HashMap<>();
        results.put("results", cleanInvoices);
        
        Map<String, Object> d = new HashMap<>();
        d.put("d", results);
        
        return d;
    }
    @GetMapping(value = "/export/csv", produces = "text/csv")
    public void downloadCsv(HttpServletResponse response) throws IOException {
        response.setContentType("text/csv");
        response.setHeader("Content-Disposition", "attachment; filename=\"ai_invoices.csv\"");
        
        PrintWriter writer = response.getWriter();
        // 1. Write the CSV Headers
        writer.println("id,docId,vendorName,invoiceNumber,totalAmount,companyCode,status");
        
        // 2. Write the Database Rows
        List<Invoice> invoices = invoiceRepository.findAll();
        for (Invoice inv : invoices) {
            writer.printf("%d,\"%s\",\"%s\",\"%s\",%.2f,\"%s\",\"%s\"\n",
                    inv.getId(),
                    inv.getDocId() != null ? inv.getDocId() : "",
                    inv.getVendorName() != null ? inv.getVendorName() : "",
                    inv.getInvoiceNumber() != null ? inv.getInvoiceNumber() : "",
                    inv.getTotalAmount() != null ? inv.getTotalAmount() : 0.0,
                    inv.getCompanyCode() != null ? inv.getCompanyCode() : "",
                    inv.getStatus() != null ? inv.getStatus() : "");
        }
    }
}