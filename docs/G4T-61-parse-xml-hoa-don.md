# G4T-61 · ST07 · Parse XML hóa đơn (gồm G4T-46 · ST07.1 Parse XML Directly)

Người làm: Lương Quốc An · Epic: G4T-22 (Document Reading & Classification) · Dựa trên: G4T-66, G4T-67, G4T-68

Mục tiêu theo Jira: parse trực tiếp XML hóa đơn điện tử theo các chuẩn được PO xác nhận, **không đưa XML qua OCR**.
RFP liên quan: EXT 02 (mapping có phiên bản, kiểm tra schema), EXT 03 (trường header), EXT 05 (bằng chứng XML path),
EXT 06 (chuẩn hóa, thiếu là chưa biết), DAT 03 (cấu trúc trường), SEC 04 (chặn XXE), VN 01/02 (Unicode, MST, vòng đời).

Code: `backend/app/xml_parser.py` · Test: `backend/tests/test_xml_parser.py` · Mẫu: `backend/tests/fixtures/xml/`

## 1. Đối chiếu tiêu chí nghiệm thu

| Tiêu chí (Jira G4T-61) | Cách đáp ứng | Test |
|---|---|---|
| Có mẫu XML hợp lệ cho từng chuẩn được hỗ trợ | 4 mẫu giả cho biến thể `tct-hdon-v1`: đầu vào, đầu ra có namespace, hóa đơn thay thế, hóa đơn bọc trong thông điệp | `test_incoming_…`, `test_outgoing_…`, `test_replacement_…`, `test_wrapped_…` |
| Parse thành cấu trúc dữ liệu có schema rõ ràng | `XmlParseResult` / `ExtractedField` (Pydantic), mỗi trường có trạng thái | toàn bộ |
| Giữ MST và số hóa đơn dạng chuỗi, cả số 0 đầu; bảo toàn Unicode | Không bao giờ ép sang số; giữ `raw_value` nguyên văn, `normalized_value` chuẩn NFC | `test_identifiers_…`, `test_vietnamese_unicode_…`, `test_decomposed_unicode_…`, `test_utf16_…` |
| XML sai cấu trúc trả lỗi có mã và thông điệp rõ ràng | `XmlParseError.code` + `.message` (mục 6) | `test_errors_have_code_and_message`, `test_two_invoices_…` |
| Chặn DTD / external entities (XXE) | `defusedxml` với `forbid_dtd`, `forbid_entities`, `forbid_external` | 3 ca XXE trong `test_errors_…` |
| Kết quả liên kết `document_id`, `job_id`, có XML path | Mỗi kết quả mang `document_id`, `job_id`; mỗi trường có `xml_path` tuyệt đối | `test_xml_path_…`, `test_worker_flow_links_…` |

Kiểm tra thêm: thử cố ý phá 6 chỗ (cho phép DTD, bỏ số 0 đầu, dùng float, thiếu thành 0, bỏ kiểm tra trùng, mất dấu),
test đều bắt được.

## 2. Biến thể và mapping

Mỗi chuẩn XML là một `Variant` có `mapping_version` riêng (ARC 03). Kết quả luôn ghi `mapping_version` và
`processor_version` để tái lập được lần chạy (DAT 04).

**`tct-hdon-v1`**: cấu trúc XML hóa đơn điện tử của Tổng cục Thuế (phần tử `HDon` → `DLHDon` → `TTChung`, `NDHDon`).
Nhận diện: có phần tử `HDon` chứa `DLHDon/TTChung`, ở gốc hoặc nằm trong thông điệp bọc ngoài. Không phụ thuộc namespace.

