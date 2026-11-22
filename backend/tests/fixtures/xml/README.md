# Bộ Dữ Liệu Thuế Mẫu Tổng Hợp (Synthetic Tax Test Dataset) · G4T-42

Phụ trách: **Nguyễn Thanh Khiêm (Dev – Automated Testing / QA)**  
Phối hợp: **Lương Quốc An (Backend & Schema), Đào Đoàn Tường Vy (OCR & Phân loại tài liệu), Huỳnh Hà Thanh (PO), Nguyễn Mạnh Hùng (Mentor / PO Chốt chuẩn)**  
Căn cứ pháp lý & kỹ thuật: **RFP 2026 – Nghị định 254/2026/NĐ-CP & Thông tư 91/2026/TT-BTC (Kế thừa cấu trúc kỹ thuật XML `tct-hdon-v1` của Tổng cục Thuế)**

> **Xác nhận chuẩn:** Toàn bộ dữ liệu XML, PDF, Hình ảnh và Gói hỗn hợp trong dataset này đã được đối soát và chốt chuẩn theo khung RFP 2026 (Nghị định 254/2026/NĐ-CP và Thông tư 91/2026/TT-BTC) cùng Mentor anh Hùng và PO Huỳnh Hà Thanh.

---

## 1. Mục đích và Nguyên tắc An toàn dữ liệu

1. **Dữ liệu giả lập 100% độc lập (Synthetic & Independent)**: Mọi tên công ty, mã số thuế (MST), địa chỉ, số hóa đơn trong bộ dữ liệu đều được sinh độc lập, không trùng lặp với code mẫu phát triển của Developer, phục vụ kiểm thử khách quan (Unit Test, Integration Test, Regression Test).
2. **Bảo mật tuyệt đối**: Không sử dụng chứng từ thật hoặc dữ liệu cá nhân/khách hàng thật trên kho mã nguồn Git công khai.
3. **Độ bao phủ đầy đủ theo Acceptance Criteria G4T-42**:
   - XML hóa đơn điện tử chuẩn TCT.
   - PDF điện tử có Text Layer trực tiếp (không qua OCR).
   - PDF scan thuần túy (không có Text Layer) phục vụ G4T-62 phân biệt luồng PDF.
   - Hình ảnh hóa đơn định dạng JPG và PNG (ảnh rõ nét và ảnh mờ/nhiễu).
   - Tài liệu phi thuế / Non-tax (Hợp đồng dịch vụ thương mại).
   - Mẫu Thông báo thuế và Giấy nộp tiền vào NSNN.
   - Gói tài liệu hỗn hợp đa định dạng (Mixed Pack).
   - Mẫu lỗi cú pháp XML (`malformed_invoice.xml`).
4. **Chuẩn hóa nhãn phân loại tài liệu theo G4T-24 (ST11)**:
   - `INVOICE`: Hóa đơn điện tử (XML, PDF, JPG, PNG).
   - `TAX_NOTICE`: Thông báo của Cơ quan thuế.
   - `TAX_PAYMENT_RECEIPT`: Giấy nộp tiền vào Ngân sách Nhà nước.
   - `UNKNOWN`: Tài liệu phi thuế / không xác định loại thuế (Hợp đồng kinh tế).
   - `MIXED`: Gói nộp hồ sơ hỗn hợp nhiều định dạng và loại chứng từ.

---

## 2. Danh mục chi tiết các tệp mẫu trong Dataset

### 📁 A. Nhóm XML Hóa đơn điện tử (`fixtures/xml/`)

| Tệp XML | Biến thể | Label (G4T-24) | Đặc tính kỹ thuật kiểm thử |
|---|---|---|---|
| `tct_hdon_01_vat10_standard.xml` | `tct-hdon-v1` | `INVOICE` | Hóa đơn GTGT 10% chuẩn, số HĐ có số 0 đầu (`0000045`), MST 10 số, mã CQT 31 ký tự. |
| `tct_hdon_02_vat8_multi_rate.xml` | `tct-hdon-v1` | `INVOICE` | Đa thuế suất 10% và 8%, bảng tổng hợp thuế suất `THTTLTSuat/LTSuat`, MST TP.HCM. |
| `tct_hdon_03_vat0_export_foreign.xml` | `tct-hdon-v1` | `INVOICE` | Xuất khẩu VAT 0%, ngoại tệ USD, tỷ giá thập phân `TGia` (`25450.00`), người mua nước ngoài (không có MST VN). |
| `tct_hdon_04_outgoing_branch.xml` | `tct-hdon-v1` | `INVOICE` | Chi nhánh phụ thuộc phát hành (MST 10-3: `0105667788-002`), ngày lập chuẩn ISO. |
| `tct_hdon_05_replacement.xml` | `tct-hdon-v1` | `INVOICE` | Hóa đơn thay thế, có thẻ thông tin hóa đơn bị thay thế `TTHDLQuan` (`TCHDon=1`). |
| `tct_hdon_06_wrapped_transmission.xml` | `tct-hdon-v1` | `INVOICE` | Hóa đơn lồng trong gói thông điệp truyền nhận ngành thuế (`TDiep/DLieu/HDon`), thuế 5%. |
| `tct_hdon_07_missing_optional.xml` | `tct-hdon-v1` | `INVOICE` | Hóa đơn tối giản thiếu các trường tùy chọn (không địa chỉ, không mã CQT, không tiền bằng chữ). |
| `malformed_invoice.xml` | N/A | `INVOICE` | XML lỗi cú pháp (thiếu thẻ đóng) để kiểm thử bắt lỗi `xml_malformed`. |

