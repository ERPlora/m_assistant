"""Tests for the file processor service."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from modules.assistant.services.file_processor import (
    MAX_FILE_SIZE,
    process_file,
)


# ============================================================================
# IMAGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_process_image_jpg():
    """JPEG images are returned as base64 for Vision."""
    fake_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    result = await process_file(fake_jpg, "photo.jpg", "image/jpeg")

    assert len(result) == 2
    assert result[0]["type"] == "input_text"
    assert "photo.jpg" in result[0]["text"]
    assert result[1]["type"] == "input_image"
    assert result[1]["image_url"].startswith("data:image/jpeg;base64,")

    # Verify round-trip
    b64_data = result[1]["image_url"].split(",", 1)[1]
    decoded = base64.b64decode(b64_data)
    assert decoded == fake_jpg


@pytest.mark.asyncio
async def test_process_image_png():
    """PNG images are returned as base64 for Vision."""
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    result = await process_file(fake_png, "screenshot.png", "image/png")

    assert len(result) == 2
    assert result[0]["type"] == "input_text"
    assert "screenshot.png" in result[0]["text"]
    assert result[1]["type"] == "input_image"
    assert result[1]["image_url"].startswith("data:image/png;base64,")


# ============================================================================
# TEXT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_process_text_plain():
    """Plain text files are read directly."""
    content = "Hello, world!\nSecond line."
    result = await process_file(content.encode("utf-8"), "readme.txt", "text/plain")

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "readme.txt" in result[0]["text"]
    assert "Hello, world!" in result[0]["text"]
    assert "Second line." in result[0]["text"]


@pytest.mark.asyncio
async def test_process_text_csv():
    """CSV files are read as text."""
    csv_content = "name,price\nWidget,9.99\nGadget,19.99"
    result = await process_file(csv_content.encode("utf-8"), "products.csv", "text/csv")

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "products.csv" in result[0]["text"]
    assert "Widget" in result[0]["text"]


@pytest.mark.asyncio
async def test_process_text_truncation():
    """Very long text files are truncated."""
    long_text = "x" * 60_000
    result = await process_file(long_text.encode("utf-8"), "huge.txt", "text/plain")

    assert len(result) == 1
    assert "truncated" in result[0]["text"]
    # Content should be cut at 50k chars
    assert len(result[0]["text"]) < 55_000


# ============================================================================
# PDF TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_process_pdf_with_text():
    """PDF with extractable text uses pdfplumber (cheap path)."""
    fake_pdf = b"%PDF-1.4 fake content"

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Invoice #1234\nTotal: $500.00\nCustomer: Acme Corp with lots of text content here"
    mock_page.extract_tables.return_value = []

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch("modules.assistant.services.file_processor.pdfplumber", create=True):
        # Make pdfplumber importable within _extract_pdf_text
        import sys
        mock_module = MagicMock()
        mock_module.open.return_value = mock_pdf
        sys.modules["pdfplumber"] = mock_module

        try:
            result = await process_file(fake_pdf, "invoice.pdf", "application/pdf")
        finally:
            del sys.modules["pdfplumber"]

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "invoice.pdf" in result[0]["text"]
    assert "Invoice #1234" in result[0]["text"]


@pytest.mark.asyncio
async def test_process_pdf_scanned():
    """Scanned PDF (no text) falls back to PyMuPDF image conversion."""
    fake_pdf = b"%PDF-1.4 scanned"
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

    # Mock pdfplumber to return empty text
    mock_pdf_plumber = MagicMock()
    mock_page_plumber = MagicMock()
    mock_page_plumber.extract_text.return_value = ""
    mock_page_plumber.extract_tables.return_value = []
    mock_pdf_plumber.pages = [mock_page_plumber]
    mock_pdf_plumber.__enter__ = MagicMock(return_value=mock_pdf_plumber)
    mock_pdf_plumber.__exit__ = MagicMock(return_value=False)

    # Mock PyMuPDF
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = fake_png

    mock_fitz_page = MagicMock()
    mock_fitz_page.get_pixmap.return_value = mock_pix

    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_fitz_page]))

    import sys

    mock_pdfplumber_mod = MagicMock()
    mock_pdfplumber_mod.open.return_value = mock_pdf_plumber

    mock_fitz_mod = MagicMock()
    mock_fitz_mod.open.return_value = mock_doc
    mock_fitz_mod.Matrix.return_value = MagicMock()

    sys.modules["pdfplumber"] = mock_pdfplumber_mod
    sys.modules["fitz"] = mock_fitz_mod

    try:
        result = await process_file(fake_pdf, "scan.pdf", "application/pdf")
    finally:
        del sys.modules["pdfplumber"]
        del sys.modules["fitz"]

    assert len(result) == 2
    assert result[0]["type"] == "input_text"
    assert "Scanned document" in result[0]["text"]
    assert "scan.pdf" in result[0]["text"]
    assert result[1]["type"] == "input_image"
    assert result[1]["image_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_empty_pdf():
    """PDF with no text and no image conversion returns error message."""
    fake_pdf = b"%PDF-1.4 empty"

    # Mock both libraries to return nothing
    mock_pdf_plumber = MagicMock()
    mock_page_plumber = MagicMock()
    mock_page_plumber.extract_text.return_value = ""
    mock_page_plumber.extract_tables.return_value = []
    mock_pdf_plumber.pages = [mock_page_plumber]
    mock_pdf_plumber.__enter__ = MagicMock(return_value=mock_pdf_plumber)
    mock_pdf_plumber.__exit__ = MagicMock(return_value=False)

    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([]))

    import sys

    mock_pdfplumber_mod = MagicMock()
    mock_pdfplumber_mod.open.return_value = mock_pdf_plumber

    mock_fitz_mod = MagicMock()
    mock_fitz_mod.open.return_value = mock_doc

    sys.modules["pdfplumber"] = mock_pdfplumber_mod
    sys.modules["fitz"] = mock_fitz_mod

    try:
        result = await process_file(fake_pdf, "empty.pdf", "application/pdf")
    finally:
        del sys.modules["pdfplumber"]
        del sys.modules["fitz"]

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "Could not read PDF" in result[0]["text"]


# ============================================================================
# UNSUPPORTED / SIZE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unsupported_type():
    """Unsupported MIME types return an error message."""
    result = await process_file(b"binary data", "file.exe", "application/octet-stream")

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "Unsupported file type" in result[0]["text"]


@pytest.mark.asyncio
async def test_file_too_large():
    """Files exceeding MAX_FILE_SIZE are rejected."""
    huge = b"\x00" * (MAX_FILE_SIZE + 1)
    result = await process_file(huge, "huge.pdf", "application/pdf")

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "too large" in result[0]["text"]
    assert "10 MB" in result[0]["text"]


# ============================================================================
# OFFICE DOCS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_process_xlsx():
    """Excel files use openpyxl for text extraction."""
    fake_xlsx = b"PK\x03\x04" + b"\x00" * 100

    mock_ws = MagicMock()
    mock_ws.iter_rows.return_value = [
        ("Product", "Price", "Stock"),
        ("Widget", "9.99", "100"),
        ("Gadget", "19.99", "50"),
    ]

    mock_wb = MagicMock()
    mock_wb.sheetnames = ["Sheet1"]
    mock_wb.__getitem__ = MagicMock(return_value=mock_ws)

    import sys
    mock_openpyxl = MagicMock()
    mock_openpyxl.load_workbook.return_value = mock_wb
    sys.modules["openpyxl"] = mock_openpyxl

    try:
        result = await process_file(
            fake_xlsx,
            "inventory.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    finally:
        del sys.modules["openpyxl"]

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "inventory.xlsx" in result[0]["text"]
    assert "Widget" in result[0]["text"]


@pytest.mark.asyncio
async def test_process_docx():
    """Word documents use python-docx for text extraction."""
    fake_docx = b"PK\x03\x04" + b"\x00" * 100

    mock_para1 = MagicMock()
    mock_para1.text = "Contract Agreement"
    mock_para2 = MagicMock()
    mock_para2.text = "This contract is between Party A and Party B."
    mock_para3 = MagicMock()
    mock_para3.text = ""  # Empty paragraph, should be skipped

    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]

    import sys
    mock_docx_mod = MagicMock()
    mock_docx_mod.Document.return_value = mock_doc
    sys.modules["docx"] = mock_docx_mod

    try:
        result = await process_file(
            fake_docx,
            "contract.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    finally:
        del sys.modules["docx"]

    assert len(result) == 1
    assert result[0]["type"] == "input_text"
    assert "contract.docx" in result[0]["text"]
    assert "Contract Agreement" in result[0]["text"]
    assert "Party A and Party B" in result[0]["text"]
