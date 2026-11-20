# G4T-73 – Chính sách Retry, Backoff và Dead Letter Queue (ST06)

## 1. Phân loại lỗi (Transient vs Permanent)

Hệ thống chỉ lưu các mã lỗi chuẩn hóa trong `SAFE_ERRORS` (`backend/app/jobs.py`), tuyệt đối không lưu stack trace hoặc nội dung trích xuất từ tài liệu kế toán (SEC 04).

### Lỗi tạm thời – Có thể thử lại (`error_retryable = true`)
* `ocr_timeout`: Dịch vụ OCR phản hồi quá thời gian.
* `ocr_unavailable`: Dịch vụ OCR tạm thời gián đoạn.
* `quota_exceeded`: Chạm hạn mức gọi dịch vụ xử lý.
* `lease_expired`: Worker mất kết nối quá thời hạn giữ việc (`DEFAULT_LEASE = 10 phút`).
* `internal_error`: Lỗi hạ tầng / kết nối nội bộ ngoài dự kiến.

### Lỗi vĩnh viễn – Không thử lại (`error_retryable = false`)
* `original_missing`: Không tìm thấy tệp gốc trong kho lưu trữ.
* `original_tampered`: Mã băm SHA-256 của tệp gốc không khớp (vi phạm toàn vẹn ING 04).
* `unsupported_document`: Loại tài liệu chưa được hỗ trợ.
* `parser_error`: Cấu trúc tệp tài liệu bị hỏng, không thể phân tích.

## 2. Giới hạn số lần thử & Chiến lược Backoff

* **Số lần thử tối đa mặc định (`DEFAULT_MAX_ATTEMPTS`):** `3` lần (`attempt_no` từ `1` đến `3`).
* **Công thức chờ tăng dần (Exponential Backoff):**
  `delay(attempt_no) = min(30s * 2^(attempt_no - 1), 15 phút)`
  * Lần 1 thất bại -> chờ **30 giây** trước khi chạy lần 2.
  * Lần 2 thất bại -> chờ **60 giây** trước khi chạy lần 3.
  * Lần 3 thất bại -> chạm ngưỡng `max_attempts`, không tự động thử lại.

## 3. Ngữ nghĩa `attempt_no` và Hành vi kết thúc

* Mỗi lần chạy là một bản ghi bất biến trong bảng `processing_jobs` với `attempt_no` tăng tuần tự (`1, 2, 3...`), liên kết qua `retry_of_job_id` và giữ nguyên `correlation_id`.
* Khi thất bại và **còn lượt thử**: bản ghi hiện tại chuyển sang `failed` (trạng thái cuối của lần thử đó) và hệ thống sinh bản ghi mới ở trạng thái `queued` với `attempt_no + 1`.
* Khi gặp **lỗi không thể thử lại** hoặc **hết lượt thử (`attempt_no >= max_attempts`)**: bản ghi chuyển sang trạng thái cuối **`dead_letter`** để kế toán/vận hành kiểm tra qua `GET /jobs/dead-letter` và kích hoạt chạy lại thủ công (`POST /jobs/{job_id}/retry`) sau khi khắc phục sự cố.
