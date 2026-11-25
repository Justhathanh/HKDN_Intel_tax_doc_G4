"""Đọc trực tiếp lớp chữ (text layer) của PDF điện tử, theo từng trang (G4T-62, ST08).

RFP EXT 02: "Extract digital PDF text when reliable; use OCR for scanned pages and image regions."

Nguyên tắc:
- Đọc từng trang, giữ `page_number` (bắt đầu từ 1) để làm neo nguồn (EXT 05: "page ... or XML path").
- Trang có chữ đọc được thì dùng luôn, KHÔNG gửi OCR.
- Trang không có chữ (PDF scan) hoặc chữ không đọc được (lỗi font, toàn ký tự thay thế) được đánh dấu
  cần OCR; không trả chuỗi rỗng như thể thành công.
- Chỉ đọc bytes trong bộ nhớ, không ghi gì ra đĩa: bản gốc không bị thay đổi (ING 04).
- Lỗi trả mã cố định, không đưa nội dung tài liệu hay thông báo của thư viện vào kết quả (SEC 04).
"""
import io
import logging
import unicodedata
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

EXTRACTOR_NAME = "pdf-text-layer"
EXTRACTOR_VERSION = "0.1.0"

# Một trang chỉ được coi là có lớp chữ khi có ít nhất chừng này ký tự không phải khoảng trắng.
# PDF scan đôi khi chứa vài ký tự rác (số trang, dấu chấm) nhưng không có nội dung thật.
MIN_PAGE_CHARS = 20
# Tỉ lệ ký tự thay thế U+FFFD tối đa; vượt mức là font không ánh xạ được Unicode, coi như không đọc được.
MAX_REPLACEMENT_RATIO = 0.05

# pypdf ghi cảnh báo cấu trúc (ví dụ "EOF marker not found") ra logging; giữ ở mức ERROR cho gọn log worker.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PdfTextError(Exception):
    """Lỗi đọc PDF với mã cố định (khai báo trong jobs.SAFE_ERRORS)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class PageText:
    page_number: int
    raw_text: str
    text: str            # đã chuẩn hóa: Unicode NFC, gộp khoảng trắng thừa; giữ nguyên dấu tiếng Việt và số 0 đầu
    char_count: int      # số ký tự không phải khoảng trắng
    has_text_layer: bool
    reason: str | None = None  # lý do cần OCR: "no_text_layer" | "unreadable_text"


@dataclass
class PdfTextResult:
    pages: list[PageText] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def ocr_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if not p.has_text_layer]

    @property
    def text_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if p.has_text_layer]

    @property
    def outcome(self) -> str:
        """`parsed` khi mọi trang có chữ; `needs_ocr` khi có ít nhất một trang phải OCR (hợp đồng G4T-68 mục 7)."""
        return "needs_ocr" if self.ocr_pages else "parsed"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _page(page_number: int, raw: str) -> PageText:
    text = _normalize(raw)
    chars = [c for c in text if not c.isspace()]
    char_count = len(chars)
    if char_count < MIN_PAGE_CHARS:
        return PageText(page_number, raw, text, char_count, False, "no_text_layer")
    if chars.count("�") / char_count > MAX_REPLACEMENT_RATIO:
        return PageText(page_number, raw, text, char_count, False, "unreadable_text")
    return PageText(page_number, raw, text, char_count, True)


def extract_pdf_text(data: bytes) -> PdfTextResult:
    """Đọc lớp chữ của từng trang. Ném PdfTextError("pdf_encrypted" | "pdf_unreadable") khi không mở được file."""
    if not data:
        raise PdfTextError("pdf_unreadable")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            # PDF chỉ khóa quyền (mật khẩu người dùng rỗng) vẫn đọc được; có mật khẩu thật thì dừng.
            try:
                if not reader.decrypt(""):
                    raise PdfTextError("pdf_encrypted")
            except (FileNotDecryptedError, NotImplementedError) as err:
                raise PdfTextError("pdf_encrypted") from err
        result = PdfTextResult()
        for index, page in enumerate(reader.pages, start=1):
            result.pages.append(_page(index, page.extract_text() or ""))
    except PdfTextError:
        raise
    except FileNotDecryptedError as err:
        raise PdfTextError("pdf_encrypted") from err
    except PdfReadError as err:
        raise PdfTextError("pdf_unreadable") from err
    except Exception as err:  # noqa: BLE001
        # PDF hỏng có thể làm pypdf ném đủ loại lỗi (IndexError, AttributeError...). File không đổi nên đọc
        # lại cũng hỏng: trả mã không thử lại thay vì để worker quy về internal_error và retry vô ích.
        raise PdfTextError("pdf_unreadable") from err
    if not result.pages:
        raise PdfTextError("pdf_unreadable")
    return result
