"""Bộ xử lý thật cho job `extract` của worker (G4T-61, G4T-46).

Sửa nhận xét P0 của trưởng nhóm "worker báo thành công giả": trước đây bộ xử lý mặc định chỉ đọc bản gốc
rồi báo SUCCEEDED mà không trích xuất gì. Nay:

- XML hóa đơn: parse bằng `xml_parser.parse_invoice_xml`, lưu kết quả vào `extraction_runs`,
  `extracted_fields` (lớp đánh giá theo TRƯỜNG) và `document_validations` (lớp đánh giá theo CẢ TÀI LIỆU),
  tất cả gắn `document_id` + `job_id`. Chỉ khi đó job mới SUCCEEDED.
- XML không parse được: job lỗi với mã cố định (xml_*), không thử lại, vào `dead_letter`; vẫn lưu một
  `extraction_runs` trạng thái failed để truy vết.
- Loại chưa có bộ xử lý (PDF, ảnh: chờ G4T-62 và OCR): lỗi `unsupported_document`, KHÔNG báo thành công.

Hàm dùng chung session của worker (lấy qua `object_session(job)`), nên kết quả và trạng thái job được
commit cùng một transaction: không có job SUCCEEDED mà thiếu kết quả, hoặc ngược lại.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session, object_session

from .domain_models import DocumentValidation, ExtractedField, ExtractionRun, TaxEntity
from .jobs import JobError
from .models import Client, Document, ProcessingJob
from .xml_parser import PARSER_NAME, PARSER_VERSION, XmlParseError, XmlParseResult, parse_invoice_xml

XML_MIME = "application/xml"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_tax_id(db: Session, document: Document) -> str:
    """MST dùng để xác định hướng hóa đơn: pháp nhân của tài liệu nếu có, không thì MST khách hàng."""
    entity_id = getattr(document, "entity_id", None)
    if entity_id:
        entity = db.get(TaxEntity, entity_id)
        if entity is not None:
            return entity.tax_id
    client = db.get(Client, document.client_id)
    return client.tax_id if client else ""


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def document_findings(result: XmlParseResult) -> list[dict]:
    """Lớp đánh giá theo CẢ TÀI LIỆU, tách riêng khỏi trạng thái từng trường (nhận xét P0 "hai lớp đánh giá").

    Một tài liệu có thể có mọi trường riêng lẻ đều `present` mà vẫn sai ở mức tài liệu (ví dụ tổng tiền không
    khớp). Các quy tắc ở đây không đổi `field_status` của trường nào.
    """
    by_name = {f.field_name: f for f in result.fields}
    findings = [
        {"rule_code": "required_fields_present",
         "status": "passed" if not result.schema_check.missing_required else "failed",
         "details": {"missing": result.schema_check.missing_required}},
        {"rule_code": "no_field_conflicts",
         "status": "passed" if not result.schema_check.conflicts else "failed",
         "details": {"conflicts": result.schema_check.conflicts}},
    ]

    # EXT 07: tiền trước thuế + tiền thuế = tổng thanh toán (số thập phân chính xác, không làm tròn).
    net, tax, gross = (_decimal(by_name[n].normalized_value) for n in ("net_total", "tax_total", "gross_total"))
    if None in (net, tax, gross):
        findings.append({"rule_code": "totals_consistent", "status": "skipped",
                         "details": {"reason": "thiếu tổng tiền hoặc thuế; không suy ra giá trị thiếu (EXT 06)"}})
    else:
        findings.append({"rule_code": "totals_consistent", "status": "passed" if net + tax == gross else "failed",
                         "details": {"net_total": str(net), "tax_total": str(tax), "gross_total": str(gross)}})

    # Tổng tiền thuế theo từng thuế suất phải bằng tổng tiền thuế của hóa đơn (khi XML có bảng tổng hợp).
    rows = [f for f in result.fields if f.field_name.startswith("tax_breakdown[") and f.field_name.endswith(".tax_amount")]
    amounts = [_decimal(f.normalized_value) for f in rows]
    if not rows or tax is None or None in amounts:
        findings.append({"rule_code": "tax_breakdown_consistent", "status": "skipped",
                         "details": {"reason": "không có bảng thuế suất đầy đủ hoặc thiếu tổng thuế"}})
    else:
        total = sum(amounts, Decimal(0))
        findings.append({"rule_code": "tax_breakdown_consistent", "status": "passed" if total == tax else "failed",
                         "details": {"sum_breakdown": str(total), "tax_total": str(tax)}})

    direction = by_name["direction"]
    findings.append({"rule_code": "direction_determined",
                     "status": "passed" if direction.field_status == "present" else "failed",
                     "details": {"direction": direction.normalized_value}})
    return findings


def save_xml_result(db: Session, job: ProcessingJob, document: Document, result: XmlParseResult) -> ExtractionRun:
    run = ExtractionRun(client_id=document.client_id, document_id=document.id, job_id=job.id,
                        extractor_name=PARSER_NAME, extractor_version=PARSER_VERSION, status="succeeded",
                        finished_at=_now(),
                        metadata_json={"mapping_version": result.mapping_version,
                                       "schema_passed": result.schema_check.passed})
    db.add(run)
    db.flush()
    for field in result.fields:
        db.add(ExtractedField(
            extraction_run_id=run.id, field_name=field.field_name, raw_value=field.raw_value,
            normalized_value=field.normalized_value, field_status=field.field_status,
            extraction_method=field.extraction_method,
            # XML đọc theo quy tắc cố định, không có điểm tin cậy kiểu mô hình (DAT 03: "confidence if available")
            confidence=None,
            source_anchor={"xml_path": field.xml_path} if field.xml_path else None))
    for finding in document_findings(result):
        db.add(DocumentValidation(document_id=document.id, validation_scope="whole_document",
                                  rule_code=finding["rule_code"], status=finding["status"],
                                  details={**finding["details"], "extraction_run_id": run.id, "job_id": job.id}))
    db.flush()
    return run


def extract_processor(job: ProcessingJob, data: bytes) -> str:
    """Bộ xử lý mặc định của worker. Trả phiên bản bộ xử lý; lỗi thì ném JobError với mã an toàn."""
    db = object_session(job)
    document = db.get(Document, job.document_id)
    if document.mime_type != XML_MIME:
        raise JobError("unsupported_document")  # PDF/ảnh: chờ G4T-62 và OCR, không báo thành công giả
    try:
        result = parse_invoice_xml(data, _client_tax_id(db, document), document_id=document.id, job_id=job.id)
    except XmlParseError as err:
        db.add(ExtractionRun(client_id=document.client_id, document_id=document.id, job_id=job.id,
                             extractor_name=PARSER_NAME, extractor_version=PARSER_VERSION, status="failed",
                             finished_at=_now(), error_code=err.code))
        db.flush()
        raise JobError(err.code) from err
    save_xml_result(db, job, document, result)
    return f"{PARSER_NAME} {PARSER_VERSION}"
