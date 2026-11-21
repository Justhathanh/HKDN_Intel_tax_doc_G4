# G4T-73 – Chính sách Retry, Backoff và Dead Letter Queue (ST06)

Tài liệu này quy định chi tiết tham số thử lại và vận hành hàng đợi lỗi cho hệ thống xử lý nền, kế thừa bảng chuyển trạng thái tại [`docs/G4T-67-state-machine-job.md`](G4T-67-state-machine-job.md) và hợp đồng API tại [`docs/G4T-68-hop-dong-api-xu-ly.md`](G4T-68-hop-dong-api-xu-ly.md).

## 1. Phân loại lỗi (Transient vs Permanent)

Hệ thống chỉ lưu các mã lỗi chuẩn hóa trong `SAFE_ERRORS` (`backend/app/jobs.py`), tuyệt đối không lưu stack trace hoặc nội dung trích xuất từ tài liệu kế toán (SEC 04). Chi tiết ý nghĩa từng mã lỗi và thông báo chuẩn tham chiếu mục mã lỗi trong [`docs/G4T-68-hop-dong-api-xu-ly.md`](G4T-68-hop-dong-api-xu-ly.md).

* **Lỗi tạm thời – Có thể thử lại (`error_retryable = true`):** `ocr_timeout`, `ocr_unavailable`, `quota_exceeded`, `lease_expired` (`DEFAULT_LEASE = 10 phút`), `internal_error`.
* **Lỗi vĩnh viễn – Không thử lại (`error_retryable = false`):** `original_missing`, `original_tampered` (vi phạm toàn vẹn ING 04), `unsupported_document`, `parser_error`.

## 2. Giới hạn số lần thử & Chiến lược Backoff

* **Số lần thử tối đa mặc định (`DEFAULT_MAX_ATTEMPTS`):** `3` lần (`attempt_no` từ `1` đến `3`).
* **Công thức chờ tăng dần (Exponential Backoff):**
  `delay(attempt_no) = min(30s * 2^(attempt_no - 1), 15 phút)`
  * Lần 1 thất bại -> chờ **30 giây** trước khi chạy lần 2.
  * Lần 2 thất bại -> chờ **60 giây** trước khi chạy lần 3.
  * Lần 3 thất bại -> chạm ngưỡng `max_attempts`, không tự động thử lại.

## 3. Ngữ nghĩa `attempt_no`, Dead Letter Queue và Phân quyền

* Mỗi lần chạy là một bản ghi bất biến trong bảng `processing_jobs` với `attempt_no` tăng tuần tự (`1, 2, 3...`), liên kết qua `retry_of_job_id` và giữ nguyên `correlation_id`.
* Khi thất bại và **còn lượt thử**: bản ghi hiện tại chuyển sang `failed` (trạng thái cuối của lần thử đó) và hệ thống sinh bản ghi mới ở trạng thái `queued` với `attempt_no + 1`.
* Khi gặp **lỗi không thể thử lại** hoặc **hết lượt thử (`attempt_no >= max_attempts`)**: bản ghi chuyển sang trạng thái cuối **`dead_letter`** (xem lý do kiến trúc và ràng buộc chuyển trạng thái tại [`docs/G4T-67-state-machine-job.md`](G4T-67-state-machine-job.md) – RFP ARC 02) để vận hành kiểm tra qua `GET /jobs/dead-letter` và kích hoạt chạy lại thủ công (`POST /jobs/{job_id}/retry`).
* **Ghi chú bảo mật (TODO – SEC 01):** Hiện tại `POST /jobs/{job_id}/retry` kiểm tra phạm vi khách hàng (`client_ids`). Cần bổ sung kiểm tra phân quyền theo vai trò (chỉ `accountant_lead` / `admin` được phép kích hoạt retry thủ công) theo mục 9 của [`docs/G4T-68-hop-dong-api-xu-ly.md`](G4T-68-hop-dong-api-xu-ly.md) khi hoàn thiện RBAC.