### 📁 B. Nhóm PDF Chuẩn hóa bằng ReportLab (`fixtures/pdf/`)

| Tệp PDF | Label (G4T-24) | Mục đích phục vụ | Đặc tính kỹ thuật |
|---|---|---|---|
| `invoice_digital_text_layer.pdf` | `INVOICE` | Phục vụ `G4T-62 ST08 - PDF Text-layer Extraction` (Quốc An) | PDF sinh bằng ReportLab có font tiếng Việt (Arial), cấu trúc chuẩn 100% compliant (không lỗi Poppler), chứa luồng text trực tiếp. |
| `invoice_scanned_no_text.pdf` | `INVOICE` | Phục vụ `G4T-62` (kiểm tra phân biệt PDF scan) & `G4T-23` (OCR) | PDF chỉ chứa ảnh raster, tuyệt đối không có text layer (`extract_text() == ""`). |
| `non_tax_contract.pdf` | `UNKNOWN` | Phục vụ `G4T-24 ST11 - Document Classification` (Tường Vy) | Hợp đồng kinh tế dịch vụ tư vấn doanh nghiệp (tài liệu phi thuế). |
| `tax_notice_cqt.pdf` | `TAX_NOTICE` | Phục vụ `G4T-24 ST11 - Document Classification` (Tường Vy) | Thông báo nộp tiền thuế và các khoản thu NSNN của Chi cục Thuế Quận Cầu Giấy. |
| `tax_payment_receipt_nsnn.pdf` | `TAX_PAYMENT_RECEIPT` | Phục vụ `G4T-24 ST11 - Document Classification` (Tường Vy) | Giấy nộp tiền vào Ngân sách Nhà nước theo Mẫu C1-02/NS qua KBNN và Vietcombank. |

### 📁 C. Nhóm Hình ảnh Scan PNG & JPG (`fixtures/images/`)

| Tệp Ảnh | Label (G4T-24) | Mục đích phục vụ | Đặc tính kỹ thuật |
|---|---|---|---|
| `invoice_scan_clean.png` | `INVOICE` | Phục vụ `G4T-23 ST10 - OCR Scanned Documents` (Tường Vy) | Ảnh PNG scan hóa đơn rõ nét, độ tương phản cao, kích thước 900x1200. |
| `invoice_scan_blurred.png` | `INVOICE` | Phục vụ `G4T-23 ST10 - OCR Scanned Documents` (Tường Vy) | Ảnh PNG scan bị làm mờ (Gaussian Blur) để test độ bền của OCR đối với tài liệu scan chất lượng thấp. |
| `invoice_vat10_retail.jpg` | `INVOICE` | Phục vụ AC G4T-42 (bổ sung ảnh JPG) | Ảnh JPG hóa đơn giá trị gia tăng rõ nét. |

### 📁 D. Gói hồ sơ hỗn hợp Mixed Pack (`fixtures/mixed_pack/`)

| Tệp / Thư mục | Label (G4T-24) | Mục đích phục vụ | Đặc tính kỹ thuật |
|---|---|---|---|
| `manifest.json` | `MIXED` | Phục vụ kiểm thử xử lý hàng đợi G4T-71 & phân loại G4T-24 | File manifest mô tả danh mục 7 tài liệu đa định dạng (XML, PDF text, PDF scan, JPG, Hợp đồng, Thông báo thuế, Giấy nộp tiền). |
| `01_invoice_vat10.xml` $\rightarrow$ `07_tax_payment.pdf` | Từng loại | Thư mục trọn vẹn mô phỏng 1 đợt nộp hồ sơ gồm nhiều loại tài liệu hỗn hợp. |

---

## 3. Bảng chân lý Ground Truth (`ground_truth.json`)

Tệp `ground_truth.json` (phiên bản 3.0.0) đóng vai trò là **Test Oracle** chuẩn mực của dự án:
- **KPI 1 - Field Accuracy**: Đối chiếu từng trường dữ liệu trích xuất (MST, số hóa đơn, ngày lập, tiền, thuế) với giá trị ground truth.
- **KPI 2 - Whole-Document Correctness**: Kiểm tra tính toán số học chuẩn xác từng đồng bằng kiểu `Decimal` (`gross_total = net_total + tax_total`).
- **Standardized Classification (G4T-24)**: Toàn bộ mẫu đều có nhãn phân loại chuẩn (`INVOICE`, `TAX_NOTICE`, `TAX_PAYMENT_RECEIPT`, `UNKNOWN`, `MIXED`).

---

## 4. Cách chạy kiểm thử tự động

```powershell
cd backend
.\.venv\Scripts\activate
pytest tests/test_synthetic_dataset.py -v
```
