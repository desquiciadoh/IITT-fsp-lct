"""PDF text extraction module.

Extracts text using pypdf with pdfplumber fallback.
Raises UnreadablePdf if PDF is empty, malformed, password-protected,
or produces no extractable text (scanned/image-only).
Enforces caps per AI-2: <= 20 pages and <= 200 000 characters.
"""
from __future__ import annotations

import io

import pdfplumber
import pypdf

from .types import UnreadablePdf

MAX_PAGES = 20
MAX_CHARS = 200_000


def extract_text(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes.

    Raises:
        UnreadablePdf: If PDF is empty, encrypted/password-protected, malformed,
                       image-only (scanned), or produces no extractable text.
    """
    if not pdf_bytes or len(pdf_bytes.strip()) == 0:
        raise UnreadablePdf("PDF file is empty (0 bytes)")

    extracted_parts: list[str] = []

    # 1. Primary extractor: pypdf
    try:
        stream = io.BytesIO(pdf_bytes)
        reader = pypdf.PdfReader(stream)

        # Check encryption
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
                if decrypted == 0:  # 0 indicates failed decrypt with empty password
                    raise UnreadablePdf("PDF is encrypted and password protected")
            except Exception as e:
                raise UnreadablePdf("PDF is encrypted and password protected") from e

        for page in reader.pages[:MAX_PAGES]:
            text = page.extract_text() or ""
            if text.strip():
                extracted_parts.append(text.strip())
    except UnreadablePdf:
        raise
    except Exception:
        # Fall through to pdfplumber
        extracted_parts = []

    full_text = "\n\n".join(extracted_parts).strip()
    if full_text:
        return full_text[:MAX_CHARS]

    # 2. Fallback extractor: pdfplumber
    try:
        stream = io.BytesIO(pdf_bytes)
        with pdfplumber.open(stream) as pdf:
            for page in pdf.pages[:MAX_PAGES]:
                text = page.extract_text() or ""
                if text.strip():
                    extracted_parts.append(text.strip())
    except UnreadablePdf:
        raise
    except Exception as e:
        raise UnreadablePdf(f"Failed to read PDF with pdfplumber: {type(e).__name__}") from e

    full_text = "\n\n".join(extracted_parts).strip()
    if not full_text:
        raise UnreadablePdf("PDF does not contain extractable text (possibly scanned or image-only)")

    return full_text[:MAX_CHARS]
