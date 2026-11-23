"""G4T-19: kiểm tra giới hạn 30 trang cho PDF (safety.inspect)."""
import hashlib
import io

from pypdf import PdfWriter

from app import safety


def make_pdf(pages: int, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_limit_is_30():
    assert safety.MAX_PDF_PAGES == 30


def test_pdf_1_page_accepted():
    verdict = safety.inspect("a.pdf", make_pdf(1))
    assert verdict.ok and verdict.page_count == 1 and verdict.kind == "pdf"


def test_pdf_exactly_30_pages_accepted():
    verdict = safety.inspect("a.pdf", make_pdf(30))
    assert verdict.ok and verdict.page_count == 30


def test_pdf_31_pages_rejected():
    verdict = safety.inspect("a.pdf", make_pdf(31))
    assert not verdict.ok
    assert verdict.reason == "too_many_pages"
    assert not verdict.quarantine
    assert verdict.page_count is None


def test_limit_follows_config_value():
    original = safety.MAX_PDF_PAGES
    try:
        safety.MAX_PDF_PAGES = 5
        assert safety.inspect("a.pdf", make_pdf(5)).ok
        assert safety.inspect("a.pdf", make_pdf(6)).reason == "too_many_pages"
    finally:
        safety.MAX_PDF_PAGES = original


def test_corrupted_pdf_rejected():
    verdict = safety.inspect("a.pdf", b"%PDF-1.4\nthis is not a real pdf")
    assert not verdict.ok and verdict.reason == "corrupt_file"


def test_truncated_pdf_rejected():
    verdict = safety.inspect("a.pdf", make_pdf(3)[:60])
    assert not verdict.ok and verdict.reason == "corrupt_file"


def test_password_protected_pdf_rejected():
    verdict = safety.inspect("a.pdf", make_pdf(2, password="secret"))
    assert not verdict.ok and verdict.reason == "password_protected"


def test_empty_file_rejected():
    verdict = safety.inspect("a.pdf", b"")
    assert not verdict.ok and verdict.reason == "empty_file"


def test_text_file_renamed_to_pdf_rejected():
    verdict = safety.inspect("a.pdf", b"just some plain text")
    assert not verdict.ok and verdict.reason == "unsupported_format"


def test_png_renamed_to_pdf_is_mismatch():
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    verdict = safety.inspect("a.pdf", png_header)
    assert not verdict.ok and verdict.reason == "extension_content_mismatch"


def test_page_limit_does_not_apply_to_xml():
    verdict = safety.inspect("a.xml", b"<root><item/></root>")
    assert verdict.ok and verdict.kind == "xml"


def test_original_bytes_unchanged_after_inspect():
    data = make_pdf(31)
    before = hashlib.sha256(data).hexdigest()
    safety.inspect("a.pdf", data)
    assert hashlib.sha256(data).hexdigest() == before
