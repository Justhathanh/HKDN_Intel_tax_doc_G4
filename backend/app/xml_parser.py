"""Parse trực tiếp XML hóa đơn điện tử, không qua OCR (G4T-61, G4T-46; RFP EXT 02, EXT 03, EXT 05, EXT 06).

Thiết kế: docs/G4T-61-parse-xml-hoa-don.md

- Mỗi chuẩn XML là một biến thể (Variant) có mapping và phiên bản riêng (ARC 03). Hiện có `tct-hdon-v1`, theo cấu trúc
  HDon/DLHDon/TTChung/NDHDon của hóa đơn điện tử Tổng cục Thuế. Biến thể thứ hai sẽ thêm khi PO chốt (RFP mục 2).
- Mọi giá trị giữ nguyên chuỗi gốc (MST, số hóa đơn có số 0 đầu, dấu tiếng Việt); số tiền dùng Decimal chính xác.
- Thiếu là "chưa biết", không phải 0 (EXT 06). Mỗi trường có XML path làm bằng chứng (EXT 05).
- DTD, entity và tham chiếu ngoài bị chặn (SEC 04); lỗi trả mã cố định, không trả nội dung tài liệu.
- Parse đúng schema không chứng minh hóa đơn hợp lệ hay chữ ký đúng (EXT 02, VN 06).
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from pydantic import BaseModel

PARSER_NAME = "xml-parser"
PARSER_VERSION = "0.2.0"

FieldStatus = Literal["present", "missing", "not_present", "needs_review", "conflict"]

# Mã lỗi; khớp với SAFE_ERRORS trong app/jobs.py để worker gọi jobs.fail(db, job, err.code).
XML_ERRORS: dict[str, str] = {
    "xml_unsafe": "XML có DTD, entity hoặc tham chiếu ngoài; không xử lý.",
    "xml_malformed": "XML sai cú pháp, không đọc được.",
    "xml_unsupported_variant": "XML không thuộc chuẩn hóa đơn nào đang hỗ trợ.",
    "xml_schema_invalid": "XML thiếu phần bắt buộc của chuẩn hóa đơn.",
}

TAX_ID_RE = re.compile(r"^\d{10}(-\d{3})?$|^\d{12}$")  # MST 10 số, chi nhánh 10-3, hoặc số định danh 12 số
DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")  # XML dùng dấu chấm thập phân, không có dấu phân cách hàng nghìn
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T[0-9:.+\-Z]*)?$")  # xs:date hoặc xs:dateTime


class XmlParseError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.message = XML_ERRORS[code]


class ExtractedField(BaseModel):
    """Một trường trích xuất, theo DAT 03 của RFP."""

    field_name: str
    raw_value: str | None
    normalized_value: str | None
    field_status: FieldStatus
    xml_path: str | None
    extraction_method: Literal["xml"] = "xml"


class SchemaCheck(BaseModel):
    passed: bool
    missing_required: list[str]
    conflicts: list[str]


class XmlParseResult(BaseModel):
    """Kết quả parse một hóa đơn XML; phần đầu theo mục 7 của docs/G4T-68-hop-dong-api-xu-ly.md."""

    document_id: str | None
    job_id: str | None
    processor: str = PARSER_NAME
    processor_version: str = PARSER_VERSION
    mapping_version: str
    outcome: Literal["parsed"] = "parsed"
    schema_check: SchemaCheck
    fields: list[ExtractedField]

    def field(self, name: str) -> ExtractedField | None:
        return next((f for f in self.fields if f.field_name == name), None)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    path: str  # đường dẫn tương đối từ phần tử HDon
    kind: Literal["text", "tax_id", "date", "decimal", "code"] = "text"
    required: bool = False


@dataclass(frozen=True)
class Variant:
    mapping_version: str
    root: str
    required_sections: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    tax_breakdown_path: str
    tax_breakdown_fields: tuple[tuple[str, str, str], ...]  # (tên, thẻ con, kiểu)


# Theo cấu trúc XML hóa đơn điện tử của Tổng cục Thuế (HDon/DLHDon). CHƯA đối chiếu với file thật của THTax:
# PO cần xác nhận trước khi đưa vào đo AT 02.
TCT_HDON_V1 = Variant(
    mapping_version="tct-hdon-v1",
    root="HDon",
    required_sections=("DLHDon", "DLHDon/TTChung", "DLHDon/NDHDon", "DLHDon/NDHDon/NBan"),
    fields=(
        FieldSpec("invoice_form", "DLHDon/TTChung/KHMSHDon", "code"),
        FieldSpec("invoice_series", "DLHDon/TTChung/KHHDon", "code"),
        FieldSpec("invoice_number", "DLHDon/TTChung/SHDon", "code", required=True),
        FieldSpec("issue_date", "DLHDon/TTChung/NLap", "date", required=True),
        FieldSpec("currency", "DLHDon/TTChung/DVTTe", "code"),
        FieldSpec("exchange_rate", "DLHDon/TTChung/TGia", "decimal"),
        FieldSpec("seller_name", "DLHDon/NDHDon/NBan/Ten", required=True),
        FieldSpec("seller_tax_id", "DLHDon/NDHDon/NBan/MST", "tax_id", required=True),
        FieldSpec("seller_address", "DLHDon/NDHDon/NBan/DChi"),
        FieldSpec("buyer_name", "DLHDon/NDHDon/NMua/Ten"),
        FieldSpec("buyer_tax_id", "DLHDon/NDHDon/NMua/MST", "tax_id"),
        FieldSpec("net_total", "DLHDon/NDHDon/TToan/TgTCThue", "decimal"),
        FieldSpec("tax_total", "DLHDon/NDHDon/TToan/TgTThue", "decimal"),
        FieldSpec("gross_total", "DLHDon/NDHDon/TToan/TgTTTBSo", "decimal", required=True),
        FieldSpec("gross_total_in_words", "DLHDon/NDHDon/TToan/TgTTTBChu"),
        # Tham chiếu vòng đời hóa đơn (thay thế, điều chỉnh), chỉ có khi hóa đơn liên quan hóa đơn khác (EXT 03, VN 02)
        FieldSpec("related_invoice_nature", "DLHDon/TTChung/TTHDLQuan/TCHDon", "code"),
        FieldSpec("related_invoice_form", "DLHDon/TTChung/TTHDLQuan/KHMSHDCLQuan", "code"),
        FieldSpec("related_invoice_series", "DLHDon/TTChung/TTHDLQuan/KHHDCLQuan", "code"),
        FieldSpec("related_invoice_number", "DLHDon/TTChung/TTHDLQuan/SHDCLQuan", "code"),
        FieldSpec("related_invoice_date", "DLHDon/TTChung/TTHDLQuan/NLHDCLQuan", "date"),
        FieldSpec("tax_authority_code", "MCCQT", "code"),
    ),
    tax_breakdown_path="DLHDon/NDHDon/TToan/THTTLTSuat/LTSuat",
    tax_breakdown_fields=(("rate", "TSuat", "code"), ("net_amount", "ThTien", "decimal"),
                          ("tax_amount", "TThue", "decimal")),
)

VARIANTS: tuple[Variant, ...] = (TCT_HDON_V1,)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(node: Element, name: str) -> list[Element]:
    return [c for c in node if _local(c.tag) == name]


def _find_all(base: Element, path: str) -> list[Element]:
    """Tìm theo đường dẫn tương đối, bỏ qua namespace; trả mọi phần tử khớp để phát hiện trùng."""
    nodes = [base]
    for part in path.split("/"):
        nodes = [child for node in nodes for child in _children(node, part)]
    return nodes


def _text(node: Element) -> str | None:
    """Chuỗi gốc (bỏ khoảng trắng hai đầu); phần tử rỗng coi như không có giá trị."""
    if node.text is None or not node.text.strip():
        return None
    return node.text.strip()


def _normalize(kind: str, raw: str) -> tuple[str | None, FieldStatus]:
    if kind == "decimal":
        if not DECIMAL_RE.match(raw):
            return None, "needs_review"  # dấu phẩy, dấu phân cách hàng nghìn... cần người xem (EXT 06)
        try:
            return str(Decimal(raw)), "present"
        except InvalidOperation:
            return None, "needs_review"
    if kind == "date":
        if not DATE_RE.match(raw):
            return None, "needs_review"  # dd/mm/yyyy hay mm/dd/yyyy là mơ hồ, không tự đoán
        try:
            return date.fromisoformat(raw[:10]).isoformat(), "present"
        except ValueError:
            return None, "needs_review"  # dd/mm/yyyy hay mm/dd/yyyy là mơ hồ, không tự đoán
    if kind == "tax_id":
        compact = raw.replace(" ", "")
        return (compact, "present") if TAX_ID_RE.match(compact) else (None, "needs_review")
    if kind == "code":
        return raw, "present"
    return unicodedata.normalize("NFC", raw), "present"


def _parse_root(data: bytes) -> Element:
    try:
        return SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise XmlParseError("xml_unsafe") from exc
    except (ParseError, ValueError) as exc:
        raise XmlParseError("xml_malformed") from exc


def _locate(root: Element, name: str) -> tuple[Element, str] | None:
    """Tìm phần tử gốc của hóa đơn, kể cả khi được bọc trong thông điệp khác; trả kèm đường dẫn tuyệt đối."""
    stack: list[tuple[Element, str]] = [(root, "/" + _local(root.tag))]
    while stack:
        node, path = stack.pop()
        if _local(node.tag) == name:
            return node, path
        stack.extend((child, f"{path}/{_local(child.tag)}") for child in reversed(list(node)))
    return None


def detect_variant(root: Element) -> tuple[Variant, Element, str]:
    for variant in VARIANTS:
        found = _locate(root, variant.root)
        if found and _find_all(found[0], "DLHDon/TTChung"):
            return variant, found[0], found[1]
    raise XmlParseError("xml_unsupported_variant")


def _extract(spec: FieldSpec, base: Element, base_path: str) -> ExtractedField:
    path = f"{base_path}/{spec.path}"
    nodes = _find_all(base, spec.path)
    if not nodes or all(_text(n) is None for n in nodes):
        status: FieldStatus = "missing" if spec.required else "not_present"
        return ExtractedField(field_name=spec.name, raw_value=None, normalized_value=None, field_status=status,
                              xml_path=path)
    values = {_text(n) for n in nodes if _text(n) is not None}
    if len(nodes) > 1:
        # Cùng một trường xuất hiện nhiều lần: không tự chọn (EXT 07); giữ giá trị đầu để người duyệt xem
        return ExtractedField(field_name=spec.name, raw_value=sorted(values)[0], normalized_value=None,
                              field_status="conflict", xml_path=path)
    raw = values.pop()
    normalized, status = _normalize(spec.kind, raw)
    return ExtractedField(field_name=spec.name, raw_value=raw, normalized_value=normalized, field_status=status,
                          xml_path=path)


def direction(client_tax_id: str, seller: str | None, buyer: str | None) -> tuple[str, FieldStatus]:
    """Khách hàng là bên mua: đầu vào; bên bán: đầu ra; cả hai hoặc không: xung đột cần duyệt (EXT 03)."""
    is_seller, is_buyer = seller == client_tax_id, buyer == client_tax_id
    if is_buyer and not is_seller:
        return "incoming", "present"
    if is_seller and not is_buyer:
        return "outgoing", "present"
    return "unknown", "conflict"


def parse_invoice_xml(data: bytes, client_tax_id: str, document_id: str | None = None,
                      job_id: str | None = None) -> XmlParseResult:
    """Parse một file XML hóa đơn. Ném XmlParseError với mã trong XML_ERRORS nếu không parse được."""
    root = _parse_root(data)
    variant, base, base_path = detect_variant(root)

    missing_sections = [s for s in variant.required_sections if not _find_all(base, s)]
    if missing_sections:
        raise XmlParseError("xml_schema_invalid")
    if len(_find_all(base, "DLHDon")) != 1:
        raise XmlParseError("xml_schema_invalid")  # một file một hóa đơn (RFP mục 2)

    fields = [_extract(spec, base, base_path) for spec in variant.fields]

    for i, row in enumerate(_find_all(base, variant.tax_breakdown_path), start=1):
        row_path = f"{base_path}/{variant.tax_breakdown_path}[{i}]"
        for name, tag, kind in variant.tax_breakdown_fields:
            fields.append(_extract(FieldSpec(f"tax_breakdown[{i}].{name}", tag, kind), row, row_path))

    by_name = {f.field_name: f for f in fields}
    label, status = direction(client_tax_id.strip(), by_name["seller_tax_id"].normalized_value,
                              by_name["buyer_tax_id"].normalized_value)
    fields.append(ExtractedField(field_name="direction", raw_value=None, normalized_value=label,
                                 field_status=status, xml_path=None))

    required = {s.name for s in variant.fields if s.required}
    return XmlParseResult(
        document_id=document_id, job_id=job_id, mapping_version=variant.mapping_version,
        schema_check=SchemaCheck(
            passed=not any(by_name[n].field_status == "missing" for n in required),
            missing_required=sorted(n for n in required if by_name[n].field_status == "missing"),
            conflicts=sorted(f.field_name for f in fields if f.field_status == "conflict")),
        fields=fields)
