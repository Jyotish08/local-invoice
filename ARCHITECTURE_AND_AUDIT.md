# Architecture and Diagnostic Audit Report

**Date:** 2026-10-16  
**Auditor:** Senior Backend Architect  
**Objective:** Diagnose existing codebase, document failure reproductions, audit against common architectural breakers, and define a minimal repair plan.

---

## 1. Repository Map

### 1.1 Files & Modules

| Path | Role | Dependencies / External Services |
| :--- | :--- | :--- |
| `app/__init__.py` | Package marker for core microservice | None |
| `app/config.py` | Configuration settings (`Settings` using Pydantic `BaseModel`) | Environment variables: `OLLAMA_HOST`, `MODEL_NAME`, `MAX_CONTEXT_CHARS`, `MIN_TEXT_CHARS_THRESHOLD` |
| `app/pdf_parser.py` | PyMuPDF (`pymupdf`) document ingestion, multi-page concatenation, text-layer presence validation, context truncation | `pymupdf`, `app.config.settings` |
| `app/extractor.py` | Data models (`InvoiceData`, `LineItem`) and `LocalInvoiceExtractor` calling Ollama | `pydantic`, `ollama`, `app.config.settings`, Local Ollama daemon (`http://localhost:11434`) |
| `app/main.py` | FastAPI application, CORS, `/health` and `/api/v1/extract` endpoints | `fastapi`, `app.config.settings`, `app.pdf_parser`, `app.extractor` |
| `sample_data/generate_sample.py` | Generator for mock test PDFs (searchable invoice & scanned raster image) | `reportlab`, `pymupdf`, `PIL` |
| `sample_data/sample_invoice.pdf` | Generated multi-page searchable PDF test fixture | None |
| `sample_data/scanned_image.pdf` | Generated rasterized/scanned non-searchable PDF test fixture | None |
| `tests/__init__.py` | Package marker for test suite | None |
| `tests/test_api.py` | API endpoint integration tests | `pytest`, `fastapi.testclient.TestClient`, `unittest.mock` |
| `tests/test_extractor.py` | Unit tests for Pydantic schema validation & extraction logic | `pytest`, `pydantic`, `unittest.mock` |
| `tests/test_pdf_parser.py` | Unit tests for PyMuPDF text extraction & OCR detection | `pytest`, `pymupdf` |
| `requirements.txt` | Python runtime and test dependencies | PyPI packages (`fastapi`, `uvicorn`, `pydantic`, `pymupdf`, `ollama`, `python-multipart`, `pytest`, `httpx`, `reportlab`) |
| `.gitignore` | Version control exclusions | None |
| `SPEC.md` | Architecture specification document | None |
| `README.md` | Usage instructions and API documentation | None |

### 1.2 Entry Points
*   **Application Server:** `uvicorn app.main:app --host 127.0.0.1 --port 8000`
*   **Test Runner:** `pytest`
*   **Sample Data Generation:** `python sample_data/generate_sample.py`

### 1.3 External Services & Environment Variables
*   **Local Service:** Ollama daemon running on `http://localhost:11434` (model: `gemma2:2b`).
*   **Environment Variables:**
    *   `OLLAMA_HOST` (default: `"http://localhost:11434"`)
    *   `MODEL_NAME` (default: `"gemma2:2b"`)
    *   `MAX_CONTEXT_CHARS` (default: `12000`)
    *   `MIN_TEXT_CHARS_THRESHOLD` (default: `30`)

---

## 2. Common Breakers Audit Checklist

| Breaker Category | Status | Details / Evidence |
| :--- | :--- | :--- |
| **Missing or mismatched dependencies, versions, or env vars** | **CONFIRMED** | Local Ollama daemon is not running on `http://localhost:11434`. `OllamaSetup.exe` is present in user Downloads, but daemon is offline, blocking live LLM inference. |
| **Blocking sync calls inside async handlers** | **CONFIRMED** | `app/main.py` defines `async def health_check()` and `async def extract_invoice()`, yet invokes blocking synchronous I/O (`ollama.Client.list()`, `ollama.Client.chat()`, `pymupdf.open()`). When Ollama is offline or processing, the entire asyncio event loop is frozen for up to 4+ seconds, starving concurrent requests. |
| **Heavy resources re-created per request** | **NOT PRESENT** | `extractor = LocalInvoiceExtractor()` is instantiated once as a module-level singleton in `app/main.py`. PyMuPDF documents are properly closed via `doc.close()`. |
| **Unhandled exceptions from external services** | **CONFIRMED** | In `app/extractor.py`, non-connection errors (such as missing model `404` from Ollama or inference timeout) are treated as generic `OllamaExtractionError` and returned as `HTTP 422 Unprocessable Entity` rather than identifying server/model readiness (`503` or `500`). Additionally, `ollama.Client` lacks a timeout setting. |
| **Fragile parsing of LLM/model output** | **CONFIRMED** | `InvoiceData` and `LineItem` declare strict `float` and `List[LineItem]` types without input sanitizers. If the model emits currency strings (e.g. `"$1,250.50"` or `"1,500.00"`), `null` for `tax_amount`, or `null` for `line_items`, Pydantic raises an uncaught `ValidationError`. |
| **Silent truncation or limits** | **CONFIRMED** | 1. `truncate_text_for_context()` truncates oversized documents, but the returned API response contains no header or field notifying the client that text was cut. 2. `await file.read()` in `app/main.py` has no file size limit, leaving the server vulnerable to OOM on very large uploads. |
| **Temp files or data written to disk unintentionally** | **NOT PRESENT** | Ingestion reads bytes into memory and opens `pymupdf.open(stream=pdf_bytes)`. No temporary files are written to disk. |
| **Frontend/backend contract mismatches** | **CONFIRMED** | `app/main.py` lacks `CORSMiddleware`. Any browser-based client (such as local accounting web tools or dashboards) will be blocked by CORS policy. |

