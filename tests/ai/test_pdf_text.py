"""extract_text on real PDFs (AI-R10) and the pdfplumber fallback (AI-R4)."""
import io
from pathlib import Path

import llm_gateway.pdf_text as pdf_text
import pypdf
import pytest
from llm_gateway import UnreadablePdf, extract_text

CV_DIR = Path(__file__).resolve().parent / "fixtures" / "cv"


@pytest.mark.parametrize(
    ("pdf", "expected"),
    [
        ("cv_backend_middle.pdf", ["Иванов Иван Иванович", "Python Backend Developer", "FastAPI"]),
        ("cv_frontend_junior.pdf", ["Петрова Анна Сергеевна", "TypeScript", "Next.js"]),
        ("cv_ml_senior.pdf", ["Смирнов Дмитрий Алексеевич", "PyTorch", "CatBoost"]),
    ],
)
def test_hero_pdfs_have_a_text_layer(pdf, expected):
    text = extract_text((CV_DIR / pdf).read_bytes())
    for fragment in expected:
        assert fragment in text


def test_image_only_pdf_is_unreadable():
    with pytest.raises(UnreadablePdf):
        extract_text((CV_DIR / "cv_scanned_image_only.pdf").read_bytes())


def test_password_protected_pdf_is_unreadable():
    writer = pypdf.PdfWriter(clone_from=io.BytesIO((CV_DIR / "cv_backend_middle.pdf").read_bytes()))
    try:
        writer.encrypt(user_password="secret", owner_password="owner", algorithm="RC4-128")
    except Exception as e:  # pragma: no cover - depends on the installed crypto backend
        pytest.skip(f"pypdf cannot encrypt here: {type(e).__name__}")
    buf = io.BytesIO()
    writer.write(buf)

    with pytest.raises(UnreadablePdf):
        extract_text(buf.getvalue())


def test_pdfplumber_is_used_when_pypdf_finds_no_text(monkeypatch):
    class EmptyPage:
        def extract_text(self):
            return ""

    class EmptyReader:
        is_encrypted = False
        pages = [EmptyPage()]

        def __init__(self, stream):
            pass

    class PlumberPage:
        def extract_text(self):
            return "Текст из pdfplumber"

    class PlumberDoc:
        pages = [PlumberPage()]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pdf_text.pypdf, "PdfReader", EmptyReader)
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda stream: PlumberDoc())

    assert extract_text(b"%PDF-1.4 fake") == "Текст из pdfplumber"
