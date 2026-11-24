"""Đánh giá parser XML trên dataset chính thức G4T-42 theo HAI LỚP riêng biệt (G4T-61).

Nhận xét P0 của trưởng nhóm: field accuracy và độ đúng của cả tài liệu phải đo riêng, không gộp một điểm.

- Lớp TRƯỜNG (field accuracy): số trường trích xuất khớp ground truth / tổng số trường có trong ground truth.
- Lớp TÀI LIỆU (document correctness): tài liệu chỉ tính là đúng khi MỌI trường khớp, hướng hóa đơn đúng,
  kết quả kiểm tra schema đúng như ground truth và không có quy tắc mức tài liệu nào báo `failed`.
- Tệp XML lỗi được đếm riêng: phải trả đúng mã lỗi kỳ vọng.

Chạy: cd backend && python -m scripts.evaluate_xml_dataset [--json]
"""
import json
import sys
from pathlib import Path

from app.extraction import document_findings
from app.xml_parser import PARSER_VERSION, VARIANTS, XmlParseError, parse_invoice_xml

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def evaluate(fixtures: Path = FIXTURES) -> dict:
    ground_truth = json.loads((fixtures / "ground_truth.json").read_text(encoding="utf-8"))
    docs, errors = [], []
    for name, meta in ground_truth["files"].items():
        if meta.get("format", "").lower() != "xml":
            continue
        data = (fixtures / meta["relative_path"]).read_bytes()
        if meta.get("expected_error"):
            try:
                parse_invoice_xml(data, meta.get("client_tax_id") or "")
                got = None
            except XmlParseError as err:
                got = err.code
            errors.append({"file": name, "expected": meta["expected_error"], "got": got,
                           "correct": got == meta["expected_error"]})
            continue
        result = parse_invoice_xml(data, meta["client_tax_id"])
        values = {f.field_name: f.normalized_value for f in result.fields}
        expected = meta.get("fields") or {}
        wrong = sorted(k for k, v in expected.items() if values.get(k) != v)
        failed_rules = sorted(f["rule_code"] for f in document_findings(result) if f["status"] == "failed")
        direction_ok = values.get("direction") == meta.get("expected_direction")
        schema_ok = result.schema_check.passed == meta.get("schema_passed")
        docs.append({"file": name, "fields_total": len(expected), "fields_correct": len(expected) - len(wrong),
                     "wrong_fields": wrong, "direction_ok": direction_ok, "schema_ok": schema_ok,
                     "failed_document_rules": failed_rules,
                     "document_correct": not wrong and direction_ok and schema_ok and not failed_rules})
    fields_total = sum(d["fields_total"] for d in docs)
    fields_correct = sum(d["fields_correct"] for d in docs)
    return {
        "dataset_version": ground_truth.get("version"),
        "parser_version": PARSER_VERSION,
        "mapping_version": ", ".join(v.mapping_version for v in VARIANTS),
        "field_level": {"correct": fields_correct, "total": fields_total,
                        "accuracy": round(fields_correct / fields_total, 4) if fields_total else None},
        "document_level": {"correct": sum(d["document_correct"] for d in docs), "total": len(docs)},
        "error_cases": {"correct": sum(e["correct"] for e in errors), "total": len(errors)},
        "documents": docs,
        "errors": errors,
    }


def to_markdown(report: dict) -> str:
    f, d, e = report["field_level"], report["document_level"], report["error_cases"]
    lines = [
        f"Dataset `{report['dataset_version']}` · parser `{report['parser_version']}` · "
        f"mapping `{report['mapping_version']}`",
        "",
        "| Lớp | Đúng | Tổng |",
        "|---|---|---|",
        f"| Trường (field accuracy) | {f['correct']} | {f['total']} |",
        f"| Tài liệu (document correctness) | {d['correct']} | {d['total']} |",
        f"| Tệp lỗi trả đúng mã | {e['correct']} | {e['total']} |",
        "",
        "| Tệp | Trường đúng | Hướng | Schema | Quy tắc tài liệu lỗi | Tài liệu đúng |",
        "|---|---|---|---|---|---|",
    ]
    for doc in report["documents"]:
        lines.append(f"| `{doc['file']}` | {doc['fields_correct']}/{doc['fields_total']} | "
                     f"{'✔' if doc['direction_ok'] else '✘'} | {'✔' if doc['schema_ok'] else '✘'} | "
                     f"{', '.join(doc['failed_document_rules']) or '—'} | {'✔' if doc['document_correct'] else '✘'} |")
    for err in report["errors"]:
        lines.append(f"| `{err['file']}` | lỗi kỳ vọng `{err['expected']}`, nhận `{err['got']}` | | | | "
                     f"{'✔' if err['correct'] else '✘'} |")
    return "\n".join(lines)


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2) if "--json" in sys.argv else to_markdown(report))
