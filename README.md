# Invoice Pipeline

Enterprise invoice extraction pipeline for SAP FICO/MM.  
Extracts structured data from PDF/image invoices using GPT-4o via GitHub Models.

## Architecture

                                                                                                                              ````
                                                                                                                              invoice.pdf / image
                                                                                                                                     │
                                                                                                                                     ▼
                                                                                                                              ┌─────────────────────┐
                                                                                                                              │ DocumentPreprocessor│  Piece 1 — Normalize to 300 DPI PNGs
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
                                                                                                                              ````

# How to Run & Test the Stack

## Prerequisites

- Docker Desktop installed and running
- A GitHub Personal Access Token with `models:read` permission
  (for GitHub Models / GPT-4o access)

---

## Step 1 — Set your GitHub token

Create a `.env` file **inside the `Legacy-Document-Digitizer/` folder**
(same folder as `docker-compose.yml`):

```
GITHUB_TOKEN=ghp_your_actual_token_here
```

Never commit this file. It's already in `.gitignore` by convention.

---

## Step 2 — Build and start everything

From inside `Legacy-Document-Digitizer/`:

```bash
docker compose up --build
```

To run 3 AI worker replicas (as originally intended):

```bash
docker compose up --build --scale ai-worker=3
```

First run takes 3–5 minutes to build images and pull dependencies.

---

## Step 3 — Watch the logs

Open a second terminal to tail logs:

```bash
# All services
docker compose logs -f

# Only the AI workers
docker compose logs -f ai-worker

# Only the Spring Boot API
docker compose logs -f invoice-api
```

**Healthy startup looks like this:**

```
sap-rabbitmq  | Server startup complete
sap-postgres  | database system is ready to accept connections
invoice-api   | Started InvoiceApiApplication in 4.2 seconds
ai-worker-1   | AI Worker booting. Connecting to RabbitMQ at rabbitmq...
ai-worker-1   | Worker listening on 'invoice_requests'. Waiting for invoices...
```

---

## Step 4 — Check the RabbitMQ Management UI

Open http://localhost:15672 in your browser.

- Login: `admin` / `password`
- Go to **Queues** tab → you should see `invoice_requests` listed
- This is where you'll watch messages move when you submit an invoice

---

## Step 5 — Submit a test invoice

### 5a. Request an upload URL

```bash
curl -X POST http://localhost:8080/api/invoices/request-upload \
  -H "Content-Type: application/json" \
  -d '{"filename": "test-invoice.pdf"}'
```

Response:
```json
{
  "id": "INV-a1b2c3d4",
  "uploadUrl": "http://127.0.0.1:10000/devstoreaccount1/invoices/uuid-test-invoice.pdf?sv=..."
}
```

### 5b. Upload the PDF to Azurite using the URL from 5a

```bash
curl -X PUT "<uploadUrl from above>" \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: application/pdf" \
  --data-binary @/path/to/your/invoice.pdf
```

A sample PDF is already in `data/clean.pdf`:

```bash
curl -X PUT "<uploadUrl>" \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: application/pdf" \
  --data-binary @data/clean.pdf
```

### 5c. Trigger AI processing

```bash
curl -X POST http://localhost:8080/api/invoices/INV-a1b2c3d4/process
```

Response: `Processing started for INV-a1b2c3d4`

### 5d. Watch it process

In the RabbitMQ UI (http://localhost:15672 → Queues), you'll see the
message count tick up then immediately drop to 0 as a worker picks it up.

In the worker logs:
```
ai-worker-1  | Received | doc_id=INV-a1b2c3d4 url=http://...
ai-worker-1  | DB updated | doc_id=INV-a1b2c3d4 status=PROCESSING
ai-worker-1  | Extracting | doc_id=INV-a1b2c3d4 pages=1 model=gpt-4o
ai-worker-1  | Extraction complete | doc_id=INV-a1b2c3d4 ...
ai-worker-1  | DB updated | doc_id=INV-a1b2c3d4 status=READY_FOR_SAP
```

---

## Step 6 — Check the result in PostgreSQL

Connect to the database:

```bash
docker exec -it sap-postgres psql -U admin -d sap_invoices
```

Then query:

```sql
SELECT doc_id, status, vendor_name, total_amount FROM invoices;

-- See the full extracted JSON payload
SELECT doc_id, status, extracted_payload FROM invoices WHERE doc_id = 'INV-a1b2c3d4';
```

Type `\q` to exit.

---

## Step 7 — Run the Python unit tests (no Docker needed)

```bash
cd Legacy-Document-Digitizer

# Install deps in a virtualenv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set a dummy token so config.py doesn't crash
export GITHUB_TOKEN=test_token

# Run tests
pytest tests/ -v
```

Expected output:
```
tests/test_mapper_parser.py::TestParseDate::test_iso_passthrough PASSED
tests/test_mapper_parser.py::TestParseDate::test_dd_mm_yyyy PASSED
...
tests/test_mapper_parser.py::TestProcessDocument::test_ready_for_sap PASSED
17 passed in 0.42s
```

---

## Stopping everything

```bash
docker compose down          # stops containers, keeps volumes (DB data survives)
docker compose down -v       # stops containers AND deletes all volumes (fresh start)
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ai-worker` exits immediately with `EnvironmentError: GITHUB_TOKEN is not set` | Check your `.env` file is in the right folder and contains `GITHUB_TOKEN=...` |
| `invoice-api` fails to start with `Connection refused` to postgres | Postgres health check hasn't passed yet — wait 30s and retry `docker compose up` |
| RabbitMQ queue shows message stuck in "Ready" forever | Worker didn't connect — run `docker compose logs ai-worker` to see the error |
| `curl /process` returns 404 | The `doc_id` doesn't exist in the DB — make sure step 5a ran successfully first |
| Worker logs show `CorruptFileError` | The file type extension in the URL didn't match the actual file — check the upload used the right Content-Type |2000
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
