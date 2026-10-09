"""PDF text extraction module.

Extracts text using pypdf with pdfplumber fallback.
Raises UnreadablePdf if PDF is empty, malformed, password-protected,
or produces no extractable text (scanned/image-only).
Enforces caps per AI-2: <= 20 pages and <= 200 000 characters.

Parser failures on an uploaded file are logged with the exception type and the file hash (never
text) and end as UnreadablePdf; a broken page is skipped instead of discarding the whole file.
"""
from __future__ import annotations

import hashlib
import io
import logging

import pdfplumber
import pypdf

from .types import UnreadablePdf

logger = logging.getLogger(__name__)

MAX_PAGES = 20
MAX_CHARS = 200_000


def _page_texts(pages, parser: str, sha: str) -> list[str]:
    texts: list[str] = []
    for number, page in enumerate(pages):
        try:
            text = page.extract_text() or ""
        except MemoryError:
            raise
        except Exception as e:  # one broken page must not discard the others
            logger.warning("%s page %d failed (%s, sha=%s)", parser, number, type(e).__name__, sha)
            continue
        if text.strip():
            texts.append(text.strip())
    return texts


def extract_text(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes.

    Raises:
        UnreadablePdf: If PDF is empty, encrypted/password-protected, malformed,
                       image-only (scanned), or produces no extractable text.
    """
    if not pdf_bytes or len(pdf_bytes.strip()) == 0:
        raise UnreadablePdf("PDF file is empty (0 bytes)")
    sha = hashlib.sha256(pdf_bytes).hexdigest()[:12]

    # 1. Primary extractor: pypdf
    parts: list[str] = []
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
            except Exception as e:
                raise UnreadablePdf("PDF is encrypted and password protected") from e
            if decrypted == 0:  # 0: the empty password does not open it
                raise UnreadablePdf("PDF is encrypted and password protected")
        parts = _page_texts(reader.pages[:MAX_PAGES], "pypdf", sha)
    except (UnreadablePdf, MemoryError):
        raise
    except Exception as e:
        logger.warning("pypdf failed (%s, sha=%s), trying pdfplumber", type(e).__name__, sha)
        parts = []

    full_text = "\n\n".join(parts).strip()
    if full_text:
        return full_text[:MAX_CHARS]

    # 2. Fallback extractor: pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            parts = _page_texts(pdf.pages[:MAX_PAGES], "pdfplumber", sha)
    except MemoryError:
        raise
    except Exception as e:
        logger.warning("pdfplumber failed (%s, sha=%s)", type(e).__name__, sha)
        raise UnreadablePdf(f"Failed to read PDF with pdfplumber: {type(e).__name__}") from e

    full_text = "\n\n".join(parts).strip()
    if not full_text:
        raise UnreadablePdf("PDF does not contain extractable text (possibly scanned or image-only)")

    return full_text[:MAX_CHARS]
