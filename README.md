# invoice_pipeline

Enterprise invoice extraction pipeline for SAP FICO/MM.  
Extracts structured data from PDF/image invoices using GPT-4o via GitHub Models.

## Architecture

```
invoice.pdf / image
       │
       ▼
┌─────────────────────┐
│  DocumentPreprocessor│  Piece 1 — Normalize to 300 DPI PNGs
└──────────┬──────────┘
           │ list[ProcessedPage]
           ▼
┌─────────────────────┐
│   InferenceWorker   │  Piece 2 — GPT-4o multimodal extraction
└──────────┬──────────┘
           │ {doc_metadata, extracted_entities}
           ▼
┌─────────────────────┐
│   DocumentMapper    │  Piece 3 — Parse, validate, SAP payload
└──────────┬──────────┘
           │ InvoicePayload (dict)
           ▼
    JSON to stdout
```

## Setup

### Local

```bash
# 1. Install Poppler (required by pdf2image for scanned PDFs)
#    macOS:  brew install poppler
#    Debian: apt-get install -y poppler-utils

# 2. Install Python deps
pip install -r requirements.txt

# 3. Set env vars
cp .env.example .env
# Edit .env — set GITHUB_TOKEN at minimum

# 4. Run
export $(cat .env | xargs)
python main.py invoice.pdf --doc-id INV-2026-001
```

### Docker

```bash
# Build
docker build -t invoice-pipeline:latest .

# Run — minimum config
docker run --rm \
  -e GITHUB_TOKEN=your_pat_here \
  -v /host/invoices:/data/invoices:ro \
  invoice-pipeline:latest \
  /data/invoices/invoice.pdf --doc-id INV-2026-001

# Run — with persistent PNG output and full config
docker run --rm \
  --env-file .env \
  -v /host/invoices:/data/invoices:ro \
  -v /host/pages:/data/pages \
  invoice-pipeline:latest \
  /data/invoices/invoice.pdf \
  --doc-id INV-2026-001 \
  --output-dir /data/pages \
  --company-code 2000
```

## Environment Variables

| Variable               | Required | Default                                    | Description                              |
|------------------------|----------|--------------------------------------------|------------------------------------------|
| `GITHUB_TOKEN`         | **Yes**  | —                                          | GitHub Models PAT                        |
| `MODEL_NAME`           | No       | `gpt-4o-mini`                              | `gpt-4o` or `gpt-4o-mini`               |
| `GITHUB_ENDPOINT`      | No       | `https://models.inference.ai.azure.com`    | Azure inference endpoint                 |
| `API_DELAY_SECONDS`    | No       | `4`                                        | Rate-limit delay between API calls       |
| `MAX_RETRIES`          | No       | `3`                                        | OpenAI client retry count                |
| `TIMEOUT_SECONDS`      | No       | `120`                                      | API request timeout                      |
| `OUTPUT_DIR`           | No       | `/tmp/ingestor`                            | Where normalized PNGs are written        |
| `TARGET_DPI`           | No       | `300`                                      | Rasterization DPI                        |
| `NATIVE_TEXT_MIN_CHARS`| No       | `10`                                       | Min chars for native-text PDF detection  |
| `CONFIDENCE_THRESHOLD` | No       | `0.72`                                     | Min confidence for READY_FOR_SAP         |
| `MATH_TOLERANCE`       | No       | `0.05`                                     | Acceptable total delta (INR)             |
| `SAP_COMPANY_CODE`     | No       | `1000`                                     | Default SAP company code                 |
| `SAP_DOC_TYPE`         | No       | `RE`                                       | Default SAP document type                |
| `SAP_CURRENCY`         | No       | `INR`                                      | Default SAP currency                     |
| `LOG_LEVEL`            | No       | `INFO`                                     | `DEBUG` / `INFO` / `WARNING` / `ERROR`   |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Output Shape

```json
{
  "doc_id": "INV-2026-001",
  "status": "READY_FOR_SAP",
  "overall_confidence": 0.95,
  "sap_metadata": { "company_code": "1000", "doc_type": "RE", "currency": "INR" },
  "header_data": {
    "vendor_name": "ACME Supplies Pvt Ltd",
    "vendor_gstin": "27AAPFU0939F1ZV",
    "invoice_number": "INV/2026/001",
    "invoice_date": "2026-05-15",
    ...
  },
  "financial_data": {
    "base_amount": 10000.0,
    "cgst_amount": 900.0,
    "sgst_amount": 900.0,
    "igst_amount": null,
    "total_invoice_amount": 11800.0
  },
  "line_item_data": [
    {
      "invoice_item_text": "Laptop Model X",
      "hsn_sac_code": "8471",
      "quantity": 2.0,
      "unit_price": 5000.0,
      "line_amount": 10000.0,
      "sap_mm_fields": { "po_item_number": "00010" },
      "sap_fico_fields": { "gl_account": null, "cost_center": null }
    }
  ]
}
```
