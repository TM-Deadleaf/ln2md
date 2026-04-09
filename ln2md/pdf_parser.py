from __future__ import annotations

import re
from pathlib import Path


class PDFParserError(Exception):
    """Raised when a resume PDF cannot be converted into usable profile text."""


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract and clean text from a resume PDF.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Cleaned profile text.

    Raises:
        FileNotFoundError: If the file does not exist.
        PDFParserError: If the PDF is invalid, empty, scanned/image-only, or yields no usable text.
    """
    pdf_path = Path(file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if not pdf_path.is_file():
        raise PDFParserError(f"Expected a file path, got: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PDFParserError(f"Unsupported file type: {pdf_path.suffix or '<none>'}. Expected .pdf")
    if pdf_path.stat().st_size == 0:
        raise PDFParserError("The PDF file is empty.")

    try:
        import pdfplumber
    except ImportError as exc:
        raise PDFParserError(
            "Missing dependency 'pdfplumber'. Install it before parsing PDF resumes."
        ) from exc

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if not pdf.pages:
                raise PDFParserError("The PDF contains no pages.")

            raw_pages: list[str] = []
            text_pages = 0

            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                page_text = page_text.strip()
                if page_text:
                    text_pages += 1
                    raw_pages.append(page_text)

    except PDFParserError:
        raise
    except Exception as exc:
        raise PDFParserError(f"Invalid or unreadable PDF: {pdf_path}") from exc

    if text_pages == 0:
        raise PDFParserError(
            "No extractable text found. The document appears to be scanned or image-only."
        )

    cleaned_text = _clean_extracted_text("\n\n".join(raw_pages))
    if not cleaned_text:
        raise PDFParserError("Extracted PDF text is empty after cleaning.")
    if not re.search(r"[A-Za-z0-9]", cleaned_text):
        raise PDFParserError("The PDF did not contain usable profile text.")

    return cleaned_text


def _clean_extracted_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\uf0b7", "- ")
    text = text.replace("\u2022", "- ")
    text = text.replace("\u25cf", "- ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Repair words broken across line-wrap hyphenation.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue

        line = re.sub(r"[ \t]+", " ", line)
        line = re.sub(r"\s+([,.;:])", r"\1", line)
        line = re.sub(r"^Page\s+\d+(\s+of\s+\d+)?$", "", line, flags=re.IGNORECASE)
        lines.append(line)

    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                normalized.append("")
            previous_blank = True
            continue

        normalized.append(line)
        previous_blank = False

    cleaned = "\n".join(normalized).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned
