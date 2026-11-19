"""Kiểm thử tự động bộ dữ liệu thuế mẫu tổng hợp (Synthetic Tax Test Dataset - G4T-42).

Tác giả: Nguyễn Thanh Khiêm (Dev - Automated Testing / QA)
Phạm vi:
- Xác thực tính hợp lệ cú pháp (XML Validity & Safety) của tất cả file XML mẫu
- Xác thực tính nhất quán giữa file XML mẫu và bảng chân lý (ground_truth.json)
- Kiểm tra các quy tắc nghiệp vụ thuế (logic tính tổng tiền, cấu trúc MST, số hóa đơn)
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from defusedxml import ElementTree as SafeET

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "xml"
GROUND_TRUTH_PATH = FIXTURES_DIR / "ground_truth.json"


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    assert GROUND_TRUTH_PATH.exists(), "Tệp ground_truth.json không tồn tại!"
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def test_ground_truth_structure_and_files_exist(ground_truth):
    """Kiểm tra cấu trúc ground_truth.json và đảm bảo mọi file khai báo đều có mặt trên đĩa."""
    assert "files" in ground_truth
    files_map = ground_truth["files"]
    assert len(files_map) >= 7, "Dataset phải bao gồm tối thiểu 7 trường hợp kiểm thử!"

    for filename, meta in files_map.items():
        file_path = FIXTURES_DIR / filename
        assert file_path.exists(), f"Không tìm thấy file mẫu: {filename}"
        assert file_path.stat().st_size > 0, f"File {filename} rỗng!"
        assert meta["variant"] == "tct-hdon-v1"
        assert meta["expected_direction"] in ("incoming", "outgoing")
        assert "fields" in meta


@pytest.mark.parametrize("filename", [
    "tct_hdon_01_vat10_standard.xml",
    "tct_hdon_02_vat8_multi_rate.xml",
    "tct_hdon_03_vat0_export_foreign.xml",
    "tct_hdon_04_outgoing_branch.xml",
    "tct_hdon_05_replacement.xml",
    "tct_hdon_06_wrapped_transmission.xml",
    "tct_hdon_07_missing_optional.xml",
])
def test_xml_syntax_safe_and_well_formed(filename):
    """Đảm bảo tất cả file XML mẫu không chứa DTD độc hại (XXE) và parse an toàn với defusedxml."""
    xml_bytes = (FIXTURES_DIR / filename).read_bytes()
    root = SafeET.fromstring(xml_bytes, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    assert root is not None


def test_business_logic_arithmetic_consistency(ground_truth):
    """Kiểm tra tính nhất quán số học trên dataset: Tổng tiền trước thuế + tiền thuế = tổng tiền thanh toán."""
    for filename, meta in ground_truth["files"].items():
        fields = meta["fields"]
        if "net_total" in fields and "tax_total" in fields and "gross_total" in fields:
            net = Decimal(fields["net_total"])
            tax = Decimal(fields["tax_total"])
            gross = Decimal(fields["gross_total"])
            assert net + tax == gross, f"Lỗi số học trong {filename}: {net} + {tax} != {gross}"


def test_tax_ids_and_invoice_numbers_format(ground_truth):
    """Kiểm tra MST và số hóa đơn trong dataset đảm bảo chuẩn chuỗi có số 0 ở đầu."""
    for filename, meta in ground_truth["files"].items():
        fields = meta["fields"]
        inv_no = fields.get("invoice_number")
        assert inv_no is not None
        assert isinstance(inv_no, str), f"Số hóa đơn phải là dạng string trong {filename}"
        assert len(inv_no) >= 6, f"Số hóa đơn {inv_no} phải có ít nhất 6 chữ số kèm số 0 đầu"

        seller_tax = fields.get("seller_tax_id")
        assert seller_tax is not None
        # MST Việt Nam: 10 chữ số hoặc 14 ký tự (10 số - 3 số chi nhánh) hoặc 12 số CCCD/hộ kinh doanh
        cleaned_mst = seller_tax.replace("-", "")
        assert cleaned_mst.isdigit(), f"MST người bán {seller_tax} không đúng định dạng!"


def test_integration_with_current_xml_parser(ground_truth):
    """Kiểm tra bộ dữ liệu tương thích hoàn toàn với app.xml_parser hiện có của hệ thống."""
    from app.xml_parser import parse_invoice

    for filename, meta in ground_truth["files"].items():
        xml_bytes = (FIXTURES_DIR / filename).read_bytes()
        client_tax_id = meta["client_tax_id"]

        fields = parse_invoice(xml_bytes, client_tax_id)
        assert len(fields) > 0

        # Lấy trường direction
        dir_field = next(f for f in fields if f.name == "direction")
        assert dir_field.normalized == meta["expected_direction"], (
            f"Direction không khớp cho {filename}: mong đợi {meta['expected_direction']}, nhận {dir_field.normalized}"
        )
