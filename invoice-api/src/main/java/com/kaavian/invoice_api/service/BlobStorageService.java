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

    // FIX: Spring Boot's OWN client (used to create the container, and to
    // build the BlobClient that generates the SAS) must always reach
    // Azurite at its real network address — "azurite" (the Docker service
    // name) when running in Docker, "127.0.0.1" when running locally on the
    // host. That's what azure.storage.connection-string controls, and it is
    // never browser-facing.
    //
    // The browser, however, runs OUTSIDE Docker and can only reach Azurite
    // via the published port on 127.0.0.1. So the SAS URL handed back to the
    // browser needs its host rewritten to azure.storage.public-host, which
    // defaults to 127.0.0.1 and only needs to change if you expose Azurite
    // under a different public hostname (e.g. a real Azure Storage account
    // in production, where this rewrite is skipped entirely).
    private final String publicBlobHost;

    public BlobStorageService(
            @Value("${azure.storage.connection-string}") String connectionString,
            @Value("${azure.storage.public-host:127.0.0.1}") String publicBlobHost) {
        this.blobServiceClient = new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
        this.publicBlobHost = publicBlobHost;

        BlobContainerClient containerClient = blobServiceClient.getBlobContainerClient(containerName);
        if (!containerClient.exists()) {
            containerClient.create();
        }
    }

    /**
     * Result of an upload-URL request: the short-lived SAS URL for the browser
     * to PUT against, plus the bare blob name (no token) that gets persisted
     * and queued for the worker.
     */
    public record UploadTarget(String uploadUrl, String blobName) {}

    /**
     * Generates a secure, temporary upload URL for the React frontend.
     *
     * FIX (vulnerability A — "SAS Token Time-Bomb"):
     * Previously this returned only the SAS URL, which was the same string
     * persisted to Postgres and pushed onto RabbitMQ. If a worker picked the
     * message up more than 15 minutes after it was queued, the SAS token had
     * already expired and the download would 403.
     *
     * Now we return BOTH the SAS URL (for the browser's one-time PUT) and the
     * bare blob name (no token, never expires) separately. Only the blob name
     * gets stored/queued — the worker fetches the blob directly via the master
     * connection string (see InferenceWorker's companion fetch in Python),
     * which never expires and isn't a network-fetchable URL at all.
     */
    public UploadTarget generateUploadTarget(String originalFilename) {
        String uniqueFilename = UUID.randomUUID().toString() + "-" + originalFilename;

        BlobContainerClient containerClient = blobServiceClient.getBlobContainerClient(containerName);
        BlobClient blobClient = containerClient.getBlobClient(uniqueFilename);

        BlobSasPermission sasPermission = new BlobSasPermission()
                .setReadPermission(true)
                .setWritePermission(true)
                .setCreatePermission(true);

        BlobServiceSasSignatureValues sasValues = new BlobServiceSasSignatureValues(
                OffsetDateTime.now().plusMinutes(15), sasPermission);

        String uploadUrl = blobClient.getBlobUrl() + "?" + blobClient.generateSas(sasValues);

        // Rewrite whatever host the SDK baked in (the Docker service name,
        // e.g. "azurite") to the publicly-reachable host the browser can
        // actually connect to. This only touches the hostname segment of
        // the URL — the SAS signature itself is unaffected since signatures
        // don't cover the host.
        uploadUrl = uploadUrl.replaceFirst("://[^/:]+:", "://" + publicBlobHost + ":");

        // blobName is just "invoices/<uuid>-clean.pdf" — no host, no token, no expiry.
        return new UploadTarget(uploadUrl, uniqueFilename);
    }

    /**
     * Checks whether a blob actually landed in storage.
     *
     * FIX: the browser's PUT to Azurite is made with fetch's `no-cors` mode
     * (Azurite has no CORS rules configured by default, so a normal
     * cross-origin fetch would be blocked entirely). That makes the
     * response "opaque" client-side — the frontend literally cannot tell a
     * 200 from a 403/404 on that request, so a failed or incomplete upload
     * was silently treated as a success and queued for processing anyway,
     * only surfacing much later as a CorruptFileError in the worker logs.
     * The Java backend has no such CORS restriction (server-to-server), so
     * it can check directly — this is the real verification point.
     */
    public boolean blobExists(String blobName) {
        BlobContainerClient containerClient = blobServiceClient.getBlobContainerClient(containerName);
        return containerClient.getBlobClient(blobName).exists();
    }
}