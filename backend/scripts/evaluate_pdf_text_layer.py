"""Đánh giá đọc lớp chữ PDF (G4T-62) trên dataset chính thức G4T-42. Không dùng dữ liệu tự tạo.

Nhãn so sánh lấy từ dữ liệu của Khiêm (PR #15), không do người viết parser tự đặt:
- Định tuyến: `mixed_pack/manifest.json` ghi `PDF_TEXT` (có lớp chữ) hoặc `PDF_SCAN` (phải OCR). Các file trong
  `pdf/` trùng byte (cùng SHA-256) với file trong mixed pack nên dùng chung nhãn; file không có nhãn thì bỏ qua
  phần định tuyến, không tự đoán.
- Số trang: `total_pages` trong `ground_truth.json` (nếu có).
- Nội dung: với file `PDF_TEXT`, mọi giá trị trong `fields` của ground truth phải xuất hiện trong chữ đọc được
  (số tiền so theo chữ số, bỏ dấu phân cách hàng nghìn).

Chạy: cd backend && python -m scripts.evaluate_pdf_text_layer [--json]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from app.pdf_text import EXTRACTOR_VERSION, extract_pdf_text

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
EXPECTED_OUTCOME = {"PDF_TEXT": "parsed", "PDF_SCAN": "needs_ocr"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def route_labels(fixtures: Path = FIXTURES) -> dict[str, str]:
    """SHA-256 của file PDF -> nhãn định dạng trong manifest chính thức."""
    manifest = json.loads((fixtures / "mixed_pack" / "manifest.json").read_text(encoding="utf-8"))
    return {_sha(fixtures / "mixed_pack" / item["file"]): item["format"]
            for item in manifest["items"] if item["format"] in EXPECTED_OUTCOME}


def _found(value: str, text: str) -> bool:
    if value in text:
        return True
    if value.isdigit():  # số tiền: "55000000" khớp "55.000.000" hoặc "55,000,000"
        return value in re.sub(r"(?<=\d)[.,\s](?=\d{3})", "", text)
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if iso:  # ngày chuẩn hóa "2026-04-12" khớp cách in trên hóa đơn "Ngày 12 tháng 04 năm 2026" hoặc "12/04/2026"
        y, m, d = iso.groups()
        pattern = rf"ngày\s+0?{int(d)}\s+tháng\s+0?{int(m)}\s+năm\s+{y}|\b0?{int(d)}/0?{int(m)}/{y}\b"
        return re.search(pattern, text, re.IGNORECASE) is not None
    return False


def evaluate(fixtures: Path = FIXTURES) -> dict:
    labels = route_labels(fixtures)
    ground_truth = json.loads((fixtures / "ground_truth.json").read_text(encoding="utf-8"))["files"]
    docs = []
    for name, meta in ground_truth.items():
        if meta.get("format", "").lower() != "pdf":
            continue
        path = fixtures / meta["relative_path"]
        result = extract_pdf_text(path.read_bytes())
        label = labels.get(_sha(path))
        text = "\n".join(p.text for p in result.pages if p.has_text_layer)
        row = {"file": name, "label": label, "outcome": result.outcome, "page_count": result.page_count,
               "ocr_pages": result.ocr_pages}
        if label:
            row["route_correct"] = result.outcome == EXPECTED_OUTCOME[label]
        if meta.get("total_pages") is not None:
            row["page_count_correct"] = result.page_count == meta["total_pages"]
        if label == "PDF_TEXT":
            values = {k: v for k, v in (meta.get("fields") or {}).items() if isinstance(v, str)}
            missing = [k for k, v in values.items() if not _found(v, text)]
            row.update(values_total=len(values), values_found=len(values) - len(missing), values_missing=missing)
        docs.append(row)

    routed = [d for d in docs if "route_correct" in d]
    paged = [d for d in docs if "page_count_correct" in d]
    return {
        "extractor_version": EXTRACTOR_VERSION,
        "routing": {"correct": sum(d["route_correct"] for d in routed), "total": len(routed)},
        "page_count": {"correct": sum(d["page_count_correct"] for d in paged), "total": len(paged)},
        "text_values": {"found": sum(d.get("values_found", 0) for d in docs),
                        "total": sum(d.get("values_total", 0) for d in docs)},
        "unlabeled": [d["file"] for d in docs if d["label"] is None],
        "documents": docs,
    }


def main() -> int:
    report = evaluate()
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        r, p, v = report["routing"], report["page_count"], report["text_values"]
        print(f"pdf-text-layer {report['extractor_version']}")
        print(f"Định tuyến text/OCR đúng: {r['correct']}/{r['total']}")
        print(f"Số trang đúng:            {p['correct']}/{p['total']}")
        print(f"Giá trị ground truth thấy trong chữ đọc được: {v['found']}/{v['total']}")
        if report["unlabeled"]:
            print("Không có nhãn định tuyến (bỏ qua phần định tuyến):", ", ".join(report["unlabeled"]))
        for d in report["documents"]:
            print(f"  {d['file']}: {d['outcome']} trang={d['page_count']} ocr={d['ocr_pages']}"
                  + (f" thiếu={d['values_missing']}" if d.get("values_missing") else ""))
    ok = (report["routing"]["correct"] == report["routing"]["total"]
          and report["page_count"]["correct"] == report["page_count"]["total"]
          and report["text_values"]["found"] == report["text_values"]["total"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
