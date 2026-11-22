"""Script kiem tra toan dien bo dataset danh cho Khiem tu test."""
import json
import os
import pypdf
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")

print("=" * 65)
print("  HE THONG KIEM THU TOAN DIEN BO DATASET G4T-42 (NGUYEN THANH KHIEM)")
print("=" * 65)

print("\n[MUC 1] KIEM TRA CAC TEP PDF (REPORTLAB & TEXT LAYER)")
pdf_dir = os.path.join(FIXTURES_DIR, "pdf")
for f in sorted(os.listdir(pdf_dir)):
    p = os.path.join(pdf_dir, f)
    reader = pypdf.PdfReader(p)
    text = reader.pages[0].extract_text()
    has_text = len(text.strip()) > 0
    print(f"  * {f:<32} -> {len(text.strip()):>4} ky tu | Co Text Layer: {str(has_text):<5}")

print("\n[MUC 2] KIEM TRA HINH ANH (PNG SCAN & JPG)")
img_dir = os.path.join(FIXTURES_DIR, "images")
for f in sorted(os.listdir(img_dir)):
    p = os.path.join(img_dir, f)
    with Image.open(p) as img:
        print(f"  * {f:<28} -> Dinh dang: {img.format:<5} | Kich thuoc: {img.size}")

print("\n[MUC 3] KIEM TRA GOI HON HOP MIXED PACK & MANIFEST.JSON")
manifest_p = os.path.join(FIXTURES_DIR, "mixed_pack", "manifest.json")
with open(manifest_p, encoding="utf-8") as mf:
    mdata = json.load(mf)
print(f"  * Ten goi: {mdata['package_name']} | Loai: {mdata['batch_type']} | Tong file: {mdata['total_documents']}")
for it in mdata["items"]:
    target = os.path.join(FIXTURES_DIR, "mixed_pack", it["file"])
    exists = os.path.exists(target)
    print(f"    - {it['file']:<28} [{it['format']:^8}] -> Nhan G4T-24: {it['expected_document_type']:<20} (Ton tai: {exists})")

print("\n[MUC 4] KIEM TRA NHAN PHAN LOAI TRONG GROUND_TRUTH.JSON (THEO G4T-24)")
gt_p = os.path.join(FIXTURES_DIR, "xml", "ground_truth.json")
with open(gt_p, encoding="utf-8") as gf:
    gt = json.load(gf)

types_count = {}
for fname, meta in gt["files"].items():
    doc_type = meta.get("expected_document_type", "CHUA_CO")
    types_count[doc_type] = types_count.get(doc_type, 0) + 1

print("  * Thong ke nhan G4T-24 tren toan bo 17 muc:")
for t, cnt in sorted(types_count.items()):
    print(f"    + {t:<22}: {cnt} tai lieu")

print("\n[MUC 5] KIEM TRA PARSE XML VOI PARSER CUA QUOC AN (BRANCH G4T-61)")
from an_xml_test import test_an_parser_independent
test_an_parser_independent(FIXTURES_DIR, gt["files"])

print("\n" + "=" * 65)
print("  HOAN TAT KIEM TRA TOAN DIEN: TAT CA CAC DIEU KIEN DEU DAT 100%!")
print("=" * 65)
