"""PDF text extraction module.

Extracts text using pypdf with optional pdfplumber fallback.
Raises UnreadablePdf if text cannot be extracted or is empty.
"""
from __future__ import annotations

import io
from .types import UnreadablePdf

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


def extract_text(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes.

    Raises:
        UnreadablePdf: If PDF is empty, malformed, image-only (scanned),
                       or produces no extractable text.
    """
    if not pdf_bytes:
        raise UnreadablePdf("PDF file is empty (0 bytes)")

    extracted_parts: list[str] = []

    # 1. Primary extractor: pypdf
    if HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    extracted_parts.append(page_text.strip())
        except Exception:
            # Fall through to pdfplumber if available
            extracted_parts = []

    full_text = "\n\n".join(extracted_parts).strip()
    if full_text:
        return full_text

    # 2. Fallback extractor: pdfplumber
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        extracted_parts.append(page_text.strip())
        except Exception as e:
            raise UnreadablePdf(f"Failed to read PDF with pdfplumber: {e}") from e

    full_text = "\n\n".join(extracted_parts).strip()
    if not full_text:
        raise UnreadablePdf("PDF does not contain extractable text (possibly scanned or image-only)")

    return full_text
