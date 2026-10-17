"""Unit tests for PDF Ingestion and PyMuPDF text parsing."""

import pytest
from app.pdf_parser import (
    extract_text_from_pdf_bytes,
    truncate_text_for_context,
    ScannedPDFError,
)
from sample_data.generate_sample import create_native_pdf_bytes, create_scanned_pdf_bytes


def test_extract_native_pdf():
    pdf_bytes = create_native_pdf_bytes()
    text, pages = extract_text_from_pdf_bytes(pdf_bytes)

    assert pages == 2
    assert "Acme Tech Solutions Inc." in text
    assert "INV-2024-9988" in text
    assert "--- Page 1 ---" in text
    assert "--- Page 2 ---" in text


def test_scanned_pdf_raises_scanned_pdf_error():
    scanned_bytes = create_scanned_pdf_bytes()
    with pytest.raises(ScannedPDFError) as exc_info:
        extract_text_from_pdf_bytes(scanned_bytes)
    assert "OCR not supported yet, please upload a native PDF" in str(exc_info.value)


def test_empty_bytes_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        extract_text_from_pdf_bytes(b"")
    assert "empty" in str(exc_info.value)


def test_corrupt_bytes_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        extract_text_from_pdf_bytes(b"%PDF-invalid-bytes-12345")
    assert "Failed to parse PDF" in str(exc_info.value)


def test_truncate_text_for_context():
    sample_text = "A" * 100
    # Under limit
    truncated, was_cut = truncate_text_for_context(sample_text, max_chars=150)
    assert not was_cut
    assert len(truncated) == 100

    # Over limit
    truncated, was_cut = truncate_text_for_context(sample_text, max_chars=50)
    assert was_cut
    assert truncated.startswith("A" * 50)
    assert "[WARNING: Document text truncated to fit model context window]" in truncated
