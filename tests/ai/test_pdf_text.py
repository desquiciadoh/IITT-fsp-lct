"""extract_text on real PDFs (AI-R10) and the pdfplumber fallback (AI-R4)."""
import io
import logging
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


def test_a_broken_page_does_not_discard_the_others(monkeypatch, caplog):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            if self.text is None:
                raise KeyError("/Contents")
            return self.text

    class Reader:
        is_encrypted = False

        def __init__(self, stream):
            self.pages = [Page("Страница один"), Page(None), Page("Страница три")]

    monkeypatch.setattr(pdf_text.pypdf, "PdfReader", Reader)
    with caplog.at_level(logging.WARNING):
        text = extract_text(b"%PDF-1.4 fake")

    assert "Страница один" in text and "Страница три" in text
    assert any("KeyError" in r.getMessage() for r in caplog.records)


def test_parser_failures_are_logged_then_unreadable(monkeypatch, caplog):
    def broken_reader(stream):
        raise AttributeError("pypdf bug")

    def broken_plumber(stream):
        raise TypeError("pdfminer bug")

    monkeypatch.setattr(pdf_text.pypdf, "PdfReader", broken_reader)
    monkeypatch.setattr(pdf_text.pdfplumber, "open", broken_plumber)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(UnreadablePdf):
            extract_text(b"%PDF-1.4 fake")

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "AttributeError" in messages and "TypeError" in messages
    assert "bug" not in messages  # types only, never exception text


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
