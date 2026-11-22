"""Kiểm thử tự động bộ dữ liệu thuế mẫu tổng hợp (Synthetic Tax Test Dataset - G4T-42).

Tác giả: Nguyễn Thanh Khiêm (Dev - Automated Testing / QA)
Phối hợp: Lương Quốc An (Backend & Schema), Đào Đoàn Tường Vy (OCR & Phân loại tài liệu), Huỳnh Hà Thanh (PO), Nguyễn Mạnh Hùng (Mentor / PO Chốt chuẩn)
Căn cứ: RFP 2026 (Nghị định 254/2026/NĐ-CP & Thông tư 91/2026/TT-BTC) kế thừa chuẩn tct-hdon-v1
Quy chuẩn nhãn phân loại tài liệu: G4T-24 (INVOICE, TAX_NOTICE, TAX_PAYMENT_RECEIPT, UNKNOWN, MIXED)

Phạm vi Acceptance Criteria Jira G4T-42:
1. XML hóa đơn chuẩn PO (tct-hdon-v1 độc lập với dữ liệu dev).
2. PDF điện tử (text layer), PDF scan không text layer, PDF thông báo thuế & giấy nộp tiền.
3. Ảnh scan (PNG rõ, PNG mờ, JPG hóa đơn).
4. Mẫu non-tax (Hợp đồng kinh tế nhãn UNKNOWN).
5. Gói hồ sơ hỗn hợp đa định dạng (Mixed Pack) kèm manifest.json.
6. Bảng Ground Truth JSON đầy đủ và nhất quán toán học (Decimal).
7. Mẫu XML lỗi cú pháp (malformed_invoice.xml).
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from defusedxml import ElementTree as SafeET
from PIL import Image
from pypdf import PdfReader

FIXTURES_DIR = Path(__file__).parent / "fixtures"
XML_DIR = FIXTURES_DIR / "xml"
PDF_DIR = FIXTURES_DIR / "pdf"
IMAGES_DIR = FIXTURES_DIR / "images"
MIXED_DIR = FIXTURES_DIR / "mixed_pack"
GROUND_TRUTH_PATH = (
    FIXTURES_DIR / "ground_truth.json"
    if (FIXTURES_DIR / "ground_truth.json").exists()
    else XML_DIR / "ground_truth.json"
)

ALLOWED_DOC_TYPES = {
    "INVOICE",
    "TAX_NOTICE",
    "TAX_PAYMENT_RECEIPT",
    "UNKNOWN",
    "MIXED",
}


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    assert GROUND_TRUTH_PATH.exists(), "Tệp ground_truth.json không tồn tại!"
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def test_ground_truth_structure_and_expected_doc_types(ground_truth):
    """Kiểm tra cấu trúc ground_truth.json, đảm bảo 100% mẫu đều có expected_document_type theo G4T-24."""
    assert "files" in ground_truth
    files_map = ground_truth["files"]
    assert len(files_map) >= 15, f"Dataset phải có ít nhất 15 tệp/gói mẫu đa dạng! Hiện có: {len(files_map)}"

    for filename, meta in files_map.items():
        rel_path = meta.get("relative_path")
        assert rel_path, f"Thiếu relative_path trong {filename}"
        file_path = FIXTURES_DIR / rel_path
        assert file_path.exists(), f"Không tìm thấy file mẫu: {file_path}"
        assert file_path.stat().st_size > 0, f"File {filename} rỗng!"
        assert "expected_document_type" in meta, f"Thiếu expected_document_type cho {filename}"
        doc_type = meta["expected_document_type"]
        assert doc_type in ALLOWED_DOC_TYPES, (
            f"Nhãn {doc_type} của {filename} không nằm trong tập chuẩn G4T-24 {ALLOWED_DOC_TYPES}"
        )


@pytest.mark.parametrize("filename", [
    "tct_hdon_01_vat10_standard.xml",
    "tct_hdon_02_vat8_multi_rate.xml",
    "tct_hdon_03_vat0_export_foreign.xml",
    "tct_hdon_04_outgoing_branch.xml",
    "tct_hdon_05_replacement.xml",
    "tct_hdon_06_wrapped_transmission.xml",
    "tct_hdon_07_missing_optional.xml",
])
def test_valid_xml_syntax_safe_and_well_formed(filename):
    """Đảm bảo các file XML mẫu hợp lệ không chứa DTD độc hại (XXE) và parse an toàn với defusedxml."""
    xml_bytes = (XML_DIR / filename).read_bytes()
    root = SafeET.fromstring(xml_bytes, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    assert root is not None


def test_malformed_xml_detection():
    """Kiểm tra mẫu XML lỗi cú pháp (malformed_invoice.xml) phải raise ParseError đúng thiết kế."""
    from xml.etree.ElementTree import ParseError
    malformed_bytes = (XML_DIR / "malformed_invoice.xml").read_bytes()
    with pytest.raises(ParseError):
        SafeET.fromstring(malformed_bytes)


def test_pdf_digital_text_layer_extractable():
    """Kiểm tra file PDF hóa đơn điện tử có text layer trích xuất được trực tiếp (cho G4T-62)."""
    pdf_path = PDF_DIR / "invoice_digital_text_layer.pdf"
    assert pdf_path.exists()
    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "HÓA ĐƠN GIÁ TRỊ GIA TĂNG" in text
    assert "0108998877" in text
    assert "00000088" in text


def test_pdf_scanned_has_no_text_layer():
    """Kiểm tra file PDF scan thuần túy không có text layer để phục vụ phân biệt luồng PDF (cho G4T-62)."""
    pdf_path = PDF_DIR / "invoice_scanned_no_text.pdf"
    assert pdf_path.exists()
    reader = PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    assert len(text.strip()) == 0, f"PDF scan không được chứa text layer! Nhận được: '{text}'"


def test_non_tax_contract_classification_sample():
    """Kiểm tra file Non-Tax (hợp đồng kinh tế) có nhãn UNKNOWN phục vụ phân loại tài liệu (cho G4T-24)."""
    pdf_path = PDF_DIR / "non_tax_contract.pdf"
    assert pdf_path.exists()
    reader = PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    assert "HỢP ĐỒNG KINH TẾ DỊCH VỤ" in text
    assert "HÓA ĐƠN GIÁ TRỊ GIA TĂNG" not in text


def test_tax_notice_classification_sample():
    """Kiểm tra file Thông báo thuế của CQT có nhãn TAX_NOTICE phục vụ phân loại tài liệu (cho G4T-24)."""
    pdf_path = PDF_DIR / "tax_notice_cqt.pdf"
    assert pdf_path.exists()
    reader = PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    assert "THÔNG BÁO" in text
    assert "14285/TB-CCT" in text
    assert "GIẢ LẬP" in text


def test_tax_payment_receipt_classification_sample():
    """Kiểm tra file Giấy nộp tiền NSNN có nhãn TAX_PAYMENT_RECEIPT phục vụ phân loại tài liệu (cho G4T-24)."""
    pdf_path = PDF_DIR / "tax_payment_receipt_nsnn.pdf"
    assert pdf_path.exists()
    reader = PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    assert "GIẤY NỘP TIỀN VÀO NGÂN SÁCH NHÀ NƯỚC" in text
    assert "GNT-2026" in text
    assert "GIẢ LẬP" in text


def test_mixed_documents_multi_page_pdf():
    """Kiểm tra tệp PDF đa trang ghép nhiều loại chứng từ mang nhãn MIXED (theo chuẩn G4T-24)."""
    pdf_path = PDF_DIR / "mixed_documents_multi_page.pdf"
    assert pdf_path.exists(), "mixed_documents_multi_page.pdf phải tồn tại!"
    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == 3, f"mixed_documents_multi_page.pdf phải có đúng 3 trang, nhận {len(reader.pages)}"
    # Trang 1: Hóa đơn điện tử
    p1_text = reader.pages[0].extract_text()
    assert "HÓA ĐƠN GIÁ TRỊ GIA TĂNG" in p1_text
    # Trang 2: Thông báo nộp tiền thuế
    p2_text = reader.pages[1].extract_text()
    assert "THÔNG BÁO NỘP TIỀN THUẾ" in p2_text
    # Trang 3: Giấy nộp tiền NSNN
    p3_text = reader.pages[2].extract_text()
    assert "GIẤY NỘP TIỀN VÀO NGÂN SÁCH NHÀ NƯỚC" in p3_text


def test_scanned_image_samples_validity():
    """Kiểm tra các file ảnh scan PNG và JPG phục vụ OCR (cho G4T-23 và AC G4T-42)."""
    clean_img_path = IMAGES_DIR / "invoice_scan_clean.png"
    blurred_img_path = IMAGES_DIR / "invoice_scan_blurred.png"
    jpg_img_path = IMAGES_DIR / "invoice_vat10_retail.jpg"

    assert clean_img_path.exists()
    assert blurred_img_path.exists()
    assert jpg_img_path.exists()

    with Image.open(clean_img_path) as img:
        img.verify()
    with Image.open(blurred_img_path) as img:
        img.verify()
    with Image.open(jpg_img_path) as img:
        img.verify()


def test_mixed_pack_package_and_manifest():
    """Kiểm tra gói tài liệu hỗn hợp đa định dạng Mixed Pack có đầy đủ manifest và tệp thành phần."""
    manifest_path = MIXED_DIR / "manifest.json"
    assert manifest_path.exists(), "Mixed Pack phải có manifest.json!"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest_data.get("batch_type") == "MIXED"
    items = manifest_data.get("items", [])
    assert len(items) >= 5, "Mixed Pack phải có ít nhất 5 tài liệu thành phần!"

    for item in items:
        file_name = item["file"]
        target = MIXED_DIR / file_name
        assert target.exists(), f"Tệp {file_name} trong mixed_pack không tồn tại trên đĩa!"
        assert target.stat().st_size > 0, f"Tệp {file_name} rỗng!"
        assert item["expected_document_type"] in ALLOWED_DOC_TYPES


def test_business_logic_arithmetic_consistency(ground_truth):
    """Kiểm tra tính nhất quán số học trên dataset: Tổng tiền trước thuế + tiền thuế = tổng tiền thanh toán."""
    for filename, meta in ground_truth["files"].items():
        fields = meta.get("fields", {})
        if "net_total" in fields and "tax_total" in fields and "gross_total" in fields:
            net = Decimal(fields["net_total"])
            tax = Decimal(fields["tax_total"])
            gross = Decimal(fields["gross_total"])
            assert net + tax == gross, f"Lỗi số học trong {filename}: {net} + {tax} != {gross}"


def test_tax_ids_and_invoice_numbers_format(ground_truth):
    """Kiểm tra MST và số hóa đơn trong dataset đảm bảo chuẩn chuỗi có số 0 ở đầu."""
    for filename, meta in ground_truth["files"].items():
        fields = meta.get("fields", {})
        if "invoice_number" in fields:
            inv_no = fields["invoice_number"]
            assert isinstance(inv_no, str), f"Số hóa đơn phải là dạng string trong {filename}"
            assert len(inv_no) >= 6, f"Số hóa đơn {inv_no} phải có ít nhất 6 chữ số kèm số 0 đầu"

        if "seller_tax_id" in fields:
            seller_tax = fields["seller_tax_id"]
            cleaned_mst = seller_tax.replace("-", "")
            assert cleaned_mst.isdigit(), f"MST người bán {seller_tax} không đúng định dạng!"


def test_integration_with_current_xml_parser(ground_truth):
    """Kiểm tra bộ dữ liệu XML tương thích hoàn toàn với app.xml_parser hiện có của hệ thống."""
    from app.xml_parser import parse_invoice

    for filename, meta in ground_truth["files"].items():
        if meta.get("format") == "xml" and meta.get("schema_passed") is True:
            rel_path = meta["relative_path"]
            xml_bytes = (FIXTURES_DIR / rel_path).read_bytes()
            client_tax_id = meta["client_tax_id"]

            fields = parse_invoice(xml_bytes, client_tax_id)
            assert len(fields) > 0

            # Lấy trường direction
            dir_field = next(f for f in fields if f.name == "direction")
            assert dir_field.normalized == meta["expected_direction"], (
                f"Direction không khớp cho {filename}: mong đợi {meta['expected_direction']}, nhận {dir_field.normalized}"
            )
