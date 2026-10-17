"""Generate sample test PDFs: a native invoice PDF and an image-only (scanned) PDF."""

import io
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pymupdf


def create_native_pdf_bytes() -> bytes:
    """Generates a multi-page native PDF with a searchable text layer."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    # Page 1
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "INVOICE: Acme Tech Solutions Inc.")
    p.setFont("Helvetica", 12)
    p.drawString(100, 730, "Invoice Number: INV-2024-9988")
    p.drawString(100, 710, "Invoice Date: 2024-10-15")
    p.drawString(100, 680, "Vendor: Acme Tech Solutions Inc.")
    p.drawString(100, 650, "Description: Cloud Architecture Consulting")
    p.drawString(100, 630, "Quantity: 10 | Unit Price: 150.00 | Total: 1500.00")
    p.drawString(100, 600, "Tax Amount: 150.00")
    p.drawString(100, 580, "Total Amount Due: 1650.00")
    p.showPage()

    # Page 2
    p.setFont("Helvetica", 12)
    p.drawString(100, 750, "Terms and Conditions:")
    p.drawString(100, 730, "Payment due within 30 days. Wire transfer details enclosed.")
    p.showPage()

    p.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_scanned_pdf_bytes() -> bytes:
    """Generates a PDF containing only a rasterized image with no text layer."""
    # Create an image in memory
    img = Image.new("RGB", (600, 800), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 550, 750], outline=(0, 0, 0), width=2)
    draw.text((100, 100), "SCANNED INVOICE IMAGE", fill=(0, 0, 0))

    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_bytes = img_buffer.getvalue()

    # Embed raster image directly into PyMuPDF without searchable text
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    rect = pymupdf.Rect(0, 0, 600, 800)
    page.insert_image(rect, stream=img_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


if __name__ == "__main__":
    import os
    os.makedirs("sample_data", exist_ok=True)
    with open("sample_data/sample_invoice.pdf", "wb") as f:
        f.write(create_native_pdf_bytes())
    with open("sample_data/scanned_image.pdf", "wb") as f:
        f.write(create_scanned_pdf_bytes())
    print("Sample PDFs generated in sample_data/")
