"""FastAPI Main Application and Routing Layer for Local Invoice Extraction."""

from typing import Dict, Any
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse

import anyio
from app.config import settings
from app.pdf_parser import (
    extract_text_from_pdf_bytes,
    truncate_text_for_context,
    ScannedPDFError,
)
from app.extractor import (
    InvoiceData,
    LocalInvoiceExtractor,
    OllamaExtractionError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)

from fastapi.middleware.cors import CORSMiddleware

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("invoice_extractor")

app = FastAPI(
    title="local-invoice",
    description="Offline microservice using PyMuPDF and Ollama Gemma 2 for financial invoice parsing.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

extractor = LocalInvoiceExtractor()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """Health check endpoint verifying microservice status and Ollama connectivity."""
    ollama_ready = await anyio.to_thread.run_sync(extractor.check_connection)
    return {
        "status": "healthy" if ollama_ready else "degraded",
        "ollama_connected": ollama_ready,
        "model": settings.MODEL_NAME,
        "ollama_host": settings.OLLAMA_HOST,
        "privacy": "100% Local / Zero Cloud Leakage",
    }


@app.post(
    "/api/v1/extract",
    response_model=InvoiceData,
    status_code=status.HTTP_200_OK,
    summary="Extract structured financial data from an uploaded PDF invoice",
    responses={
        200: {"description": "Structured invoice data successfully extracted."},
        400: {"description": "Invalid file type or non-searchable/scanned PDF without text layer."},
        422: {"description": "Document text could not be mapped to required invoice schema."},
        503: {"description": "Local Ollama daemon is unreachable or offline."},
    },
)
async def extract_invoice(file: UploadFile = File(...)) -> InvoiceData:
    """Ingests a native PDF invoice, extracts text with PyMuPDF, and parses structured data via Gemma 2.
    
    Returns:
        JSON adhering to the InvoiceData schema, directly consumable by pandas/TabPFN.
    """
    # 1. Validate file extension / MIME type
    filename = file.filename or ""
    if not (filename.lower().endswith(".pdf") or file.content_type == "application/pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF files are supported.",
        )

    # 2. Read bytes into memory with size limit safeguard
    max_bytes = settings.MAX_FILE_SIZE_BYTES
    try:
        pdf_bytes = await file.read(max_bytes + 1)
        if len(pdf_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
                detail=f"File exceeds maximum allowable size of {max_bytes // (1024 * 1024)}MB.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed reading uploaded file stream: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(exc)}",
        )

    # 3. Parse PDF with PyMuPDF
    try:
        raw_text, page_count = await anyio.to_thread.run_sync(extract_text_from_pdf_bytes, pdf_bytes)
        logger.info(f"Successfully extracted {len(raw_text)} chars from {page_count} pages.")
    except ScannedPDFError as scanned_err:
        logger.warning(f"Scanned PDF detected without text layer: {scanned_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OCR not supported yet, please upload a native PDF",
        )
    except ValueError as val_err:
        logger.warning(f"Malformed PDF: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    # 4. Context truncation safeguard
    safe_text, was_truncated = truncate_text_for_context(raw_text)
    if was_truncated:
        logger.warning("Input text exceeded context window and was truncated.")

    # 5. Extract structured invoice data with Ollama + Gemma 2
    try:
        invoice_data = await anyio.to_thread.run_sync(extractor.extract, safe_text)
        return invoice_data
    except (OllamaConnectionError, OllamaModelNotFoundError) as infra_err:
        logger.error(f"Ollama infrastructure error: {infra_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(infra_err),
        )
    except OllamaExtractionError as ext_err:
        logger.error(f"Ollama extraction error: {ext_err}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ext_err),
        )
