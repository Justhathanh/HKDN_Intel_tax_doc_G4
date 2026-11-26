# G4T-61 · ST07 · Parse XML hóa đơn (gồm G4T-46 · ST07.1 Parse XML Directly)

Người làm: Lương Quốc An · Epic: G4T-22 (Document Reading & Classification) · Dựa trên: G4T-66, G4T-67, G4T-68

Mục tiêu theo Jira: parse trực tiếp XML hóa đơn điện tử theo các chuẩn được PO xác nhận, **không đưa XML qua OCR**.
RFP liên quan: EXT 02 (mapping có phiên bản, kiểm tra schema), EXT 03 (trường header), EXT 05 (bằng chứng XML path),
EXT 06 (chuẩn hóa, thiếu là chưa biết), DAT 03 (cấu trúc trường), SEC 04 (chặn XXE), VN 01/02 (Unicode, MST, vòng đời).

Code: `backend/app/xml_parser.py`, `backend/app/extraction.py` (bộ xử lý của worker), `backend/scripts/evaluate_xml_dataset.py`
Test: `backend/tests/test_xml_parser.py` (an toàn, mã lỗi), `backend/tests/test_xml_golden.py` (dataset chính thức, worker)

> **Trạng thái (22/11):** đã code và đã test trên dataset chính thức G4T-42 (PR #15, đã merge); PR #13 chờ review.
> Chưa merge vào `main`. Trên `main` hiện vẫn là parser cũ `tt-generic-v0` (chưa đối chiếu file thật, không có worker
> gọi tới); khi PR #13 merge, `tct-hdon-v1` thay thế hoàn toàn bản cũ.
> Cách ghi trạng thái theo góp ý của trưởng nhóm: **coded → tested → reviewed → merged → accepted**. G4T-61 đang ở **tested**.

## 1. Đối chiếu tiêu chí nghiệm thu

| Tiêu chí (Jira G4T-61) | Tình trạng | Bằng chứng |
|---|---|---|
| Có mẫu XML hợp lệ cho từng chuẩn được hỗ trợ | ✔ tested | 7 mẫu `tct-hdon-v1` trong dataset G4T-42 (`tests/fixtures/xml`, Khiêm tạo, ghi rõ dữ liệu giả lập) |
| Parse thành cấu trúc dữ liệu có schema rõ ràng | ✔ tested | `XmlParseResult` / `ExtractedField`; lưu vào `extraction_runs`, `extracted_fields` (PR #18) |
| Giữ MST và số hóa đơn dạng chuỗi, cả số 0 đầu; bảo toàn Unicode | ✔ tested | `test_every_ground_truth_field_matches`: 143/143 trường khớp ground truth |
| XML sai cấu trúc trả lỗi có mã và thông điệp rõ ràng | ✔ tested | `test_malformed_sample_returns_expected_code`, `test_errors_have_code_and_message` |
| Chặn DTD / external entities (XXE) | ✔ tested | 3 chuỗi tấn công trong `test_errors_have_code_and_message` |
| Kết quả liên kết `document_id`, `job_id`, có XML path | ✔ tested | `test_worker_saves_field_and_document_results`: qua worker thật, `extraction_runs.job_id`, `source_anchor.xml_path` |

## 1a. Kết quả trên dataset chính thức (hai lớp đánh giá riêng)

Theo góp ý P0 của trưởng nhóm, kết quả **không gộp thành một điểm**:
- **Lớp trường:** số trường khớp ground truth / tổng số trường.
- **Lớp tài liệu:** tài liệu chỉ đúng khi mọi trường khớp, hướng hóa đơn đúng, kết quả kiểm tra schema đúng và không có
  quy tắc mức tài liệu nào báo lỗi (mục 7a). Một tài liệu có thể đúng từng trường mà vẫn sai ở mức tài liệu
  (`test_fields_all_valid_but_document_wrong`), và ngược lại một trường sai không che các kết luận mức tài liệu
  (`test_field_wrong_does_not_hide_document_findings`).

Chạy lại: `cd backend && python -m scripts.evaluate_xml_dataset` (thêm `--json` để lấy số liệu máy đọc).
Test `test_two_level_report_on_official_dataset` khóa các con số này.

Dataset `3.1.0` · parser `0.3.0` · mapping `tct-hdon-v1`

| Lớp | Đúng | Tổng |
|---|---|---|
| Trường (field accuracy) | 143 | 143 |
| Tài liệu (document correctness) | 7 | 7 |
| Tệp lỗi trả đúng mã | 1 | 1 |

| Tệp | Trường đúng | Hướng | Schema | Quy tắc tài liệu lỗi | Tài liệu đúng |
|---|---|---|---|---|---|
| `tct_hdon_01_vat10_standard.xml` | 21/21 | ✔ | ✔ | — | ✔ |
| `tct_hdon_02_vat8_multi_rate.xml` | 24/24 | ✔ | ✔ | — | ✔ |
| `tct_hdon_03_vat0_export_foreign.xml` | 20/20 | ✔ | ✔ | — | ✔ |
| `tct_hdon_04_outgoing_branch.xml` | 21/21 | ✔ | ✔ | — | ✔ |
| `tct_hdon_05_replacement.xml` | 26/26 | ✔ | ✔ | — | ✔ |
| `tct_hdon_06_wrapped_transmission.xml` | 21/21 | ✔ | ✔ | — | ✔ |
| `tct_hdon_07_missing_optional.xml` | 10/10 | ✔ | ✔ | — | ✔ |
| `malformed_invoice.xml` | lỗi kỳ vọng `xml_malformed`, nhận `xml_malformed` | | | | ✔ |

**Phạm vi của con số:** 7 hóa đơn XML tổng hợp (1 biến thể) chỉ là **golden test** để chống lỗi lùi, **không phải KPI
nghiệm thu**. RFP AT 02 yêu cầu ≥ 300 XML (≥ 100 mỗi biến thể, ≥ 50 mỗi hướng) và độ chính xác trường quan trọng
≥ 99,5%; ngưỡng và tập benchmark cần PO chốt trước khi báo KPI.

**Cách tái lập** (mọi con số trong tài liệu và PR đều chạy bằng các lệnh này, trên commit ghi kèm ở PR #13):
`cd backend && python -m scripts.evaluate_xml_dataset` (báo cáo hai lớp) và
`TEST_DATABASE_URL=postgresql+psycopg://…/<db> pytest -q` (PostgreSQL 16; bỏ biến này thì chạy SQLite).

XML là định dạng có cấu trúc, đọc theo quy tắc cố định nên **không có điểm tin cậy** kiểu mô hình: cột `confidence`
để trống (DAT 03 ghi "confidence if available"). Điểm tin cậy sẽ có ở OCR (G4T-23).

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
| `buyer_address` | `DLHDon/NDHDon/NMua/DChi` | chữ | |
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

## 5. Cấu trúc kết quả

```text
XmlParseResult
  document_id, job_id            liên kết tài liệu và lần thử (G4T-68)
  processor, processor_version   "xml-parser", phiên bản code
  mapping_version                ví dụ "tct-hdon-v1"
  outcome                        "parsed"
  schema_check                   passed, missing_required[], conflicts[]
  fields[]                       ExtractedField
    field_name                   tên trường ở mục 2
    raw_value                    chuỗi gốc trong XML (null nếu không có)
    normalized_value             giá trị chuẩn hóa (null nếu không có hoặc cần xem lại)
    field_status                 present | missing | not_present | needs_review | conflict
    xml_path                     đường dẫn tuyệt đối, ví dụ /HDon/DLHDon/TTChung/SHDon
    extraction_method            "xml"
```

Ví dụ có giá trị sẽ lấy từ dataset G4T-42, không tự tạo.

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

## 7. Nối với worker (`app/extraction.py`)

Bộ xử lý mặc định của worker (`worker.default_processor`, G4T-70 của Thuận) gọi `extraction.extract_processor`.
Trước đây bộ xử lý mặc định chỉ đọc bản gốc rồi báo SUCCEEDED (nhận xét P0 "worker báo thành công giả"). Nay:

| Đầu vào | Kết quả job | Dữ liệu lưu |
|---|---|---|
| XML hóa đơn `tct-hdon-v1` | `succeeded`, `processor_version = "xml-parser 0.3.0"` | 1 `extraction_runs` (status succeeded, `job_id`), mỗi trường 1 `extracted_fields` (`field_status`, `extraction_method = xml`, `source_anchor.xml_path`), các quy tắc mức tài liệu trong `document_validations` |
| XML không parse được | `dead_letter`, mã `xml_*`, không thử lại | 1 `extraction_runs` status failed kèm `error_code` để truy vết |
| PDF, ảnh (chưa có bộ xử lý) | `dead_letter`, mã `unsupported_document` | không có kết quả; **không báo thành công giả**. Khi có G4T-62 và OCR sẽ có bộ xử lý riêng |

Kết quả và trạng thái job được ghi trong **cùng một transaction** với worker (`object_session(job)`): không thể có
job SUCCEEDED mà thiếu kết quả. MST dùng để xác định hướng hóa đơn lấy từ pháp nhân (`tax_entities`) của tài liệu,
không có thì lấy MST khách hàng.

### 7a. Quy tắc mức tài liệu (`document_validations`, `validation_scope = whole_document`)

| `rule_code` | Kiểm tra | `skipped` khi |
|---|---|---|
| `required_fields_present` | Không thiếu trường bắt buộc | — |
| `no_field_conflicts` | Không có trường xuất hiện nhiều lần | — |
| `totals_consistent` | Tiền trước thuế + tiền thuế = tổng thanh toán (Decimal, EXT 07) | thiếu một trong ba giá trị (không suy ra giá trị thiếu, EXT 06) |
| `tax_breakdown_consistent` | Tổng thuế theo từng thuế suất = tổng tiền thuế | không có bảng thuế suất |
| `related_invoice_date_not_after_issue` | Hóa đơn thay thế/điều chỉnh: ngày của hóa đơn gốc được tham chiếu không sau ngày lập | không có tham chiếu hóa đơn liên quan |
| `direction_determined` | Xác định được hóa đơn đầu vào hay đầu ra | — |

**Chưa làm (cần nhóm chốt):** worker chưa chuyển trạng thái *tài liệu* (`received → processing → needs_review`,
G4T-67 mục 6), nên tài liệu vẫn ở `received` sau khi job xong.

## 8. An toàn

- Parser: `defusedxml`, chặn DTD, entity, tham chiếu ngoài; không tải gì từ mạng.
- Lúc upload, `app/safety.py` đã cách ly XML không an toàn; parser chặn thêm một lần nữa.
- Bản gốc chỉ đọc, kiểm tra mã băm trước khi parse (G4T-66); parser không ghi gì ra đĩa.
- Không có hóa đơn mẫu tự tạo trong repo; không đưa hóa đơn thật của khách hàng vào repo công khai.
- Parse đúng không có nghĩa hóa đơn hợp lệ, chữ ký đúng hay được khấu trừ (EXT 02, VN 06). Parser không kiểm tra chữ ký.

## 9. Ngoài phạm vi / cần làm tiếp

- Kiểm tra theo **XSD chính thức**: cần file XSD được THTax/PO cung cấp; hiện kiểm tra cấu trúc tối thiểu và trường bắt buộc.
- Ghép XML với PDF của cùng hóa đơn (EXT 08); chính sách làm tròn khi so tổng tiền có ngoại tệ (EXT 07).

## 10. Câu hỏi cho PO

1. Hai biến thể XML chính thức của pilot là gì? Hiện mới có `tct-hdon-v1` theo cấu trúc Tổng cục Thuế.
2. Danh sách trường bắt buộc ở mục 2 có đúng với từ điển trường G1 không?
3. Khi nào có file XML mẫu thật (đã ẩn danh, được THTax cho phép) để đối chiếu mapping trước AT 02?
