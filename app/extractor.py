"""Local LLM Extraction Layer using Ollama and Gemma 2 (2B) with Pydantic v2 structured output."""

import re
from typing import List, Optional, Any
import json
import logging
from pydantic import BaseModel, Field, ValidationError, field_validator
import ollama
from app.config import settings

logger = logging.getLogger(__name__)


def _clean_float(val: Any) -> float:
    """Helper to sanitize currency strings, comma separated numbers, and nulls."""
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Remove currency symbols ($, €, £, etc.) and commas/spaces
        cleaned = re.sub(r"[^\d.-]", "", val.strip())
        if not cleaned or cleaned == "-":
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


class LineItem(BaseModel):
    """Individual invoice item line specification."""
    description: str = Field(..., description="Description of the goods or services rendered")
    quantity: float = Field(default=1.0, description="Quantity of items")
    unit_price: float = Field(default=0.0, description="Unit price per item")
    total_price: float = Field(default=0.0, description="Calculated total price (quantity * unit_price)")

    @field_validator("quantity", "unit_price", "total_price", mode="before")
    @classmethod
    def parse_numbers(cls, v: Any) -> float:
        return _clean_float(v)


class InvoiceData(BaseModel):
    """Strict structured representation of invoice financial data."""
    vendor_name: str = Field(..., description="Name of the vendor or company issuing the invoice")
    invoice_number: str = Field(..., description="Unique invoice identifier or code")
    invoice_date: str = Field(..., description="Date of the invoice formatted as YYYY-MM-DD or as written")
    total_amount: float = Field(..., description="Final invoice balance or total amount due")
    tax_amount: float = Field(default=0.0, description="Total VAT/GST/sales tax amount (0.0 if not specified)")
    line_items: List[LineItem] = Field(default_factory=list, description="Extracted individual invoice items")

    @field_validator("total_amount", "tax_amount", mode="before")
    @classmethod
    def parse_amounts(cls, v: Any) -> float:
        return _clean_float(v)

    @field_validator("line_items", mode="before")
    @classmethod
    def parse_line_items(cls, v: Any) -> list:
        if v is None:
            return []
        return v


class OllamaExtractionError(Exception):
    """Raised when Ollama inference or schema validation fails."""
    pass


class OllamaConnectionError(Exception):
    """Raised when Ollama daemon is unreachable."""
    pass


class OllamaModelNotFoundError(Exception):
    """Raised when the specified model is not downloaded or found in Ollama."""
    pass


DETERMINISTIC_SYSTEM_PROMPT = """You are a deterministic financial information extraction engine.
Your sole job is to extract invoice fields from the provided document text and populate the required JSON schema.

Strict Extraction Rules:
1. Extract data only if explicitly stated or directly inferable from the text.
2. Format all monetary figures (amounts, taxes, unit prices, totals) and quantities as numeric floats.
3. If tax amount is not specified or 0, return 0.0.
4. Extract all identifiable line items with their description, quantity, unit price, and total price.
5. Return ONLY valid JSON adhering to the provided schema. Do not include markdown codeblocks, explanatory preamble, or conversational commentary."""


class LocalInvoiceExtractor:
    """Orchestrates local inference against Gemma 2 using Ollama with structured output."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None, timeout: float = 60.0):
        self.host = host or settings.OLLAMA_HOST
        self.model = model or settings.MODEL_NAME
        self.timeout = timeout
        self.client = ollama.Client(host=self.host, timeout=self.timeout)

    def check_connection(self) -> bool:
        """Verifies if Ollama daemon is reachable and responding."""
        try:
            self.client.list()
            return True
        except Exception as exc:
            logger.warning(f"Ollama connection check failed: {exc}")
            return False

    def extract(self, invoice_text: str) -> InvoiceData:
        """Extracts structured invoice information using Gemma 2 with JSON schema constraints.
        
        Args:
            invoice_text: Cleaned/extracted text from the PDF.
            
        Returns:
            Validated InvoiceData Pydantic instance.
            
        Raises:
            OllamaConnectionError: If local Ollama service cannot be reached.
            OllamaModelNotFoundError: If requested model is not installed.
            OllamaExtractionError: If model response cannot be parsed or validated.
        """
        schema = InvoiceData.model_json_schema()
        messages = [
            {"role": "system", "content": DETERMINISTIC_SYSTEM_PROMPT},
            {"role": "user", "content": f"Invoice text:\n{invoice_text}"},
        ]

        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                format=schema,
                options={
                    "temperature": 0.0,  # Ensure maximum determinism
                },
            )
        except Exception as exc:
            err_msg = str(exc).lower()
            if "not found" in err_msg or "pull" in err_msg:
                raise OllamaModelNotFoundError(
                    f"Model '{self.model}' not found in Ollama. Please run `ollama pull {self.model}`."
                ) from exc
            if "connection" in err_msg or "refused" in err_msg or "failed to connect" in err_msg or "timeout" in err_msg:
                raise OllamaConnectionError(
                    f"Unable to connect to Ollama daemon at {self.host}. Please ensure Ollama is running."
                ) from exc
            raise OllamaExtractionError(f"Ollama inference error: {str(exc)}") from exc

        content = response.get("message", {}).get("content", "")
        if not content:
            raise OllamaExtractionError("Received empty response from local LLM.")

        try:
            # Parse and validate with Pydantic v2
            invoice_data = InvoiceData.model_validate_json(content)
            return invoice_data
        except (ValidationError, json.JSONDecodeError) as val_err:
            raise OllamaExtractionError(
                f"Model output failed strict schema validation: {str(val_err)}. Raw content: {content}"
            ) from val_err