| Trường | XML path (từ `HDon`) | Kiểu | Bắt buộc |
|---|---|---|---|
| `invoice_form` | `DLHDon/TTChung/KHMSHDon` | mã | |
| `invoice_series` | `DLHDon/TTChung/KHHDon` | mã | |
| `invoice_number` | `DLHDon/TTChung/SHDon` | mã | ✔ |
| `issue_date` | `DLHDon/TTChung/NLap` | ngày | ✔ |
| `currency` | `DLHDon/TTChung/DVTTe` | mã | |
| `exchange_rate` | `DLHDon/TTChung/TGia` | số thập phân | |
| `seller_name` | `DLHDon/NDHDon/NBan/Ten` | chữ | ✔ |
| `seller_tax_id` | `DLHDon/NDHDon/NBan/MST` | MST | ✔ |
| `seller_address` | `DLHDon/NDHDon/NBan/DChi` | chữ | |
| `buyer_name` | `DLHDon/NDHDon/NMua/Ten` | chữ | |
| `buyer_tax_id` | `DLHDon/NDHDon/NMua/MST` | MST | |
| `net_total` | `DLHDon/NDHDon/TToan/TgTCThue` | số thập phân | |
| `tax_total` | `DLHDon/NDHDon/TToan/TgTThue` | số thập phân | |
| `gross_total` | `DLHDon/NDHDon/TToan/TgTTTBSo` | số thập phân | ✔ |
| `gross_total_in_words` | `DLHDon/NDHDon/TToan/TgTTTBChu` | chữ | |
| `tax_breakdown[n].rate / net_amount / tax_amount` | `DLHDon/NDHDon/TToan/THTTLTSuat/LTSuat[n]/TSuat, ThTien, TThue` | mã / số | |
| `related_invoice_nature` | `DLHDon/TTChung/TTHDLQuan/TCHDon` | mã | |
| `related_invoice_form / series / number / date` | `DLHDon/TTChung/TTHDLQuan/KHMSHDCLQuan, KHHDCLQuan, SHDCLQuan, NLHDCLQuan` | mã / ngày | |
| `tax_authority_code` | `MCCQT` | mã | |
| `direction` | suy ra từ MST bên bán/bên mua và MST khách hàng | | |

Không lấy dòng hàng hóa (`DSHHDVu`): EXT 03 ghi rõ Core không trích xuất dòng hàng.

**Biến thể thứ hai**: RFP mục 2 nói pilot dùng *"two nominated invoice XML schema variants"*. Biến thể thứ hai chưa
được PO/THTax chỉ định. Khi có, chỉ cần thêm một `Variant` mới vào `VARIANTS`, kèm mẫu và test; code parse không đổi.

## 3. Trạng thái trường (`field_status`)

| Giá trị | Khi nào |
|---|---|
| `present` | Có giá trị và chuẩn hóa được |
| `missing` | Trường **bắt buộc** không có hoặc rỗng; `schema_check.passed = false` |
| `not_present` | Trường không bắt buộc không có (ví dụ bên mua nước ngoài không có MST, hóa đơn gốc không có tham chiếu thay thế) |
| `needs_review` | Có giá trị nhưng mơ hồ hoặc sai định dạng; giữ `raw_value`, `normalized_value = null` |
| `conflict` | Một trường xuất hiện nhiều lần, hoặc hướng hóa đơn không xác định; không tự chọn |

Thiếu **không bao giờ** thành 0 (EXT 06).

## 4. Quy tắc chuẩn hóa

| Kiểu | Quy tắc | Không đạt → |
|---|---|---|
| MST | Bỏ khoảng trắng; 10 số, 10 số + `-` + 3 số (chi nhánh), hoặc 12 số (số định danh cá nhân) | `needs_review` |
| Ngày | `YYYY-MM-DD` hoặc `YYYY-MM-DDThh:mm:ss` → `YYYY-MM-DD` | `needs_review` (không đoán `dd/mm` hay `mm/dd`) |
| Số tiền | Chỉ chữ số và dấu chấm thập phân; dùng `Decimal`, không dùng float | `needs_review` (dấu phẩy, dấu phân cách hàng nghìn, ký hiệu khoa học) |
| Mã (số hóa đơn, ký hiệu, tiền tệ) | Giữ nguyên chuỗi | — |
| Chữ (tên, địa chỉ) | Giữ `raw_value` nguyên văn; `normalized_value` chuẩn Unicode NFC | — |

Hướng hóa đơn (EXT 03): khách hàng là bên mua → `incoming`; là bên bán → `outgoing`; cả hai hoặc không → `conflict`.

## 5. Ví dụ kết quả (rút gọn từ `tct_hdon_incoming.xml`)

