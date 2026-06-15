"""
main.py - RabbitMQ Consumer for Invoice Pipeline (with DB update)
"""

import os
import json
import logging
import time
import requests
import tempfile
from pathlib import Path

import pika
import psycopg2
from dotenv import load_dotenv
load_dotenv()

from pipeline.logging_setup import configure_logging
from pipeline.orchestrator import run_pipeline

logger = logging.getLogger("worker_main")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "password")
QUEUE_NAME = "invoice_requests"

# PostgreSQL config - Docker internal network
DB_HOST = os.getenv("DB_HOST", "sap-postgres")
DB_PORT = os.getenv("DB_PORT", "5432")  # Internal container port
DB_NAME = os.getenv("DB_NAME", "sap_invoices")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password")


def update_invoice_status(doc_id: str, status: str, payload: dict = None) -> None:
    """Update invoice status and extracted payload in PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cursor = conn.cursor()
        
        if payload:
            payload_json = json.dumps(payload)
            cursor.execute(
                "UPDATE invoices SET status = %s, extracted_payload = %s WHERE doc_id = %s",
                (status, payload_json, doc_id)
            )
        else:
            cursor.execute(
                "UPDATE invoices SET status = %s WHERE doc_id = %s",
                (status, doc_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("📊 DB updated | doc_id=%s status=%s", doc_id, status)
        
    except Exception as e:
        logger.error("❌ DB update failed | doc_id=%s error=%s", doc_id, str(e))


def process_message(ch, method, properties, body) -> None:
    try:
        message = json.loads(body)
        file_path = message.get("file_path")
        doc_id = message.get("doc_id", f"auto-{int(time.time())}")
        
        logger.info("📥 Received | doc_id=%s url=%s", doc_id, file_path)
        
        # Update status to PROCESSING
        update_invoice_status(doc_id, "PROCESSING")
        
        # Fix Azurite URL for Docker internal network
        file_path = file_path.replace("127.0.0.1", "sap-azurite")
        
        # Download from Azure Blob Storage to a temp file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        response = requests.get(file_path, timeout=60)
        response.raise_for_status()
        tmp.write(response.content)
        tmp.close()
        
        logger.info("📥 Downloaded to %s", tmp.name)
        
        # Process the local temp file
        result = run_pipeline(file_path=tmp.name, doc_id=doc_id)
        
        # Clean up
        Path(tmp.name).unlink()
        
        # Update status and payload in database
        status = result.get("status", "REQUIRES_MANUAL_REVIEW")
        update_invoice_status(doc_id, status, result)
        
        logger.info("✅ Done | doc_id=%s status=%s", doc_id, status)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error("❌ Failed | error=%s", str(e))
        try:
            msg = json.loads(body)
            update_invoice_status(msg.get("doc_id", "UNKNOWN"), "FAILED")
        except:
            pass
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    configure_logging()
    
    logger.info("🚀 AI Worker booting. Connecting to RabbitMQ at %s...", RABBITMQ_HOST)
    
    time.sleep(5)
    
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)
    
    logger.info("🎧 Worker is actively listening to '%s'. Waiting for invoices...", QUEUE_NAME)
    
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("🛑 Worker shutting down...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()