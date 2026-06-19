"""
main.py - RabbitMQ Consumer for Invoice Pipeline (with DB update)
"""

import os
import json
import logging
import time
import tempfile
from pathlib import Path

import pika
import psycopg2
import psycopg2.pool
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
load_dotenv()

from pipeline.logging_setup import configure_logging
from pipeline.orchestrator import run_pipeline

logger = logging.getLogger("worker_main")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "password")
QUEUE_NAME = "invoice_requests"

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "sap_invoices")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password")

# FIX (vulnerability A & B): The worker now talks to Azure/Azurite directly
# via the SDK and a master connection string — never over an HTTP SAS URL
# that could expire mid-queue-backlog (vuln A), and never via a hardcoded
# "127.0.0.1 -> sap-azurite" string replace that would corrupt URLs in any
# real cloud deployment (vuln B). The connection string itself carries the
# right host for whichever environment we're in (local Azurite vs Docker vs
# real Azure), so main.py needs zero environment-specific hacks.
AZURE_STORAGE_CONNECTION_STRING = os.getenv(
    "AZURE_STORAGE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://azurite:10000/devstoreaccount1;",
)
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "invoices")

_db_pool: psycopg2.pool.SimpleConnectionPool | None = None
_blob_service_client: BlobServiceClient | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _db_pool
    if _db_pool is None:
        _db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
        )
    return _db_pool


def _get_blob_client() -> BlobServiceClient:
    global _blob_service_client
    if _blob_service_client is None:
        _blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )
    return _blob_service_client


def _extract_summary_fields(payload: dict) -> dict:
    """Pull dashboard summary columns from the nested extraction payload."""
    header = payload.get("header_data") or {}
    financial = payload.get("financial_data") or {}
    sap_metadata = payload.get("sap_metadata") or {}
    return {
        "vendor_name": header.get("vendor_name"),
        "invoice_number": header.get("invoice_number"),
        "total_amount": financial.get("total_invoice_amount"),
        "company_code": sap_metadata.get("company_code"),
    }


