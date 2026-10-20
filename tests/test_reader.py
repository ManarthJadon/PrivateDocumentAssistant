import io
from pathlib import Path

import pypdf
import pytest

from app.reader import ReadError, read_document

FIXTURES = Path(__file__).parent / "fixtures"


# --- reading each file type ---

def test_pdf_pages_are_numbered():
    pages = read_document("sample.pdf", (FIXTURES / "sample.pdf").read_bytes())
    assert len(pages) == 2
    assert pages[0][0] == 1 and "Apples" in pages[0][1]
    assert pages[1][0] == 2 and "Bananas" in pages[1][1]


def test_docx_has_no_page():
    pages = read_document("sample.docx", (FIXTURES / "sample.docx").read_bytes())
    assert len(pages) == 1
    assert pages[0][0] is None
    assert "Cherries" in pages[0][1]


def test_txt_and_md():
    assert read_document("a.txt", b"Hello") == [(None, "Hello")]
    assert read_document("a.md", b"Hello") == [(None, "Hello")]


def test_uppercase_extension_works():
    assert read_document("NOTES.TXT", b"Hello") == [(None, "Hello")]


def test_non_utf8_text_does_not_crash():
    # "café" saved the old Windows way (cp1252), not UTF-8
    pages = read_document("a.txt", "café".encode("cp1252"))
    assert "caf" in pages[0][1]


# --- problems the user should hear about ---

def make_blank_pdf() -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_blank_pdf_raises_no_text():
    with pytest.raises(ReadError, match="No text found"):
        read_document("blank.pdf", make_blank_pdf())


def test_empty_txt_raises_no_text():
    with pytest.raises(ReadError, match="No text found"):
        read_document("empty.txt", b"   ")


def test_unsupported_type():
    with pytest.raises(ReadError, match="Only .pdf, .docx, .txt and .md"):
        read_document("a.exe", b"whatever")


def test_broken_pdf():
    with pytest.raises(ReadError, match="Couldn't read this file"):
        read_document("broken.pdf", b"not a pdf")