---

## 3. Reproduced Failures (Ranked by Blocking Impact)

### Failure 1: Fragile LLM Output Parsing Crashes on Currency Strings and Nulls
*   **Severity:** CRITICAL (Breaks core extraction flow whenever LLM formats currency or outputs null)
*   **Reproducing Command 1 (Currency String):**
    ```powershell
    python -c "from app.extractor import InvoiceData; import json; raw = json.dumps({'vendor_name': 'V', 'invoice_number': '1', 'invoice_date': '2024-01-01', 'total_amount': '$1,250.50', 'tax_amount': 0.0, 'line_items': []}); InvoiceData.model_validate_json(raw)"
    ```
*   **Exact Error Output:**
    ```text
    pydantic_core._pydantic_core.ValidationError: 1 validation error for InvoiceData
    total_amount
      Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='$1,250.50', input_type=str]
    ```
*   **Reproducing Command 2 (Null Tax Amount):**
    ```powershell
    python -c "from app.extractor import InvoiceData; import json; raw = json.dumps({'vendor_name': 'V', 'invoice_number': '1', 'invoice_date': '2024-01-01', 'total_amount': 100.0, 'tax_amount': None, 'line_items': []}); InvoiceData.model_validate_json(raw)"
    ```
*   **Exact Error Output:**
    ```text
    pydantic_core._pydantic_core.ValidationError: 1 validation error for InvoiceData
    tax_amount
      Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
    ```

---

### Failure 2: Blocking Synchronous Calls Freeze the Async Event Loop
*   **Severity:** HIGH (Degrades performance, blocks concurrent traffic)
*   **Reproducing Evidence:**
    When Ollama is offline or busy, `curl.exe -i http://127.0.0.1:8000/health` executes `self.client.list()` synchronously inside `async def health_check()`.
    Curl output:
    ```text
    Time Total: 00:04 (4.02 seconds)
    HTTP/1.1 200 OK
    {"status":"degraded","ollama_connected":false,"model":"gemma2:2b",...}
    ```
    During these 4.02 seconds, the single thread of the asyncio event loop was 100% blocked; no other request could be initiated or answered.
*   **Root Cause:**
    `async def` tells FastAPI to execute the handler directly on the event loop. Invoking synchronous blocking I/O (`ollama.Client` and `pymupdf`) on the event loop starves all concurrent requests.

---

### Failure 3: Unhandled External Service Failures & Model Not Found Mapped to 422
*   **Severity:** HIGH (Misleading error reporting to clients)
*   **Reproducing Evidence:**
    In `app/extractor.py`:
    ```python
    except Exception as exc:
        err_msg = str(exc).lower()
        if "connection" in err_msg or "refused" in err_msg or "failed to connect" in err_msg:
            raise OllamaConnectionError(...)
        raise OllamaExtractionError(f"Ollama inference error: {str(exc)}")
    ```
    When Ollama is running but the model `gemma2:2b` is not pulled (or when a timeout occurs), Ollama returns an HTTP 404 with `"model 'gemma2:2b' not found"`. The current code raises `OllamaExtractionError`, which `app/main.py` converts to `HTTP 422 Unprocessable Entity` ("Document text could not be mapped to required invoice schema"), incorrectly blaming the client's PDF instead of reporting an infrastructure deficiency (`HTTP 503` or `HTTP 500`).

---

### Failure 4: Missing File Size Ceiling (Unchecked Memory Ingestion)
*   **Severity:** MEDIUM (Resource exhaustion vector)
*   **Reproducing Evidence:**
    In `app/main.py`:
    ```python
    pdf_bytes = await file.read()
    ```
    There is no check on `Content-Length` or running byte count, permitting multi-gigabyte uploads to be buffered directly into RAM.

---

### Failure 5: Missing CORS Middleware for Web/Client Consumption
*   **Severity:** MEDIUM (Prevents browser-based accounting frontend consumption)
*   **Reproducing Evidence:**
    `OPTIONS /api/v1/extract` with standard CORS origin headers returns 405 Method Not Allowed because `CORSMiddleware` is omitted from `app/main.py`.

