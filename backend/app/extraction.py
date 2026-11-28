"""Bộ xử lý thật cho job `extract` của worker (G4T-61, G4T-46).

Sửa nhận xét P0 của trưởng nhóm "worker báo thành công giả": trước đây bộ xử lý mặc định chỉ đọc bản gốc
rồi báo SUCCEEDED mà không trích xuất gì. Nay:

- XML hóa đơn: parse bằng `xml_parser.parse_invoice_xml`, lưu kết quả vào `extraction_runs`,
  `extracted_fields` (lớp đánh giá theo TRƯỜNG) và `document_validations` (lớp đánh giá theo CẢ TÀI LIỆU),
  tất cả gắn `document_id` + `job_id`. Chỉ khi đó job mới SUCCEEDED.
- XML không parse được: job lỗi với mã cố định (xml_*), không thử lại, vào `dead_letter`; vẫn lưu một
  `extraction_runs` trạng thái failed để truy vết.
- PDF (G4T-62): đọc lớp chữ theo từng trang, mỗi trang một `extracted_fields` (`page_text`,
  `extraction_method='pdf_text'`, neo `page_number`). Trang không có chữ được đánh dấu cần OCR: run có
  trạng thái `needs_ocr`, không lưu chuỗi rỗng như thể đã đọc được.
- Loại chưa có bộ xử lý (ảnh: chờ OCR G4T-23): lỗi `unsupported_document`, KHÔNG báo thành công.

Hàm dùng chung session của worker (lấy qua `object_session(job)`), nên kết quả và trạng thái job được
commit cùng một transaction: không có job SUCCEEDED mà thiếu kết quả, hoặc ngược lại.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session, object_session

from .domain_models import DocumentValidation, ExtractedField, ExtractionRun, TaxEntity
from .jobs import JobError
from .models import Client, Document, ProcessingJob
from .pdf_text import EXTRACTOR_NAME as PDF_EXTRACTOR, EXTRACTOR_VERSION as PDF_VERSION
from .pdf_text import PdfTextError, PdfTextResult, extract_pdf_text
from .xml_parser import PARSER_NAME, PARSER_VERSION, XmlParseError, XmlParseResult, parse_invoice_xml

XML_MIME = "application/xml"
PDF_MIME = "application/pdf"


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

    # Ngày: hóa đơn thay thế/điều chỉnh không thể có ngày lập trước hóa đơn gốc mà nó tham chiếu (EXT 03, VN 02).
    issued, related = by_name["issue_date"].normalized_value, by_name["related_invoice_date"].normalized_value
    if issued is None or related is None:
        findings.append({"rule_code": "related_invoice_date_not_after_issue", "status": "skipped",
                         "details": {"reason": "không có tham chiếu hóa đơn liên quan hoặc thiếu ngày"}})
    else:  # đã chuẩn hóa YYYY-MM-DD nên so chuỗi là so ngày
        findings.append({"rule_code": "related_invoice_date_not_after_issue",
                         "status": "passed" if related <= issued else "failed",
                         "details": {"issue_date": issued, "related_invoice_date": related}})

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


def save_pdf_text_result(db: Session, job: ProcessingJob, document: Document, result: PdfTextResult) -> ExtractionRun:
    """Lưu chữ từng trang. Gắn document_id + job_id qua extraction_run; page_number nằm trong source_anchor."""
    run = ExtractionRun(client_id=document.client_id, document_id=document.id, job_id=job.id,
                        extractor_name=PDF_EXTRACTOR, extractor_version=PDF_VERSION,
                        status="succeeded" if result.outcome == "parsed" else "needs_ocr",
                        finished_at=_now(),
                        metadata_json={"outcome": result.outcome, "page_count": result.page_count,
                                       "text_pages": result.text_pages, "ocr_pages": result.ocr_pages})
    db.add(run)
    db.flush()
    for page in result.pages:
        db.add(ExtractedField(
            extraction_run_id=run.id, field_name="page_text",
            raw_value=page.raw_text if page.has_text_layer else None,
            normalized_value=page.text if page.has_text_layer else None,
            # Trang cần OCR: không có giá trị, KHÔNG phải chuỗi rỗng "đọc được".
            field_status="present" if page.has_text_layer else "missing",
            extraction_method="pdf_text", confidence=None,
            source_anchor={"page_number": page.page_number, "char_count": page.char_count,
                           "needs_ocr": not page.has_text_layer, "reason": page.reason}))
    db.add(DocumentValidation(
        document_id=document.id, validation_scope="whole_document", rule_code="pdf_text_layer_available",
        status="passed" if result.outcome == "parsed" else "failed",
        details={"page_count": result.page_count, "ocr_pages": result.ocr_pages,
                 "extraction_run_id": run.id, "job_id": job.id}))
    db.flush()
    return run


def _process_pdf(db: Session, job: ProcessingJob, document: Document, data: bytes) -> str:
    try:
        result = extract_pdf_text(data)
    except PdfTextError as err:
        db.add(ExtractionRun(client_id=document.client_id, document_id=document.id, job_id=job.id,
                             extractor_name=PDF_EXTRACTOR, extractor_version=PDF_VERSION, status="failed",
                             finished_at=_now(), error_code=err.code))
        db.flush()
        raise JobError(err.code) from err
    save_pdf_text_result(db, job, document, result)
    return f"{PDF_EXTRACTOR} {PDF_VERSION}"


def extract_processor(job: ProcessingJob, data: bytes) -> str:
    """Bộ xử lý mặc định của worker. Trả phiên bản bộ xử lý; lỗi thì ném JobError với mã an toàn."""
    db = object_session(job)
    document = db.get(Document, job.document_id)
    if document.mime_type == PDF_MIME:
        return _process_pdf(db, job, document, data)
    if document.mime_type != XML_MIME:
        raise JobError("unsupported_document")  # ảnh: chờ OCR (G4T-23), không báo thành công giả
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
