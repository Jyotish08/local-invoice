"""Integration and API Route Tests for FastAPI Application."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.extractor import InvoiceData, LineItem
from sample_data.generate_sample import create_native_pdf_bytes, create_scanned_pdf_bytes

client = TestClient(app)


def test_health_check_ollama_online():
    with patch("app.main.extractor.check_connection", return_value=True):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["ollama_connected"] is True
        assert data["model"] == "gemma2:2b"


def test_health_check_ollama_offline():
    with patch("app.main.extractor.check_connection", return_value=False):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["ollama_connected"] is False


def test_extract_invalid_file_extension():
    response = client.post(
        "/api/v1/extract",
        files={"file": ("test.txt", b"plain text content", "text/plain")},
    )
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]


def test_extract_scanned_pdf_returns_400():
    scanned_bytes = create_scanned_pdf_bytes()
    response = client.post(
        "/api/v1/extract",
        files={"file": ("scanned.pdf", scanned_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "OCR not supported yet, please upload a native PDF"


def test_extract_native_pdf_success():
    native_bytes = create_native_pdf_bytes()
    mock_invoice = InvoiceData(
        vendor_name="Acme Tech Solutions Inc.",
        invoice_number="INV-2024-9988",
        invoice_date="2024-10-15",
        total_amount=1650.0,
        tax_amount=150.0,
        line_items=[
            LineItem(
                description="Cloud Architecture Consulting",
                quantity=10.0,
                unit_price=150.0,
                total_price=1500.0,
            )
        ],
    )

    with patch("app.main.extractor.extract", return_value=mock_invoice):
        response = client.post(
            "/api/v1/extract",
            files={"file": ("invoice.pdf", native_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["vendor_name"] == "Acme Tech Solutions Inc."
        assert data["invoice_number"] == "INV-2024-9988"
        assert data["total_amount"] == 1650.0
        assert data["tax_amount"] == 150.0
        assert len(data["line_items"]) == 1
        assert data["line_items"][0]["description"] == "Cloud Architecture Consulting"


def test_extract_ollama_service_unavailable():
    native_bytes = create_native_pdf_bytes()
    from app.extractor import OllamaConnectionError

    with patch(
        "app.main.extractor.extract",
        side_effect=OllamaConnectionError("Ollama daemon is offline"),
    ):
        response = client.post(
            "/api/v1/extract",
            files={"file": ("invoice.pdf", native_bytes, "application/pdf")},
        )
        assert response.status_code == 503
        assert "Ollama daemon is offline" in response.json()["detail"]


def test_extract_ollama_model_not_found_returns_503():
    native_bytes = create_native_pdf_bytes()
    from app.extractor import OllamaModelNotFoundError

    with patch(
        "app.main.extractor.extract",
        side_effect=OllamaModelNotFoundError("Model 'gemma2:2b' not found in Ollama"),
    ):
        response = client.post(
            "/api/v1/extract",
            files={"file": ("invoice.pdf", native_bytes, "application/pdf")},
        )
        assert response.status_code == 503
        assert "Model 'gemma2:2b' not found in Ollama" in response.json()["detail"]


def test_extract_file_too_large_returns_413():
    with patch("app.main.settings.MAX_FILE_SIZE_BYTES", 100):
        oversized_bytes = b"%PDF-" + b"0" * 150
        response = client.post(
            "/api/v1/extract",
            files={"file": ("large.pdf", oversized_bytes, "application/pdf")},
        )
        assert response.status_code == 413
        assert "exceeds maximum allowable size" in response.json()["detail"]


def test_cors_preflight_headers():
    response = client.options(
        "/api/v1/extract",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"