---

## 4. Suspected-But-Unverified Items

1.  **Ollama Long-Generation Timeout:**
    *   `LocalInvoiceExtractor` does not specify a request timeout on `ollama.Client(host=self.host, timeout=...)`. On very complex invoices running on slow CPU-only machines, Ollama may take over 60 seconds or hang.
    *   *Status:* Suspected, unverified until long-running inference is tested under load.
2.  **Date Normalization Edge Cases:**
    *   `invoice_date` is typed as `str` in `InvoiceData`. If an invoice has a textual date like `"15th of October, 2024"`, Gemma may output that string directly.
    *   *Status:* Suspected, unverified (string representation currently accepted by schema).

---

## 5. Short Repair Plan (Minimal Fixes in Order)

### Fix 1: Robust Pydantic Parsing for Floats, Currency Strings, and Nulls
*   **Root Cause:** `InvoiceData` and `LineItem` lack pre-validators to coerce currency strings (`"$1,250.50"`, `"1,500.00"`), strip currency symbols, and convert `null` to `0.0` or empty lists.
*   **Minimal Fix:** Add a `@field_validator("*", mode="before")` or dedicated helper to sanitize currency strings and convert `None` to defaults for numeric fields (`total_amount`, `tax_amount`, `quantity`, `unit_price`, `total_price`) and ensure `line_items` defaults to `[]` when `None`.
*   **Files Touched:** `app/extractor.py`, `tests/test_extractor.py`
*   **Verification:** Run pytest including new test cases for `$`, `,`, `None`/`null` values.

### Fix 2: Prevent Event Loop Starvation by Converting Sync Handlers or Offloading
*   **Root Cause:** Synchronous `pymupdf` and `ollama.Client` calls inside `async def` routes block FastAPI's event loop.
*   **Minimal Fix:** In `app/main.py`, define endpoints using standard `def` (which FastAPI automatically offloads to its worker threadpool via `run_in_threadpool`), or offload synchronous calls (`extractor.check_connection()`, `extractor.extract()`, `extract_text_from_pdf_bytes()`) via `anyio.to_thread.run_sync()`. Standard `def` for synchronous handlers is the idiomatic FastAPI solution.
*   **Files Touched:** `app/main.py`
*   **Verification:** Measure `/health` and concurrent endpoint responsiveness when Ollama is offline or slow.

### Fix 3: Differentiate Infrastructure Errors (Model Missing/Offline) from Data Errors (422)
*   **Root Cause:** Catch-all maps model missing or server timeouts to 422 Unprocessable Entity.
*   **Minimal Fix:** Update `app/extractor.py` to identify "not found" / "model" errors as `OllamaConnectionError` / `OllamaModelNotFoundError`, and set a sensible timeout (e.g., 60 seconds). Map these to HTTP 503 in `app/main.py`.
*   **Files Touched:** `app/extractor.py`, `app/main.py`, `tests/test_api.py`
*   **Verification:** Unit and integration tests mocking model-not-found error verifying HTTP 503 response.

### Fix 4: Add Upload File Size Limit Guardrail
*   **Root Cause:** `await file.read()` reads unbounded bytes into RAM.
*   **Minimal Fix:** Check file size limit (e.g. 25MB). If exceeded, raise `HTTP 413 Payload Too Large`.
*   **Files Touched:** `app/main.py`, `app/config.py`, `tests/test_api.py`
*   **Verification:** Integration test uploading >25MB file returning 413.

### Fix 5: Add CORSMiddleware
*   **Root Cause:** FastAPI instance lacks CORS middleware for cross-origin browser requests.
*   **Minimal Fix:** Add `CORSMiddleware` with configurable/permissive local origins (`*` or localhost ports).
*   **Files Touched:** `app/main.py`
*   **Verification:** Curl test with `OPTIONS /api/v1/extract` verifying CORS response headers (`access-control-allow-origin`).

---

## 6. Repair Status & Verification Summary

All 5 planned fixes have been successfully implemented and verified:

*   **Fix 1 (Pydantic parsing robustness):** `[VERIFIED]` Handled currency strings (`"$1,250.50"`), symbols, commas, and nulls with `@field_validator`.
*   **Fix 2 (Async event loop starvation):** `[VERIFIED]` Offloaded blocking synchronous PyMuPDF and Ollama calls using `anyio.to_thread.run_sync()`.
*   **Fix 3 (Infrastructure error differentiation):** `[VERIFIED]` Separated model-not-found / timeout from extraction errors, mapped to `HTTP 503`. Added 60s timeout to `ollama.Client`.
*   **Fix 4 (File size limit guardrail):** `[VERIFIED]` Stream-limited file ingestion to `MAX_FILE_SIZE_BYTES` (25MB), returning `HTTP 413`.
*   **Fix 5 (CORS support):** `[VERIFIED]` Added `CORSMiddleware`, returning HTTP 200 with appropriate preflight headers on `OPTIONS`.

**Test Suite:** 22/22 unit and integration tests passing.

