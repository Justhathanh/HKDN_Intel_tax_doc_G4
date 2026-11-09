"""Kiểm tra file khi tải lên (ING 03, giới hạn ở mục 2 của RFP).

Chưa có quét mã độc và sandbox: thuộc story riêng. Quét nội dung PDF chỉ là lớp cơ bản,
không thay thế ClamAV.
"""
import io
import re
import warnings
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from PIL import Image
from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 30
EXTENSIONS = {"pdf": "pdf", "jpg": "jpg", "jpeg": "jpg", "png": "png", "xml": "xml"}
MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png", "xml": "application/xml"}
_ACTIVE_PDF = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFiles)\b")


@dataclass
class Verdict:
    ok: bool
    kind: str | None = None
    reason: str | None = None
    quarantine: bool = False
    page_count: int | None = None


def sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"PK\x03\x04", b"Rar!", b"7z\xbc\xaf", b"\x1f\x8b")):
        return "archive"
    if data[:256].lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        return "xml"
    return None


def _inspect_pdf(data: bytes) -> Verdict:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return Verdict(False, reason="password_protected")
        pages = len(reader.pages)
        root = reader.trailer["/Root"].get_object()
        names = root.get("/Names")
        names = names.get_object() if names is not None else {}
    except Exception:
        return Verdict(False, reason="corrupt_file")
    if pages == 0:
        return Verdict(False, reason="corrupt_file")
    if pages > MAX_PDF_PAGES:
        return Verdict(False, reason="too_many_pages")
    if _ACTIVE_PDF.search(data) or "/JavaScript" in names or "/EmbeddedFiles" in names:
        return Verdict(False, reason="active_content", quarantine=True)
    return Verdict(True, kind="pdf", page_count=pages)


def _inspect_image(data: bytes, kind: str) -> Verdict:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
    except Exception:
        return Verdict(False, reason="corrupt_file")
    return Verdict(True, kind=kind, page_count=1)


def _inspect_xml(data: bytes) -> Verdict:
    try:
        SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException:
        return Verdict(False, reason="unsafe_xml", quarantine=True)
    except ParseError:
        return Verdict(False, reason="corrupt_file")
    return Verdict(True, kind="xml")


def inspect(name: str, data: bytes) -> Verdict:
    if not data:
        return Verdict(False, reason="empty_file")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    kind = sniff(data)
    if kind == "archive":
        return Verdict(False, reason="archive_not_supported")
    if ext not in EXTENSIONS or kind is None:
        return Verdict(False, reason="unsupported_format")
    if EXTENSIONS[ext] != kind:
        return Verdict(False, reason="extension_content_mismatch", quarantine=True)
    if kind == "pdf":
        return _inspect_pdf(data)
    if kind == "xml":
        return _inspect_xml(data)
    return _inspect_image(data, kind)
