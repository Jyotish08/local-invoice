# local-invoice

A 100% offline, zero-cost, private AI microservice for freelance accountants and financial data pipelines. Processes client invoice PDFs locally with **FastAPI**, **PyMuPDF**, and **Gemma 2 (2B)** via **Ollama**.

---

## Key Features
* **Zero Cloud Leakage:** Works completely offline without an internet connection. No client data ever leaves your computer.
* **Zero API Costs:** Replaces cloud LLMs (OpenAI, Gemini) with local inference using Google's `gemma2:2b`.
* **PyMuPDF Native Ingestion:** High-speed text extraction across multi-page PDF documents.
* **Scanned PDF Guardrail:** Detects non-searchable/scanned PDFs and returns a clear `400 Bad Request` informing the user that native text is required.
* **Structured Output via Ollama:** Enforces strict Pydantic v2 JSON schema adherence.
* **TabPFN & Pandas Ready:** Flat, normalized JSON outputs directly ingestible into pandas and downstream anomaly detection models.

---

## Architecture & Technology Stack
* **Web Framework:** FastAPI (with Pydantic v2)
* **PDF Parser:** PyMuPDF (`fitz`)
* **Local Inference:** Ollama Python SDK running `gemma2:2b`
* **Test Suite:** Pytest & HTTPX

---

## Quick Start Guide

### 1. Prerequisites
1. Install [Ollama](https://ollama.ai/).
2. Pull the Gemma 2 2B model:
   ```bash
   ollama pull gemma2:2b
   ```
3. Start the Ollama daemon:
   ```bash
   ollama serve
   ```

### 2. Environment Setup
Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Run the Microservice
Start the FastAPI server:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## API Documentation & Curl Commands

### 1. Health Check
```bash
curl -X GET http://127.0.0.1:8000/health
```

**Response (Ollama Online):**
```json
{
  "status": "healthy",
  "ollama_connected": true,
  "model": "gemma2:2b",
  "ollama_host": "http://localhost:11434",
  "privacy": "100% Local / Zero Cloud Leakage"
}
```

### 2. Extract Invoice (Native PDF)
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/extract" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@sample_data/sample_invoice.pdf;type=application/pdf"
```

**Response:**
```json
{
  "vendor_name": "Acme Tech Solutions Inc.",
  "invoice_number": "INV-2024-9988",
  "invoice_date": "2024-10-15",
  "total_amount": 1650.0,
  "tax_amount": 150.0,
  "line_items": [
    {
      "description": "Cloud Architecture Consulting",
      "quantity": 10.0,
      "unit_price": 150.0,
      "total_price": 1500.0
    }
  ]
}
```

### 3. Scanned PDF (No Text Layer)
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/extract" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@sample_data/scanned_image.pdf;type=application/pdf"
```

**Response (HTTP 400 Bad Request):**
```json
{
  "detail": "OCR not supported yet, please upload a native PDF"
}
```

---

## Downstream Dataframe / TabPFN Consumption Example

```python
import requests
import pandas as pd

# 1. Call local extraction microservice
with open("sample_data/sample_invoice.pdf", "rb") as f:
    response = requests.post("http://127.0.0.1:8000/api/v1/extract", files={"file": f})
invoice_json = response.json()

# 2. Convert line items directly to pandas DataFrame for TabPFN tabular anomaly detection
df_items = pd.DataFrame(invoice_json["line_items"])
df_items["vendor_name"] = invoice_json["vendor_name"]
df_items["invoice_number"] = invoice_json["invoice_number"]
df_items["invoice_date"] = invoice_json["invoice_date"]

print(df_items)
```

---

## Running the Automated Test Suite

```bash
pytest
```
