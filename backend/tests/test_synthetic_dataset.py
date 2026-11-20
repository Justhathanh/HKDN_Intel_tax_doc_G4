"""Kiểm thử tự động bộ dữ liệu thuế mẫu tổng hợp (Synthetic Tax Test Dataset - G4T-42).

Tác giả: Nguyễn Thanh Khiêm (Dev - Automated Testing / QA)
Phạm vi đối chiếu 6 tiêu chí Acceptance Criteria của Jira:
1. XML hóa đơn chuẩn PO (tct-hdon-v1)
2. PDF điện tử (text layer), PDF/ảnh scan (JPG/PNG)
3. Mẫu non-tax, tài liệu mờ/khó đọc, XML lỗi
4. Bảng Ground Truth JSON đầy đủ expected document type
5. Không dùng dữ liệu thật, đảm bảo an toàn bảo mật
6. Tương thích với các bộ xử lý parser của dự án
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
GROUND_TRUTH_PATH = XML_DIR / "ground_truth.json"


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    assert GROUND_TRUTH_PATH.exists(), "Tệp ground_truth.json không tồn tại!"
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def test_ground_truth_structure_and_expected_doc_types(ground_truth):
    """Kiểm tra cấu trúc ground_truth.json, đảm bảo 100% mẫu đều có expected_document_type."""
    assert "files" in ground_truth
    files_map = ground_truth["files"]
    assert len(files_map) >= 11, "Dataset phải bao gồm tối thiểu 11 tệp mẫu đa dạng!"

    for filename, meta in files_map.items():
        rel_path = meta.get("relative_path")
        assert rel_path, f"Thiếu relative_path trong {filename}"
        file_path = FIXTURES_DIR / rel_path
        assert file_path.exists(), f"Không tìm thấy file mẫu: {file_path}"
        assert file_path.stat().st_size > 0, f"File {filename} rỗng!"
        assert "expected_document_type" in meta, f"Thiếu expected_document_type cho {filename}"
        assert meta["expected_document_type"] in (
            "INVOICE_VAT", "NON_TAX_CONTRACT", "CORRUPT_XML"
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
    assert "HOA DON GIA TRI GIA TANG" in text
    assert "0109876543" in text
    assert "00000055" in text


def test_non_tax_contract_classification_sample():
    """Kiểm tra file Non-Tax (hợp đồng thông thường) chứa nội dung phục vụ phân loại (cho G4T-24)."""
    pdf_path = PDF_DIR / "non_tax_contract.pdf"
    assert pdf_path.exists()
    reader = PdfReader(str(pdf_path))
    text = reader.pages[0].extract_text()
    assert "HOP DONG NGUYEN TAC" in text
    assert "HOA DON GIA TRI GIA TANG" not in text


def test_scanned_image_samples_validity():
    """Kiểm tra các file ảnh scan rõ nét và mờ phục vụ OCR (cho G4T-23)."""
    clean_img_path = IMAGES_DIR / "invoice_scan_clean.png"
    blurred_img_path = IMAGES_DIR / "invoice_scan_blurred.png"
    assert clean_img_path.exists()
    assert blurred_img_path.exists()

    with Image.open(clean_img_path) as img:
        img.verify()
    with Image.open(blurred_img_path) as img:
        img.verify()


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