```json
{
  "document_id": "84307d9b-e88a-492d-9c27-939e1a3c8159",
  "job_id": "661969c2-c28a-449e-b103-8d0ded9ddc04",
  "processor": "xml-parser",
  "processor_version": "0.2.0",
  "mapping_version": "tct-hdon-v1",
  "outcome": "parsed",
  "schema_check": { "passed": true, "missing_required": [], "conflicts": [] },
  "fields": [
    { "field_name": "invoice_number", "raw_value": "00000045", "normalized_value": "00000045",
      "field_status": "present", "xml_path": "/HDon/DLHDon/TTChung/SHDon", "extraction_method": "xml" },
    { "field_name": "seller_tax_id", "raw_value": "0109876543", "normalized_value": "0109876543",
      "field_status": "present", "xml_path": "/HDon/DLHDon/NDHDon/NBan/MST", "extraction_method": "xml" },
    { "field_name": "tax_breakdown[2].tax_amount", "raw_value": "160000", "normalized_value": "160000",
      "field_status": "present", "xml_path": "/HDon/DLHDon/NDHDon/TToan/THTTLTSuat/LTSuat[2]/TThue",
      "extraction_method": "xml" },
    { "field_name": "related_invoice_number", "raw_value": null, "normalized_value": null,
      "field_status": "not_present", "xml_path": "/HDon/DLHDon/TTChung/TTHDLQuan/SHDCLQuan",
      "extraction_method": "xml" },
    { "field_name": "direction", "raw_value": null, "normalized_value": "incoming",
      "field_status": "present", "xml_path": null, "extraction_method": "xml" }
  ]
}
```

## 6. Mã lỗi

Đều **không thử lại** (file không đổi thì lần sau vẫn lỗi). Đã thêm vào `SAFE_ERRORS` trong `app/jobs.py`, nên worker
gọi thẳng `jobs.fail(db, job, err.code)` và job vào `dead_letter`.

| Mã | Khi nào |
|---|---|
| `xml_unsafe` | Có DTD, entity hoặc tham chiếu ngoài (XXE) |
| `xml_malformed` | Sai cú pháp XML, file rỗng, không phải XML |
| `xml_unsupported_variant` | XML hợp lệ nhưng không thuộc biến thể nào đang hỗ trợ |
| `xml_schema_invalid` | Đúng biến thể nhưng thiếu phần bắt buộc (`DLHDon`, `TTChung`, `NDHDon`, `NBan`) hoặc có hơn một hóa đơn trong một file |

Lỗi không chứa nội dung tài liệu (`test_error_does_not_leak_document_content`).
Thiếu một **trường** bắt buộc (ví dụ số hóa đơn rỗng) không phải lỗi: kết quả vẫn trả về với `schema_check.passed = false`
để người duyệt xử lý, vì các trường còn lại vẫn có ích.

## 7. Cách worker dùng (bàn giao cho Thuận, G4T-70)

```python
from app.xml_parser import XmlParseError, parse_invoice_xml

data = jobs.read_original(store, db, job)            # kiểm tra sha256, chỉ đọc
try:
    result = parse_invoice_xml(data, client_tax_id, document_id=job.document_id, job_id=job.id)
    save_result(db, result)                          # lưu kết quả: chưa có bảng, xem mục 9
    jobs.succeed(db, job, f"{result.processor} {result.processor_version}")
except XmlParseError as err:
    jobs.fail(db, job, err.code)
```

Test `test_worker_flow_links_result_to_document_and_job` chạy đúng luồng này với file upload qua API.

## 8. An toàn

- Parser: `defusedxml`, chặn DTD, entity, tham chiếu ngoài; không tải gì từ mạng.
- Lúc upload, `app/safety.py` đã cách ly XML không an toàn; parser chặn thêm một lần nữa.
- Bản gốc chỉ đọc, kiểm tra mã băm trước khi parse (G4T-66); parser không ghi gì ra đĩa.
- Mẫu test là dữ liệu giả; không đưa hóa đơn thật vào repo công khai.
- Parse đúng không có nghĩa hóa đơn hợp lệ, chữ ký đúng hay được khấu trừ (EXT 02, VN 06). Parser không kiểm tra chữ ký.

## 9. Ngoài phạm vi / cần làm tiếp

- **Bảng lưu kết quả trích xuất** (`extracted_fields` theo DAT 03): cần thống nhất với story review; hiện kết quả là
  object Pydantic, có thể lưu dạng JSON hoặc từng dòng.
- Kiểm tra theo **XSD chính thức**: cần file XSD được THTax/PO cung cấp; hiện kiểm tra cấu trúc tối thiểu và trường bắt buộc.
- So sánh số học tổng tiền (EXT 07), ghép XML với PDF cùng hóa đơn (EXT 08).
- Lấy MST khách hàng để tính hướng hóa đơn: worker lấy từ `clients.tax_id` của tài liệu.

## 10. Câu hỏi cho PO

1. Hai biến thể XML chính thức của pilot là gì? Hiện mới có `tct-hdon-v1` theo cấu trúc Tổng cục Thuế.
2. Danh sách trường bắt buộc ở mục 2 có đúng với từ điển trường G1 không?
3. Khi nào có file XML mẫu thật (đã ẩn danh, được THTax cho phép) để đối chiếu mapping trước AT 02?
