# G4T-62 – ST08 Đọc lớp chữ PDF (PDF text-layer extraction)

Căn cứ RFP: **EXT 02** "Extract digital PDF text when reliable; use OCR for scanned pages and image regions",
**EXT 05** (mỗi giá trị giữ trang hoặc XML path), **ING 04** (giữ nguyên bản gốc), **SEC 04** (không lộ nội dung).

## 1. Đã làm

| Thành phần | File |
|---|---|
| Bộ đọc lớp chữ theo trang | `backend/app/pdf_text.py` (`pdf-text-layer` 0.1.0, dùng `pypdf` đã có sẵn) |
| Gắn vào worker | `backend/app/extraction.py`: `extract_processor` rẽ nhánh `application/pdf` |
| Mã lỗi mới | `pdf_encrypted`, `pdf_unreadable` trong `SAFE_ERRORS` (không thử lại) |
| Đánh giá trên dataset | `backend/scripts/evaluate_pdf_text_layer.py` |
| Test | `backend/tests/test_pdf_text_layer.py` |

Không thêm bảng hay migration: dùng `extraction_runs`, `extracted_fields` (`extraction_method = 'pdf_text'` đã có sẵn
trong ràng buộc của schema) và `document_validations`.

## 2. Đối chiếu Acceptance Criteria

| AC | Cách đáp ứng | Test |
|---|---|---|
| Trích xuất text theo từng trang | Mỗi trang một dòng `extracted_fields` (`field_name = page_text`), `source_anchor.page_number` bắt đầu từ 1 | `test_multi_page_pdf_keeps_page_numbers`, `test_worker_saves_each_page_of_multi_page_pdf` |
| Không gọi OCR nếu có text layer | Trang có chữ đọc được thì dùng luôn, `needs_ocr = false`; chỉ trang thiếu chữ vào `ocr_pages` | `test_digital_invoice_text_is_read_per_page_without_ocr`, `test_only_pages_without_text_go_to_ocr` |
| PDF không có text layer đánh dấu cần OCR, không trả text rỗng như thành công | `extraction_runs.status = needs_ocr`, trang có `field_status = missing`, giá trị `NULL` (không phải chuỗi rỗng), `document_validations.pdf_text_layer_available = failed` | `test_scanned_pdf_is_marked_for_ocr_not_empty_success`, `test_worker_marks_scanned_pdf_for_ocr` |
| Kết quả liên kết document_id/job_id, giữ page_number | `extraction_runs` có `document_id` + `job_id`; trang nằm trong `source_anchor`; validation ghi `job_id` + `extraction_run_id` | `test_worker_saves_digital_pdf_text_by_page` |
| File lỗi trả lỗi truy vết được; file gốc không đổi | Lỗi trả mã cố định + `extraction_runs` trạng thái `failed` có `error_code`; bộ đọc chỉ đọc bytes trong bộ nhớ, đọc lại bản gốc vẫn khớp SHA-256 | `test_unreadable_pdfs_return_fixed_codes`, `test_unreadable_pdf_fails_with_traceable_run` |

## 3. Quy tắc "trang có chữ"

- Chuẩn hóa Unicode NFC và gộp khoảng trắng thừa; giữ nguyên dấu tiếng Việt và số 0 đầu. Bản gốc pypdf trả về
  được lưu ở `raw_value`, bản chuẩn hóa ở `normalized_value`.
- Trang có ít hơn **20** ký tự không phải khoảng trắng → `no_text_layer` (PDF scan đôi khi chỉ có số trang).
- Trang có hơn **5%** ký tự thay thế U+FFFD → `unreadable_text` (font không ánh xạ được Unicode) → cần OCR.
- `outcome` = `parsed` khi mọi trang có chữ; `needs_ocr` khi có ít nhất một trang phải OCR (hợp đồng G4T-68 mục 7).

## 4. Kết quả trên dataset chính thức G4T-42

Nhãn so sánh không do người viết bộ đọc tự đặt: định tuyến lấy từ `mixed_pack/manifest.json` (`PDF_TEXT` /
`PDF_SCAN`, áp cho file trùng SHA-256 trong `pdf/`), số trang lấy từ `total_pages`, giá trị lấy từ `fields`
của `ground_truth.json`.

| Chỉ số | Kết quả |
|---|---|
| Định tuyến chữ / OCR đúng | 5/5 |
| Số trang đúng | 1/1 (chỉ `mixed_documents_multi_page.pdf` có `total_pages`) |
| Giá trị ground truth tìm thấy trong chữ đọc được | 16/16 |

`mixed_documents_multi_page.pdf` không có nhãn `PDF_TEXT`/`PDF_SCAN` nên không tính vào định tuyến.
Đây là kiểm tra **đọc chữ**, chưa phải trích xuất trường hóa đơn từ PDF; không dùng làm KPI độ chính xác trường.

Chạy lại:

```bash
cd backend
python -m scripts.evaluate_pdf_text_layer
pytest -q tests/test_pdf_text_layer.py
```

## 5. Ngoài phạm vi / cần chốt

1. **Trạng thái job khi `needs_ocr`.** Hiện job vẫn `SUCCEEDED` (bước đọc lớp chữ đã chạy xong đúng), kết quả ghi
   `needs_ocr`. Cần thống nhất với Tâm (G4T-64) cách hiển thị để không hiểu nhầm là "đã xử lý xong", và với
   G4T-23 (OCR) cách nhận các trang trong `ocr_pages`.
2. **Trích xuất trường hóa đơn từ chữ PDF** (số, ký hiệu, MST, tiền): chưa làm trong G4T-62; cần story riêng.
3. **API đọc kết quả theo trang** cho giao diện: chưa có; có thể bổ sung khi G4T-64 cần.