def update_invoice_status(doc_id: str, status: str, payload: dict = None) -> None:
    """Update invoice status, extracted payload, and dashboard summary columns."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        if payload:
            payload_json = json.dumps(payload)
            summary = _extract_summary_fields(payload)
            cursor.execute(
                """
                UPDATE invoices
                SET status = %s,
                    extracted_payload = %s,
                    vendor_name = %s,
                    invoice_number = %s,
                    total_amount = %s,
                    company_code = %s
                WHERE doc_id = %s
                """,
                (
                    status,
                    payload_json,
                    summary["vendor_name"],
                    summary["invoice_number"],
                    summary["total_amount"],
                    summary["company_code"],
                    doc_id,
                ),
            )
        else:
            cursor.execute(
                "UPDATE invoices SET status = %s WHERE doc_id = %s",
                (status, doc_id)
            )
        conn.commit()
        cursor.close()
        logger.info("DB updated | doc_id=%s status=%s", doc_id, status)
    except Exception as e:
        logger.error("DB update failed | doc_id=%s error=%s", doc_id, str(e))
        conn.rollback()
    finally:
        pool.putconn(conn)


def download_blob_to_tempfile(blob_name: str) -> str:
    """
    Download a blob by name (no SAS token, no expiry) using the master
    connection string, and write it to a temp file preserving the real
    extension so the preprocessor routes it correctly (PDF vs image).
    """
    blob_service_client = _get_blob_client()
    container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(blob_name)

    ext = Path(blob_name).suffix.lower() or ".pdf"
    if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp"}:
        ext = ".pdf"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    download_stream = blob_client.download_blob()
    tmp.write(download_stream.readall())
    tmp.close()
    return tmp.name


MAX_RATE_LIMIT_REQUEUES = int(os.getenv("MAX_RATE_LIMIT_REQUEUES", "10"))


def process_message(ch, method, properties, body) -> None:
    try:
        message = json.loads(body)
        # blob_name is now a bare blob path like "550e8400-...-clean.pdf",
        # not a URL — see BlobStorageService.UploadTarget on the Java side.
        blob_name = message.get("file_path")
        doc_id = message.get("doc_id", f"auto-{int(time.time())}")

        logger.info("Received | doc_id=%s blob=%s", doc_id, blob_name)

        update_invoice_status(doc_id, "PROCESSING")

        tmp_path = download_blob_to_tempfile(blob_name)
        logger.info("Downloaded to %s", tmp_path)

        result = run_pipeline(file_path=tmp_path, doc_id=doc_id)

        Path(tmp_path).unlink(missing_ok=True)

        status = result.get("status", "REQUIRES_MANUAL_REVIEW")

        if status == "RATE_LIMITED":
            # x-delivery-count is set by RabbitMQ itself when a message is
            # requeued via basic_nack — no custom header bookkeeping needed.
            # Once we've requeued this same message too many times (i.e.
            # the outage is sustained, not a blip), stop looping and hand it
            # to a human instead of retrying forever.
            delivery_count = 0
            if properties.headers:
                delivery_count = properties.headers.get("x-delivery-count", 0)

            if delivery_count >= MAX_RATE_LIMIT_REQUEUES:
                logger.error(
                    "Rate limit persisted past %d requeues | doc_id=%s — "
                    "escalating to REQUIRES_MANUAL_REVIEW instead of looping forever.",
                    MAX_RATE_LIMIT_REQUEUES, doc_id,
                )
                update_invoice_status(doc_id, "REQUIRES_MANUAL_REVIEW", result)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            update_invoice_status(doc_id, status, result)
            logger.warning(
                "Requeueing rate-limited message | doc_id=%s attempt=%d/%d",
                doc_id, delivery_count + 1, MAX_RATE_LIMIT_REQUEUES,
            )
            # Nothing wrong with this document — the provider is just out
            # of capacity right now. Requeue (don't dead-letter) so a worker
            # picks it back up once capacity frees up. A short sleep avoids
            # immediately re-colliding with whatever just rate-limited us.
            time.sleep(5)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return

        update_invoice_status(doc_id, status, result)
        logger.info("Done | doc_id=%s status=%s", doc_id, status)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger.error("Failed | error=%s", str(e), exc_info=True)
        try:
            msg = json.loads(body)
            update_invoice_status(msg.get("doc_id", "UNKNOWN"), "FAILED")
        except Exception:
            pass
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def _connect_rabbitmq(max_attempts: int = 10) -> pika.BlockingConnection:
    """
    Connect to RabbitMQ with exponential backoff.

    ANOMALY FIX: previously this was a single unguarded
    pika.BlockingConnection() call. If RabbitMQ wasn't reachable on the
    first attempt (e.g. Docker restarted and rabbitmq took longer to become
    healthy than expected, despite depends_on: condition: service_healthy
    in compose), the AMQPConnectionError propagated straight out of main()
    and the worker process exited with code 1 — permanently, since there is
    no restart policy on the ai-worker service. The container then sat dead
    until someone noticed and ran `docker compose up -d` manually, during
    which time every message sent to the queue just piled up unconsumed.

    Backoff schedule: 2s, 4s, 8s, 16s... capped at 30s.
    """
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            connection = pika.BlockingConnection(parameters)
            logger.info("Connected to RabbitMQ on attempt %d/%d", attempt, max_attempts)
            return connection
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(2 ** attempt, 30)
            logger.warning(
                "RabbitMQ connection failed (attempt %d/%d), retrying in %ds: %s",
                attempt, max_attempts, delay, exc,
            )
            time.sleep(delay)

    logger.error("Could not connect to RabbitMQ after %d attempts.", max_attempts)
    raise last_exc


def main() -> None:
    configure_logging()

    logger.info("AI Worker booting. Connecting to RabbitMQ at %s...", RABBITMQ_HOST)

    # ANOMALY FIX: this used to be an unconditional 5-second sleep before
    # the (single, unguarded) connection attempt — a guess at how long
    # RabbitMQ takes to start, not an actual readiness check. The retry
    # loop in _connect_rabbitmq replaces this guess with real backoff that
    # keeps trying until RabbitMQ is actually reachable (or we genuinely
    # give up after max_attempts), so a slow-starting broker no longer
    # kills the worker outright.

    # ANOMALY FIX: wrap the whole consume loop so a connection that drops
    # mid-run (network blip, RabbitMQ restart, etc.) triggers a reconnect
    # instead of killing the process the same way the original startup
    # failure did.
    while True:
        try:
            connection = _connect_rabbitmq()
            channel = connection.channel()

            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

            logger.info("Worker listening on '%s'. Waiting for invoices...", QUEUE_NAME)

            try:
                channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("Worker shutting down...")
                channel.stop_consuming()
                connection.close()
                return
            finally:
                if connection.is_open:
                    connection.close()

        except KeyboardInterrupt:
            logger.info("Worker shutting down (interrupted before connecting)...")
            return
        except Exception as exc:
            logger.error(
                "Worker loop crashed, reconnecting in 5s: %s", exc, exc_info=True
            )
            time.sleep(5)
            continue


if __name__ == "__main__":
    main()