# Bộ Dữ Liệu Thuế Mẫu Tổng Hợp (Synthetic Tax Test Dataset) · G4T-42

Phụ trách: **Nguyễn Thanh Khiêm (Dev – Automated Testing / QA)**  
Liên quan: **G4T-61 / G4T-46 (XML Parsing), G4T-39 (Worker), ST05.7, ST06.5**  
Tiêu chuẩn căn cứ: **Nghị định 123/2020/NĐ-CP, Thông tư 78/2021/TT-BTC, Chuẩn dữ liệu XML Hóa đơn điện tử của Tổng cục Thuế (Quyết định 1450/QĐ-TCT)**

---

## 1. Mục đích và Quy tắc An toàn dữ liệu

1. **Dữ liệu giả lập 100% (Synthetic)**: Mọi tên doanh nghiệp, mã số thuế (MST), địa chỉ, số hóa đơn trong bộ dữ liệu này đều là giả định, chỉ phục vụ môi trường kiểm thử tự động (Unit Test, Integration Test, Regression Test).
2. **Không rò rỉ dữ liệu thật**: Nghiêm cấm đưa hóa đơn thực tế của doanh nghiệp hoặc khách hàng lên kho mã nguồn (Git công khai).
3. **Bảo toàn tính chất kỹ thuật**: Mặc dù dữ liệu giả, toàn bộ cấu trúc XML, quy tắc định dạng số, ngày tháng, Unicode tiếng Việt và các quan hệ kinh tế đều tuân thủ chặt chẽ nghiệp vụ hóa đơn điện tử Việt Nam.

---

## 2. Danh mục các tệp mẫu trong Dataset

| Tệp XML | Biến thể | Loại nghiệp vụ | Đặc tính kỹ thuật kiểm thử |
|---|---|---|---|
| `tct_hdon_01_vat10_standard.xml` | `tct-hdon-v1` | Mua vào (Incoming) | VAT 10% chuẩn, số hóa đơn có số 0 ở đầu (`00000001`), MST 10 số, mã CQT 34 ký tự (`MCCQT`), khối chữ ký điện tử (`DSCKS`). |
| `tct_hdon_02_vat8_multi_rate.xml` | `tct-hdon-v1` | Mua vào (Incoming) | Đa thuế suất 10% và 8% (giảm thuế theo NĐ 15/2022/NĐ-CP), có bảng tổng hợp thuế suất `THTTLTSuat/LTSuat`. |
| `tct_hdon_03_vat0_export_foreign.xml` | `tct-hdon-v1` | Bán ra (Outgoing) | Dịch vụ xuất khẩu VAT 0%, đồng tiền ngoại tệ USD, tỷ giá thập phân `TGia` (`25350.5`), người mua nước ngoài không có MST. |
| `tct_hdon_04_outgoing_branch.xml` | `tct-hdon-v1` | Bán ra (Outgoing) | Hóa đơn có XML Namespace (`xmlns:inv`), MST chi nhánh 14 ký tự dạng 10-3 (`0312345678-001`), ngày lập định dạng `xs:dateTime`. |
| `tct_hdon_05_replacement.xml` | `tct-hdon-v1` | Thay thế (Replacement) | Có thông tin hóa đơn bị thay thế (`TTHDLQuan`): tính chất thay thế, số HĐ gốc, ngày HĐ gốc. |
| `tct_hdon_06_wrapped_transmission.xml` | `tct-hdon-v1` | Mua vào (Wrapped) | Hóa đơn nằm lồng trong gói thông điệp truyền nhận ngành thuế (`TDiep/DLieu/HDon`), kiểm tra parser bóc tách độc lập vị trí gốc. |
| `tct_hdon_07_missing_optional.xml` | `tct-hdon-v1` | Mua vào (Minimal) | Hóa đơn tối giản thiếu các trường không bắt buộc (không địa chỉ, không mã CQT, không bảng kê thuế), các trường bắt buộc vẫn đủ để vượt qua kiểm tra schema. |

---

## 3. Ground Truth (`ground_truth.json`)

Tệp `ground_truth.json` đi kèm là **bảng chân lý (Test Oracle)** xác định kết quả kỳ vọng cho từng trường dữ liệu:
- **Chuẩn hóa chuỗi**: MST và số hóa đơn giữ nguyên chuỗi (string) có số 0 ở đầu, không bị chuyển thành số nguyên (integer).
- **Chuẩn hóa Unicode**: Chuẩn Unicode NFC cho tiếng Việt (`raw_value` nguyên bản, `normalized_value` chuẩn NFC).
- **Định dạng số**: Dùng chuỗi biểu diễn số thập phân chính xác (`Decimal`), không dùng dấu phẩy hay dấu phân cách hàng nghìn.
- **Xác định hướng hóa đơn (direction)**:
  - Khách hàng là bên mua (`buyer_tax_id == client_tax_id`) $\rightarrow$ `incoming` (Hóa đơn đầu vào).
  - Khách hàng là bên bán (`seller_tax_id == client_tax_id`) $\rightarrow$ `outgoing` (Hóa đơn đầu ra).

---

## 4. Hướng dẫn sử dụng cho Developer và Tester

### Trong Pytest (Python / FastAPI)
```python
import json
from pathlib import Path
from app.xml_parser import parse_invoice_xml

FIXTURES = Path(__file__).parent / "fixtures" / "xml"
GROUND_TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))

def test_parse_standard_invoice():
    xml_data = (FIXTURES / "tct_hdon_01_vat10_standard.xml").read_bytes()
    expected = GROUND_TRUTH["files"]["tct_hdon_01_vat10_standard.xml"]
    
    result = parse_invoice_xml(xml_data, expected["client_tax_id"])
    assert result.schema_check.passed is True
    assert result.field("invoice_number").normalized_value == expected["fields"]["invoice_number"]
```

### Đánh giá KPI nghiệm thu (Acceptance Criteria)
1. **KPI 1 - Field Accuracy**: Tỷ lệ trường trích xuất đúng khi so khớp với `ground_truth.json`.
2. **KPI 2 - Whole-Document Correctness**: Kiểm tra tính toán chéo: `TgTTTBSo = TgTCThue + TgTThue`.
3. **KPI 3 - Evidence Integrity**: Lưu vết XML path (ví dụ: `/HDon/DLHDon/TTChung/SHDon`) làm bằng chứng cho từng trường.
