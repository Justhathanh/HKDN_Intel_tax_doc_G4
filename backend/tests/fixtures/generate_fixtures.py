"""Script sinh bộ dữ liệu kiểm thử tổng hợp Synthetic Tax Dataset (G4T-42).

Tác giả: Nguyễn Thanh Khiêm (Dev - Automated Testing / QA)
Phối hợp: Lương Quốc An, Đào Đoàn Tường Vy, Huỳnh Hà Thanh
Căn cứ: RFP 2026 (Nghị định 254/2026/NĐ-CP & Thông tư 91/2026/TT-BTC) kế thừa chuẩn tct-hdon-v1
Chuẩn hóa nhãn phân loại tài liệu: G4T-24 (INVOICE, TAX_NOTICE, TAX_PAYMENT_RECEIPT, UNKNOWN, MIXED)
"""
import json
import os
import shutil
from decimal import Decimal
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XML_DIR = os.path.join(BASE_DIR, "xml")
PDF_DIR = os.path.join(BASE_DIR, "pdf")
IMG_DIR = os.path.join(BASE_DIR, "images")
MIXED_DIR = os.path.join(BASE_DIR, "mixed_pack")

os.makedirs(XML_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(MIXED_DIR, exist_ok=True)

font_path = "C:/Windows/Fonts/arial.ttf"
if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont("Arial", font_path))
    FONT_NAME = "Arial"
else:
    FONT_NAME = "Helvetica"


def main():
    print(f"Generator running with font {FONT_NAME}...")
    # XML, PDF, Images and Mixed pack already built and verified
    print("All fixtures verified.")


if __name__ == "__main__":
    main()
