"""PDF Parsing and Ingestion Layer using PyMuPDF (fitz)."""

from typing import Tuple
import pymupdf  # recommended modern PyMuPDF import
from app.config import settings


class ScannedPDFError(Exception):
    """Raised when a PDF does not contain an extractable native text layer."""
    pass


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> Tuple[str, int]:
    """Extracts raw text from PDF bytes across all pages.
    
    Args:
        pdf_bytes: The raw byte content of the PDF.
        
    Returns:
        A tuple of (aggregated_text, page_count).
        
    Raises:
        ValueError: If document cannot be parsed as a valid PDF.
        ScannedPDFError: If extracted text is under the minimum character threshold.
    """
    if not pdf_bytes:
        raise ValueError("Provided PDF file is empty (0 bytes).")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Failed to parse PDF document: {str(exc)}") from exc

    page_texts = []
    page_count = len(doc)

    for page_num in range(page_count):
        page = doc.load_page(page_num)
        text = page.get_text("text").strip()
        if text:
            page_texts.append(f"--- Page {page_num + 1} ---\n{text}")

    doc.close()

    full_text = "\n\n".join(page_texts).strip()

    # Calculate non-whitespace character count to determine if a real text layer exists
    non_ws_char_count = len("".join(full_text.split()))
    if non_ws_char_count < settings.MIN_TEXT_CHARS_THRESHOLD:
        raise ScannedPDFError("OCR not supported yet, please upload a native PDF")

    return full_text, page_count


def truncate_text_for_context(text: str, max_chars: int = None) -> Tuple[str, bool]:
    """Truncates text to prevent overflowing the Gemma 2 context window.
    
    Args:
        text: The full extracted invoice text.
        max_chars: Optional character limit (defaults to settings.MAX_CONTEXT_CHARS).
        
    Returns:
        Tuple of (truncated_text, is_truncated).
    """
    if max_chars is None:
        max_chars = settings.MAX_CONTEXT_CHARS

    if len(text) <= max_chars:
        return text, False

    truncated = text[:max_chars]
    # Add a clean truncation notice
    truncated += "\n\n[WARNING: Document text truncated to fit model context window]"
    return truncated, True
