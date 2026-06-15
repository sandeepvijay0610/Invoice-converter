package com.kaavian.invoice_api.service;

import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.UUID;

@Service
public class BlobStorageService {

    private final BlobServiceClient blobServiceClient;
    private final String containerName = "invoices";

    // Constructor injection grabs the connection string from your application.properties
    public BlobStorageService(@Value("${azure.storage.connection-string}") String connectionString) {
        this.blobServiceClient = new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
        
        // Auto-create the 'invoices' bucket in Azurite if it doesn't exist yet
        BlobContainerClient containerClient = blobServiceClient.getBlobContainerClient(containerName);
        if (!containerClient.exists()) {
            containerClient.create();
        }
    }

    /**
     * Generates a secure, temporary upload URL for the React frontend
     */
    public String generateUploadUrl(String originalFilename) {
        // 1. Sanitize the filename with a UUID so it is guaranteed unique
        // Example: clean.pdf -> 550e8400-e29b-41d4-a716-446655440000-clean.pdf
        String uniqueFilename = UUID.randomUUID().toString() + "-" + originalFilename;

        // 2. Get a reference to exactly where this file will live
        BlobContainerClient containerClient = blobServiceClient.getBlobContainerClient(containerName);
        BlobClient blobClient = containerClient.getBlobClient(uniqueFilename);

        // 3. Define the SAS (Shared Access Signature) permissions
        // React only needs permission to Create and Write the file, nothing else.
        BlobSasPermission sasPermission = new BlobSasPermission()
                .setReadPermission(true)
                .setWritePermission(true)
                .setCreatePermission(true);

        // 4. Set the expiration time (React has exactly 15 minutes to upload it)
        BlobServiceSasSignatureValues sasValues = new BlobServiceSasSignatureValues(
                OffsetDateTime.now().plusMinutes(15), sasPermission);

        // 5. Generate and return the final secure URL string
        return blobClient.getBlobUrl() + "?" + blobClient.generateSas(sasValues);
    }
}