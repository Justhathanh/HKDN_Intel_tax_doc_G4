"""Mã lỗi thống nhất của API; frontend dựa vào error_code để hiển thị."""
from fastapi import Request
from fastapi.responses import JSONResponse

ERRORS: dict[str, tuple[int, str]] = {
    "unauthenticated": (401, "Bạn chưa đăng nhập."),
    "not_found": (404, "Không tìm thấy dữ liệu hoặc bạn không có quyền truy cập."),
    "empty_file": (400, "Chưa có file hoặc file rỗng."),
    "missing_idempotency_key": (400, "Thiếu header Idempotency-Key."),
    "invalid_idempotency_key": (400, "Idempotency-Key không hợp lệ (tối đa 128 ký tự)."),
    "idempotency_key_conflict": (409, "Idempotency-Key này đã được dùng cho một file khác."),
    "file_too_large": (413, "File vượt quá giới hạn 20 MiB."),
    "unsupported_format": (415, "Định dạng không được hỗ trợ. Chỉ nhận PDF, JPG, PNG, XML."),
    "archive_not_supported": (415, "Không nhận file nén."),
    "extension_content_mismatch": (415, "Đuôi file không khớp nội dung; file đã được cách ly."),
    "too_many_pages": (422, "PDF vượt quá 30 trang."),
    "corrupt_file": (422, "File bị hỏng, không đọc được."),
    "password_protected": (422, "File có mật khẩu, không xử lý được."),
    "active_content": (422, "File chứa nội dung thực thi; file đã được cách ly."),
    "unsafe_xml": (422, "XML có cấu trúc không an toàn; file đã được cách ly."),
    "quarantined": (422, "File này đang bị cách ly."),
}


class ApiError(Exception):
    def __init__(self, code: str, submission_id: str | None = None, document_id: str | None = None):
        self.code, self.submission_id, self.document_id = code, submission_id, document_id


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    status, message = ERRORS[exc.code]
    return JSONResponse(status_code=status, content={
        "error_code": exc.code, "message": message,
        "submission_id": exc.submission_id, "document_id": exc.document_id})
