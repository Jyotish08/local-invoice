"""Unit tests for Pydantic v2 InvoiceData schema and LocalInvoiceExtractor."""

from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from app.extractor import (
    InvoiceData,
    LineItem,
    LocalInvoiceExtractor,
    OllamaExtractionError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)


def test_invoice_data_schema_valid():
    sample_data = {
        "vendor_name": "Acme Corp",
        "invoice_number": "INV-100",
        "invoice_date": "2024-04-01",
        "total_amount": 550.0,
        "tax_amount": 50.0,
        "line_items": [
            {
                "description": "Widget A",
                "quantity": 5.0,
                "unit_price": 100.0,
                "total_price": 500.0,
            }
        ],
    }
    invoice = InvoiceData.model_validate(sample_data)
    assert invoice.vendor_name == "Acme Corp"
    assert invoice.total_amount == 550.0
    assert len(invoice.line_items) == 1
    assert invoice.line_items[0].description == "Widget A"


def test_invoice_data_schema_missing_required_fields():
    incomplete_data = {
        "vendor_name": "Acme Corp"
        # missing invoice_number, total_amount, etc.
    }
    with pytest.raises(ValidationError):
        InvoiceData.model_validate(incomplete_data)


def test_extractor_successful_inference():
    extractor = LocalInvoiceExtractor()
    mock_response = {
        "message": {
            "content": """{
                "vendor_name": "Test Vendor",
                "invoice_number": "INV-777",
                "invoice_date": "2024-05-10",
                "total_amount": 120.0,
                "tax_amount": 20.0,
                "line_items": [
                    {
                        "description": "Consulting",
                        "quantity": 1.0,
                        "unit_price": 100.0,
                        "total_price": 100.0
                    }
                ]
            }"""
        }
    }

    with patch.object(extractor.client, "chat", return_value=mock_response):
        result = extractor.extract("Sample invoice text")
        assert isinstance(result, InvoiceData)
        assert result.vendor_name == "Test Vendor"
        assert result.invoice_number == "INV-777"
        assert result.total_amount == 120.0
        assert len(result.line_items) == 1


def test_extractor_invalid_json_response():
    extractor = LocalInvoiceExtractor()
    mock_response = {"message": {"content": "Not a valid JSON string"}}

    with patch.object(extractor.client, "chat", return_value=mock_response):
        with pytest.raises(OllamaExtractionError):
            extractor.extract("Sample invoice text")


def test_extractor_connection_error():
    extractor = LocalInvoiceExtractor()

    with patch.object(
        extractor.client, "chat", side_effect=Exception("Failed to connect to localhost:11434")
    ):
        with pytest.raises(OllamaConnectionError) as exc_info:
            extractor.extract("Sample invoice text")
        assert "Unable to connect to Ollama daemon" in str(exc_info.value)


def test_extractor_model_not_found_error():
    extractor = LocalInvoiceExtractor()

    with patch.object(
        extractor.client, "chat", side_effect=Exception("model 'gemma2:2b' not found, try pulling it first")
    ):
        with pytest.raises(OllamaModelNotFoundError) as exc_info:
            extractor.extract("Sample invoice text")
        assert "not found in Ollama" in str(exc_info.value)



def test_invoice_data_coerces_currency_strings_and_nulls():
    raw_data = {
        "vendor_name": "Acme Corp",
        "invoice_number": "INV-100",
        "invoice_date": "2024-04-01",
        "total_amount": "$1,250.50",
        "tax_amount": None,
        "line_items": [
            {
                "description": "Widget A",
                "quantity": "2.0",
                "unit_price": "$100.00",
                "total_price": "200.00",
            }
        ],
    }
    invoice = InvoiceData.model_validate(raw_data)
    assert invoice.total_amount == 1250.50
    assert invoice.tax_amount == 0.0
    assert invoice.line_items[0].unit_price == 100.00
    assert invoice.line_items[0].total_price == 200.00


def test_invoice_data_null_line_items_defaults_to_empty_list():
    raw_data = {
        "vendor_name": "Acme Corp",
        "invoice_number": "INV-100",
        "invoice_date": "2024-04-01",
        "total_amount": "500",
        "tax_amount": "$0.00",
        "line_items": None,
    }
    invoice = InvoiceData.model_validate(raw_data)
    assert invoice.total_amount == 500.0
    assert invoice.tax_amount == 0.0
    assert invoice.line_items == []

