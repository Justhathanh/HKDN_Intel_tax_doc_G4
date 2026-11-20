# Bộ Dữ Liệu Thuế Mẫu Tổng Hợp (Synthetic Tax Test Dataset) · G4T-42

Phụ trách: **Nguyễn Thanh Khiêm (Dev – Automated Testing / QA)**  
Phối hợp: **Lương Quốc An (Hỗ trợ Schema), Đào Đoàn Tường Vy (Hỗ trợ Mẫu OCR), Nguyễn Mạnh Hùng (PO xác nhận loại tài liệu)**  
Tiêu chuẩn căn cứ: **Nghị định 123/2020/NĐ-CP, Thông tư 78/2021/TT-BTC, Quyết định 1450/QĐ-TCT**

---

## 1. Mục đích và Quy tắc An toàn dữ liệu

1. **Dữ liệu giả lập 100% (Synthetic)**: Mọi tên công ty, mã số thuế (MST), địa chỉ, số hóa đơn trong bộ dữ liệu này đều là giả định, chỉ phục vụ kiểm thử tự động (Unit Test, Integration Test, Regression Test).
2. **Bảo mật tuyệt đối**: Không sử dụng chứng từ thật hoặc dữ liệu cá nhân/khách hàng thật trên kho mã nguồn Git.
3. **Độ bao phủ đa dạng (Acceptance Criteria G4T-42)**: Bao phủ đủ 4 nhóm:
   - XML hóa đơn điện tử (chuẩn PO xác nhận).
   - PDF kỹ thuật số có Text Layer.
   - Ảnh scan hóa đơn (JPG/PNG rõ nét và mờ/khó đọc).
   - Tài liệu Non-Tax (Hợp đồng nguyên tắc thông thường) phục vụ bài toán Phân loại tài liệu (`G4T-24`).
   - Mẫu lỗi cú pháp (`malformed`) phục vụ kiểm thử bắt lỗi hệ thống.

---

## 2. Danh mục chi tiết các tệp mẫu trong Dataset

### 📂 A. Nhóm XML Hóa đơn điện tử (`fixtures/xml/`)

| Tệp XML | Biến thể | Expected Document Type | Hướng | Đặc tính kỹ thuật kiểm thử |
|---|---|---|---|---|
| `tct_hdon_01_vat10_standard.xml` | `tct-hdon-v1` | `INVOICE_VAT` | incoming | VAT 10% chuẩn, số HĐ có số 0 đầu (`00000001`), MST 10 số, mã CQT 34 ký tự (`MCCQT`), khối chữ ký điện tử (`DSCKS`). |
| `tct_hdon_02_vat8_multi_rate.xml` | `tct-hdon-v1` | `INVOICE_VAT` | incoming | Đa thuế suất 10% và 8% (NĐ 15/2022/NĐ-CP), có bảng tổng hợp thuế suất `THTTLTSuat/LTSuat`. |
| `tct_hdon_03_vat0_export_foreign.xml` | `tct-hdon-v1` | `INVOICE_VAT` | outgoing | Xuất khẩu VAT 0%, ngoại tệ USD, tỷ giá thập phân `TGia` (`25350.5`), người mua nước ngoài. |
| `tct_hdon_04_outgoing_branch.xml` | `tct-hdon-v1` | `INVOICE_VAT` | outgoing | Có XML Namespace (`xmlns:inv`), MST chi nhánh 14 ký tự (`0312345678-001`), ngày lập `xs:dateTime`. |
| `tct_hdon_05_replacement.xml` | `tct-hdon-v1` | `INVOICE_VAT` | incoming | Hóa đơn thay thế, có thông tin hóa đơn bị thay thế (`TTHDLQuan`). |
| `tct_hdon_06_wrapped_transmission.xml` | `tct-hdon-v1` | `INVOICE_VAT` | incoming | Hóa đơn lồng trong gói thông điệp truyền nhận ngành thuế (`TDiep/DLieu/HDon`). |
| `tct_hdon_07_missing_optional.xml` | `tct-hdon-v1` | `INVOICE_VAT` | incoming | Hóa đơn tối giản thiếu các trường không bắt buộc (không địa chỉ, không mã CQT). |
| `malformed_invoice.xml` | N/A | `CORRUPT_XML` | N/A | XML lỗi cú pháp (thiếu thẻ đóng) để test lỗi `xml_malformed`. |

### 📂 B. Nhóm PDF Kỹ thuật số (`fixtures/pdf/`)

| Tệp PDF | Expected Document Type | Mục đích phục vụ | Đặc tính kỹ thuật |
|---|---|---|---|
| `invoice_digital_text_layer.pdf` | `INVOICE_VAT` | Phục vụ `G4T-62 ST08 - PDF Text-layer Extraction` (Quốc An) | PDF hóa đơn điện tử chuẩn A4, chứa luồng văn bản (text stream) trích xuất được trực tiếp không cần OCR. |
| `non_tax_contract.pdf` | `NON_TAX_CONTRACT` | Phục vụ `G4T-24 ST11 - Document Classification` (Tường Vy) | Hợp đồng nguyên tắc cung cấp dịch vụ (văn bản không phải hóa đơn thuế) để kiểm thử model phân loại tài liệu. |

### 📂 C. Nhóm Hình ảnh Scan (`fixtures/images/`)

| Tệp Ảnh | Expected Document Type | Mục đích phục vụ | Đặc tính kỹ thuật |
|---|---|---|---|
| `invoice_scan_clean.png` | `INVOICE_VAT` | Phục vụ `G4T-23 ST10 - OCR Scanned Documents` (Tường Vy) | Ảnh scan hóa đơn rõ nét, tương phản cao, kích thước chuẩn 800x1100. |
| `invoice_scan_blurred.png` | `INVOICE_VAT` | Phục vụ `G4T-23 ST10 - OCR Scanned Documents` (Tường Vy) | Ảnh scan bị làm mờ (Gaussian Blur) để test độ bền bỉ của OCR đối với tài liệu scan chất lượng thấp / khó đọc. |

---

## 3. Bảng chân lý Ground Truth (`ground_truth.json`)

Tệp `ground_truth.json` đóng vai trò là **Test Oracle** để đánh giá:
- **KPI 1 - Field Accuracy**: So sánh từng trường trích xuất với giá trị kỳ vọng.
- **KPI 2 - Whole-Document Correctness**: Kiểm tra tính toán số học `gross_total = net_total + tax_total`.
- **Expected Document Type**: Hỗ trợ phân loại tài liệu (`INVOICE_VAT`, `NON_TAX_CONTRACT`, `CORRUPT_XML`).

---

## 4. Cách chạy kiểm thử

```powershell
cd backend
.venv\Scripts\activate
pytest tests/test_synthetic_dataset.py -v
```
