"""Script sinh toan bo du lieu kiem thu tong hop Synthetic Tax Dataset (G4T-42).

Tac gia: Nguyen Thanh Khiem (Dev - Automated Testing / QA)
Phu hop:
- G4T-42: Bo du lieu kiem thu tong hop & Ground Truth
- G4T-24: Nhan phan loai tai lieu (INVOICE, TAX_NOTICE, TAX_PAYMENT_RECEIPT, UNKNOWN, MIXED)
- G4T-82, G4T-84: Tuan thu du lieu gia lap 100%, co watermark "DU LIEU GIA LAP", khong dia chi/MST that.
- RFP 2026: Nghi dinh 254/2026/ND-CP va Thong tu 91/2026/TT-BTC ke thua chuan tct-hdon-v1.
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

# Register Vietnamese font
font_path = "C:/Windows/Fonts/arial.ttf"
if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont("Arial", font_path))
    FONT_NAME = "Arial"
else:
    FONT_NAME = "Helvetica"


def draw_pdf_watermark(c, width, height):
    """Ve watermark DU LIEU GIA LAP cheo 45 do va footer."""
    c.saveState()
    c.setFont(FONT_NAME, 42)
    c.setFillColorRGB(0.85, 0.85, 0.85)  # gray watermark
    c.translate(width / 2.0, height / 2.0)
    c.rotate(45)
    c.drawCentredString(0, 0, "DỮ LIỆU GIẢ LẬP - TEST ONLY")
    c.drawCentredString(0, -50, "KHÔNG CÓ GIÁ TRỊ PHÁP LÝ")
    c.restoreState()

    c.saveState()
    c.setFont(FONT_NAME, 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(
        width / 2.0, 15,
        "--- DỮ LIỆU GIẢ LẬP PHỤC VỤ KIỂM THỬ DỰ ÁN THTAX (G4T-42) - KHÔNG PHẢI CHỨNG TỪ THẬT ---"
    )
    c.restoreState()


# ==========================================
# 1. GENERATE 7 INDEPENDENT XML FIXTURES
# (100% Synthetic names, MSTs, and addresses)
# ==========================================

xml_01 = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hóa đơn giá trị gia tăng</THDon>
            <KHMSHDon>1</KHMSHDon>
            <KHHDon>1C26TNN</KHHDon>
            <SHDon>0000045</SHDon>
            <NLap>2026-03-15</NLap>
            <DVTTe>VND</DVTTe>
            <TGia>1</TGia>
            <HTTToan>TM/CK</HTTToan>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN</Ten>
                <MST>0109988776</MST>
                <DChi>Số 123 Đường Giả Định Alpha, Phường Thử Nghiệm 1, Quận Kịch Bản, TP. Hà Nội</DChi>
                <SDThoai>02499991234</SDThoai>
            </NBan>
            <NMua>
                <Ten>CÔNG TY TNHH PHẦN MỀM MẪU THỬ THĂNG LONG</Ten>
                <MST>0108877665</MST>
                <DChi>Số 45 Phố Kịch Bản Thử Nghiệm, Phường Giả Định, Quận Khảo Sát, TP. Hà Nội</DChi>
            </NMua>
            <TToan>
                <TgTCThue>45000000</TgTCThue>
                <TgTThue>4500000</TgTThue>
                <TgTTTBSo>49500000</TgTTTBSo>
                <TgTTTBChu>Bốn mươi chín triệu năm trăm nghìn đồng</TgTTTBChu>
                <THTTLTSuat>
                    <LTSuat>
                        <TSuat>10%</TSuat>
                        <ThTien>45000000</ThTien>
                        <TThue>4500000</TThue>
                    </LTSuat>
                </THTTLTSuat>
            </TToan>
        </NDHDon>
    </DLHDon>
    <MCCQT>TCT010998877620261C26TNN0000045</MCCQT>
</HDon>"""

xml_02 = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hóa đơn giá trị gia tăng</THDon>
            <KHMSHDon>1</KHMSHDon>
            <KHHDon>1C26MHK</KHHDon>
            <SHDon>0001289</SHDon>
            <NLap>2026-04-20</NLap>
            <DVTTe>VND</DVTTe>
            <TGia>1</TGia>
            <HTTToan>Chuyển khoản</HTTToan>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>TẬP ĐOÀN CÔNG NGHIỆP THỬ NGHIỆM NAM PHÁT</Ten>
                <MST>0318991122</MST>
                <DChi>Số 456 Đại Lộ Kịch Bản Beta, Phường Thử Nghiệm 2, Quận Giả Lập, TP. Hồ Chí Minh</DChi>
            </NBan>
            <NMua>
                <Ten>CÔNG TY CỔ PHẦN XÂY DỰNG MẪU THỬ KHANG ĐIỀN</Ten>
                <MST>0317665544</MST>
                <DChi>Số 78 Đường Thử Nghiệm Tân Tạo, Phường Giả Lập 2, Quận Khảo Sát, TP. Hồ Chí Minh</DChi>
            </NMua>
            <TToan>
                <TgTCThue>50000000</TgTCThue>
                <TgTThue>4400000</TgTThue>
                <TgTTTBSo>54400000</TgTTTBSo>
                <TgTTTBChu>Năm mươi tư triệu bốn trăm nghìn đồng</TgTTTBChu>
                <THTTLTSuat>
                    <LTSuat>
                        <TSuat>8%</TSuat>
                        <ThTien>30000000</ThTien>
                        <TThue>2400000</TThue>
                    </LTSuat>
                    <LTSuat>
                        <TSuat>10%</TSuat>
                        <ThTien>20000000</ThTien>
                        <TThue>2000000</TThue>
                    </LTSuat>
                </THTTLTSuat>
            </TToan>
        </NDHDon>
    </DLHDon>
    <MCCQT>TCT031899112220261C26MHK0001289</MCCQT>
</HDon>"""

xml_03 = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hóa đơn giá trị gia tăng dịch vụ xuất khẩu</THDon>
            <KHMSHDon>1</KHMSHDon>
            <KHHDon>1C26TDA</KHHDon>
            <SHDon>0000305</SHDon>
            <NLap>2026-05-18</NLap>
            <DVTTe>USD</DVTTe>
            <TGia>25450.00</TGia>
            <HTTToan>Chuyển khoản quốc tế T/T</HTTToan>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>CÔNG TY TNHH XUẤT NHẬP KHẨU THỬ NGHIỆM ĐẠI TÂY DƯƠNG</Ten>
                <MST>0401882233</MST>
                <DChi>Số 789 Đường Cảng Thử Nghiệm Gamma, Phường Giả Định 3, Quận Kịch Bản, TP. Đà Nẵng</DChi>
            </NBan>
            <NMua>
                <Ten>SYNTHETIC GLOBAL LOGISTICS PTE. LTD.</Ten>
                <DChi>Tòa nhà Giả Lập Alpha, Số 99 Đường Thử Nghiệm, Khu Tài Chính Giả Định, Singapore 999999</DChi>
            </NMua>
            <TToan>
                <TgTCThue>12500.00</TgTCThue>
                <TgTThue>0.00</TgTThue>
                <TgTTTBSo>12500.00</TgTTTBSo>
                <TgTTTBChu>Twelve thousand five hundred US Dollars</TgTTTBChu>
                <THTTLTSuat>
                    <LTSuat>
                        <TSuat>0%</TSuat>
                        <ThTien>12500.00</ThTien>
                        <TThue>0.00</TThue>
                    </LTSuat>
                </THTTLTSuat>
            </TToan>
        </NDHDon>
    </DLHDon>
    <MCCQT>TCT040188223320261C26TDA0000305</MCCQT>
</HDon>"""

xml_04 = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hóa đơn giá trị gia tăng</THDon>
            <KHMSHDon>1</KHMSHDon>
            <KHHDon>1C26TDN</KHHDon>
            <SHDon>0000888</SHDon>
            <NLap>2026-06-10</NLap>
            <DVTTe>VND</DVTTe>
            <TGia>1</TGia>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>CHI NHÁNH CÔNG TY VIỄN THÔNG GIẢ LẬP SAO MAI</Ten>
                <MST>0105667788-002</MST>
                <DChi>Số 88 Đại Lộ Thử Nghiệm 3, Phường Giả Định 3, Quận Kịch Bản, TP. Đà Nẵng</DChi>
            </NBan>
            <NMua>
                <Ten>CÔNG TY TNHH KHÁCH SẠN MẪU THỬ BIỂN ĐÔNG</Ten>
                <MST>0402113355</MST>
                <DChi>Số 12 Đường Ven Biển Giả Định, Quận Thử Nghiệm, TP. Đà Nẵng</DChi>
            </NMua>
            <TToan>
                <TgTCThue>18000000</TgTCThue>
                <TgTThue>1800000</TgTThue>
                <TgTTTBSo>19800000</TgTTTBSo>
                <TgTTTBChu>Mười chín triệu tám trăm nghìn đồng</TgTTTBChu>
                <THTTLTSuat>
                    <LTSuat>
                        <TSuat>10%</TSuat>
                        <ThTien>18000000</ThTien>
                        <TThue>1800000</TThue>
                    </LTSuat>
                </THTTLTSuat>
            </TToan>
        </NDHDon>
    </DLHDon>
    <MCCQT>TCT010566778800220261C26TDN0000888</MCCQT>
</HDon>"""

xml_05 = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hóa đơn giá trị gia tăng thay thế</THDon>
            <KHMSHDon>1</KHMSHDon>
            <KHHDon>1C26THG</KHHDon>
            <SHDon>0002560</SHDon>
            <NLap>2026-07-25</NLap>
            <DVTTe>VND</DVTTe>
            <TGia>1</TGia>
            <TTHDLQuan>
                <TCHDon>1</TCHDon>
                <KHMSHDCLQuan>1</KHMSHDCLQuan>
                <KHHDCLQuan>1C26THG</KHHDCLQuan>
                <SHDCLQuan>0002100</SHDCLQuan>
                <NLHDCLQuan>2026-07-10</NLHDCLQuan>
            </TTHDLQuan>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>CÔNG TY TNHH PHẦN MỀM THỬ NGHIỆM HOÀNG GIA</Ten>
                <MST>0201993344</MST>
                <DChi>Số 101 Phố Thử Nghiệm Delta, Phường Giả Định 4, Quận Kịch Bản, TP. Hải Phòng</DChi>
            </NBan>
            <NMua>
                <Ten>CÔNG TY CỔ PHẦN LOGISTICS MẪU THỬ HẢI PHÒNG</Ten>
                <MST>0201889900</MST>
                <DChi>Số 15 Đường Cảng Giả Định, Quận Thử Nghiệm, TP. Hải Phòng</DChi>
            </NMua>
            <TToan>
                <TgTCThue>35000000</TgTCThue>
                <TgTThue>3500000</TgTThue>
                <TgTTTBSo>38500000</TgTTTBSo>
                <TgTTTBChu>Ba mươi tám triệu năm trăm nghìn đồng</TgTTTBChu>
                <THTTLTSuat>
                    <LTSuat>
                        <TSuat>10%</TSuat>
                        <ThTien>35000000</ThTien>
                        <TThue>3500000</TThue>
                    </LTSuat>
                </THTTLTSuat>
            </TToan>
        </NDHDon>
    </DLHDon>
    <MCCQT>TCT020199334420261C26THG0002560</MCCQT>
</HDon>"""

xml_06 = """<?xml version="1.0" encoding="UTF-8"?>
<TDiep>
    <TTChung>
        <PBan>2.0.0</PBan>
        <MTDiep>TCT2026081599887701</MTDiep>
        <MSNTNhan>TBT2026081501</MSNTNhan>
    </TTChung>
    <DLieu>
        <HDon>
            <DLHDon>
                <TTChung>
                    <PBan>2.0.0</PBan>
                    <THDon>Hóa đơn giá trị gia tăng</THDon>
                    <KHMSHDon>1</KHMSHDon>
                    <KHHDon>1C26TBV</KHHDon>
                    <SHDon>0000789</SHDon>
                    <NLap>2026-08-15</NLap>
                    <DVTTe>VND</DVTTe>
                    <TGia>1</TGia>
                </TTChung>
                <NDHDon>
                    <NBan>
                        <Ten>CÔNG TY CP THIẾT BỊ Y TẾ GIẢ LẬP BÁCH VIỆT</Ten>
                        <MST>0107778899</MST>
                        <DChi>Số 202 Đường Giả Lập Epsilon, Phường Thử Nghiệm 5, Quận Kịch Bản, TP. Hà Nội</DChi>
                    </NBan>
                    <NMua>
                        <Ten>BỆNH VIỆN ĐA KHOA MẪU THỬ BẠCH MAI</Ten>
                        <MST>0106554433</MST>
                        <DChi>Số 100 Phố Thử Nghiệm Đồng Tâm, Quận Giả Định, TP. Hà Nội</DChi>
                    </NMua>
                    <TToan>
                        <TgTCThue>60000000</TgTCThue>
                        <TgTThue>3000000</TgTThue>
                        <TgTTTBSo>63000000</TgTTTBSo>
                        <TgTTTBChu>Sáu mươi ba triệu đồng</TgTTTBChu>
                        <THTTLTSuat>
                            <LTSuat>
                                <TSuat>5%</TSuat>
                                <ThTien>60000000</ThTien>
                                <TThue>3000000</TThue>
                            </LTSuat>
                        </THTTLTSuat>
                    </TToan>
                </NDHDon>
            </DLHDon>
            <MCCQT>TCT010777889920261C26TBV0000789</MCCQT>
        </HDon>
    </DLieu>
</TDiep>"""

xml_07 = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <PBan>2.0.0</PBan>
            <THDon>Hóa đơn bán hàng</THDon>
            <KHMSHDon>2</KHMSHDon>
            <KHHDon>2C26TMT</KHHDon>
            <SHDon>0000150</SHDon>
            <NLap>2026-09-02</NLap>
            <DVTTe>VND</DVTTe>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>HỘ KINH DOANH NÔNG SẢN THỬ NGHIỆM MIỀN TÂY</Ten>
                <MST>1801665544</MST>
            </NBan>
            <NMua>
                <Ten>NGUYỄN VĂN AN (KHÁCH HÀNG GIẢ ĐỊNH)</Ten>
            </NMua>
            <TToan>
                <TgTTTBSo>8500000</TgTTTBSo>
            </TToan>
        </NDHDon>
    </DLHDon>
</HDon>"""

xml_malformed = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <TTChung>
            <SHDon>0000099
            <!-- Lỗi cú pháp: thiếu thẻ đóng SHDon và TTChung -->
    </DLHDon>
</HDon>"""

xml_map = {
    "tct_hdon_01_vat10_standard.xml": xml_01,
    "tct_hdon_02_vat8_multi_rate.xml": xml_02,
    "tct_hdon_03_vat0_export_foreign.xml": xml_03,
    "tct_hdon_04_outgoing_branch.xml": xml_04,
    "tct_hdon_05_replacement.xml": xml_05,
    "tct_hdon_06_wrapped_transmission.xml": xml_06,
    "tct_hdon_07_missing_optional.xml": xml_07,
    "malformed_invoice.xml": xml_malformed,
}

for fname, content in xml_map.items():
    with open(os.path.join(XML_DIR, fname), "w", encoding="utf-8") as f:
        f.write(content.strip())
print(f"Generated {len(xml_map)} XML fixtures.")


# ==========================================
# 2. GENERATE PDF FIXTURES WITH REPORTLAB & WATERMARK
# ==========================================

# A. Digital Invoice PDF
def make_digital_pdf(output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setTitle("Hóa đơn giá trị gia tăng điện tử giả lập")
    draw_pdf_watermark(c, width, height)

    c.setFont(FONT_NAME, 16)
    c.drawCentredString(width / 2.0, height - 50, "HÓA ĐƠN GIÁ TRỊ GIA TĂNG")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2.0, height - 70, "(Bản thể hiện dữ liệu giả lập phục vụ kiểm thử)")
    c.drawCentredString(width / 2.0, height - 85, "Ngày 12 tháng 04 năm 2026")

    c.drawString(400, height - 105, "Ký hiệu: 1C26TAA")
    c.drawString(400, height - 120, "Số: 00000088")

    c.setLineWidth(0.5)
    c.line(50, height - 130, width - 50, height - 130)

    y = height - 145
    c.drawString(50, y, "Đơn vị bán hàng: CÔNG TY CỔ PHẦN CÔNG NGHỆ THỬ NGHIỆM Á CHÂU")
    y -= 18
    c.drawString(50, y, "Mã số thuế: 0108998877")
    y -= 18
    c.drawString(50, y, "Địa chỉ: Số 18 Phố Thử Nghiệm Kịch Bản, Phường Giả Định, TP. Hà Nội")

    y -= 25
    c.line(50, y + 10, width - 50, y + 10)
    c.drawString(50, y, "Tên đơn vị mua hàng: CÔNG TY TNHH THƯƠNG MẠI MẪU THỬ AN BÌNH")
    y -= 18
    c.drawString(50, y, "Mã số thuế: 0317654321")
    y -= 18
    c.drawString(50, y, "Địa chỉ: Số 123 Đường Giả Lập Mẫu, Phường Kịch Bản 1, TP. Hồ Chí Minh")
    y -= 18
    c.drawString(50, y, "Hình thức thanh toán: Chuyển khoản")

    y -= 25
    c.line(50, y + 10, width - 50, y + 10)
    c.drawString(55, y, "STT")
    c.drawString(90, y, "Tên hàng hóa, dịch vụ")
    c.drawString(300, y, "ĐVT")
    c.drawString(350, y, "Số lượng")
    c.drawString(420, y, "Đơn giá")
    c.drawString(490, y, "Thành tiền")

    y -= 8
    c.line(50, y, width - 50, y)

    y -= 18
    c.drawString(60, y, "1")
    c.drawString(90, y, "Dịch vụ phần mềm thử nghiệm ERP Alpha")
    c.drawString(300, y, "Gói")
    c.drawString(365, y, "1")
    c.drawString(410, y, "50.000.000")
    c.drawString(485, y, "50.000.000")

    y -= 25
    c.line(50, y + 10, width - 50, y + 10)
    c.drawString(50, y, "Cộng tiền hàng: 50.000.000 VND")
    y -= 18
    c.drawString(50, y, "Thuế suất GTGT: 10%        Tiền thuế GTGT: 5.000.000 VND")
    y -= 18
    c.setFont(FONT_NAME, 11)
    c.drawString(50, y, "Tổng cộng tiền thanh toán: 55.000.000 VND")
    y -= 18
    c.setFont(FONT_NAME, 10)
    c.drawString(50, y, "Số tiền viết bằng chữ: Năm mươi lăm triệu đồng chẵn.")

    y -= 40
    c.drawString(90, y, "NGƯỜI MUA HÀNG (GIẢ LẬP)")
    c.drawString(380, y, "NGƯỜI BÁN HÀNG (GIẢ LẬP)")
    c.save()


make_digital_pdf(os.path.join(PDF_DIR, "invoice_digital_text_layer.pdf"))

# B. Non-Tax Contract PDF (label UNKNOWN)
def make_contract_pdf(output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setTitle("Hợp đồng dịch vụ tư vấn doanh nghiệp giả lập")
    draw_pdf_watermark(c, width, height)

    c.setFont(FONT_NAME, 12)
    c.drawCentredString(width / 2.0, height - 50, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    c.drawCentredString(width / 2.0, height - 68, "Độc lập - Tự do - Hạnh phúc")
    c.setLineWidth(0.5)
    c.line(width / 2.0 - 70, height - 74, width / 2.0 + 70, height - 74)

    c.setFont(FONT_NAME, 15)
    c.drawCentredString(width / 2.0, height - 105, "HỢP ĐỒNG KINH TẾ DỊCH VỤ (MẪU THỬ)")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2.0, height - 122, "Số: 45/2026/HĐKT-GIẢ LẬP")

    y = height - 160
    c.drawString(50, y, "Hôm nay, ngày 05 tháng 02 năm 2026, chúng tôi gồm có các bên giả định:")
    y -= 25
    c.setFont(FONT_NAME, 11)
    c.drawString(50, y, "BÊN A: CÔNG TY CỔ PHẦN ĐẦU TƯ MẪU THỬ BẮC HÀ")
    c.setFont(FONT_NAME, 10)
    y -= 18
    c.drawString(50, y, "Địa chỉ: Số 10 Đường Giả Định Alpha, Quận Kịch Bản, TP. Hà Nội")

    y -= 25
    c.setFont(FONT_NAME, 11)
    c.drawString(50, y, "BÊN B: CÔNG TY TNHH TƯ VẤN QUẢN TRỊ THỬ NGHIỆM VIỆT")
    c.setFont(FONT_NAME, 10)
    y -= 18
    c.drawString(50, y, "Địa chỉ: Tòa nhà Kịch Bản Beta, Đường Thử Nghiệm, TP. Hà Nội")

    y -= 30
    c.drawString(50, y, "Điều 1: Nội dung dịch vụ chuyển đổi số doanh nghiệp giả định.")
    y -= 18
    c.drawString(50, y, "Điều 2: Thời hạn thực hiện là 06 tháng kể từ ngày ký.")
    y -= 18
    c.drawString(50, y, "Điều 3: Phí dịch vụ là 120.000.000 VNĐ (Một trăm hai mươi triệu đồng).")

    y -= 50
    c.drawString(100, y, "ĐẠI DIỆN BÊN A")
    c.drawString(380, y, "ĐẠI DIỆN BÊN B")
    c.save()


make_contract_pdf(os.path.join(PDF_DIR, "non_tax_contract.pdf"))

# C. Tax Notice PDF (label TAX_NOTICE) - Fully synthetic authority and address
def make_tax_notice_pdf(output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setTitle("Thông báo nộp tiền thuế mẫu giả lập")
    draw_pdf_watermark(c, width, height)

    c.setFont(FONT_NAME, 10)
    c.drawString(50, height - 50, "CỤC THUẾ THỬ NGHIỆM KHU VỰC 1")
    c.drawString(50, height - 65, "CHI CỤC THUẾ KHU VỰC GIẢ ĐỊNH ALPHA")
    c.drawString(50, height - 80, "Số: 14285/TB-CCT-GIẢ LẬP")

    c.drawRightString(width - 50, height - 50, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    c.drawRightString(width - 50, height - 65, "Độc lập - Tự do - Hạnh phúc")
    c.drawRightString(width - 50, height - 80, "Ngày 10 tháng 05 năm 2026")

    c.setFont(FONT_NAME, 14)
    c.drawCentredString(width / 2.0, height - 120, "THÔNG BÁO THUẾ (DỮ LIỆU GIẢ LẬP)")
    c.setFont(FONT_NAME, 11)
    c.drawCentredString(width / 2.0, height - 140, "Về việc nộp tiền thuế phát sinh kỳ Quý I/2026")

    c.setFont(FONT_NAME, 10)
    y = height - 180
    c.drawString(50, y, "Kính gửi: CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN")
    y -= 18
    c.drawString(50, y, "Mã số thuế: 0109988776")
    y -= 18
    c.drawString(50, y, "Địa chỉ: Số 123 Đường Giả Định Alpha, Quận Kịch Bản, TP. Hà Nội")

    y -= 25
    c.drawString(50, y, "Chi cục Thuế Khu Vực Giả Định Alpha thông báo số tiền thuế phải nộp:")
    y -= 20
    c.drawString(70, y, "1. Thuế Giá trị gia tăng (Tiểu mục 1701): 4.500.000 đồng.")
    y -= 18
    c.drawString(70, y, "2. Thuế Thu nhập doanh nghiệp (Tiểu mục 1052): 12.000.000 đồng.")
    y -= 20
    c.setFont(FONT_NAME, 11)
    c.drawString(70, y, "Tổng số tiền phải nộp vào NSNN: 16.500.000 đồng.")
    c.setFont(FONT_NAME, 10)
    y -= 18
    c.drawString(70, y, "(Bằng chữ: Mười sáu triệu năm trăm nghìn đồng chẵn).")

    y -= 30
    c.drawString(50, y, "Tài khoản thu NSNN số 7111 mở tại Kho bạc Nhà nước Giả Định.")
    y -= 45
    c.drawString(380, y, "CHI CỤC TRƯỞNG (GIẢ LẬP)")
    c.save()


make_tax_notice_pdf(os.path.join(PDF_DIR, "tax_notice_cqt.pdf"))

# D. Tax Payment Receipt PDF (label TAX_PAYMENT_RECEIPT)
def make_tax_payment_receipt_pdf(output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setTitle("Giấy nộp tiền vào ngân sách nhà nước mẫu giả lập")
    draw_pdf_watermark(c, width, height)

    c.setFont(FONT_NAME, 9)
    c.drawRightString(width - 50, height - 40, "Mẫu số: C1-02/NS (GIẢ LẬP)")
    c.drawRightString(width - 50, height - 52, "Mã chứng từ: GNT-2026-GIẢ LẬP-01")

    c.setFont(FONT_NAME, 14)
    c.drawCentredString(width / 2.0, height - 80, "GIẤY NỘP TIỀN VÀO NGÂN SÁCH NHÀ NƯỚC")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2.0, height - 98, "(DỮ LIỆU MẪU KIỂM THỬ THTAX) - Loại tiền: VND")

    y = height - 130
    c.drawString(50, y, "Người nộp thuế: CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN")
    y -= 18
    c.drawString(50, y, "Mã số thuế: 0109988776")
    y -= 18
    c.drawString(50, y, "Địa chỉ: Số 123 Đường Giả Định Alpha, Quận Kịch Bản, TP. Hà Nội")

    y -= 25
    c.drawString(50, y, "Ngân hàng phục vụ: Ngân hàng TMCP Thử Nghiệm Việt Nam - CN Hà Nội")
    y -= 18
    c.drawString(50, y, "Nộp vào Ngân sách Nhà nước qua KBNN: Kho bạc Nhà nước Giả Định Alpha")
    y -= 18
    c.drawString(50, y, "Cơ quan quản lý thu: Chi cục Thuế Khu Vực Giả Định Alpha")

    y -= 25
    c.drawString(50, y, "Chi tiết khoản nộp NSNN:")
    y -= 18
    c.drawString(70, y, "+ Nội dung: Nộp thuế GTGT Quý I/2026 theo Thông báo 14285/TB-CCT")
    y -= 18
    c.drawString(70, y, "+ Số tiền nộp: 4.500.000 VND (Bốn triệu năm trăm nghìn đồng chẵn)")

    y -= 50
    c.drawString(70, y, "NGƯỜI NỘP TIỀN")
    c.drawString(240, y, "NGÂN HÀNG TRÍCH NỢ")
    c.drawString(410, y, "KHO BẠC NHÀ NƯỚC")
    c.save()


make_tax_payment_receipt_pdf(os.path.join(PDF_DIR, "tax_payment_receipt_nsnn.pdf"))

# E. Multi-page Mixed Document PDF (Single file containing multiple doc types -> label MIXED for G4T-24)
def make_mixed_multipage_pdf(output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setTitle("Tập tài liệu thuế hỗn hợp đa chứng từ (MIXED)")

    # Trang 1: Hóa đơn GTGT
    draw_pdf_watermark(c, width, height)
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(width / 2.0, height - 50, "CHỨNG TỪ 1: HÓA ĐƠN GIÁ TRỊ GIA TĂNG")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2.0, height - 70, "Ký hiệu: 1C26TNN | Số: 0000045 | Ngày 15/03/2026")
    c.drawString(50, height - 120, "Bên bán: CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN - MST: 0109988776")
    c.drawString(50, height - 140, "Bên mua: CÔNG TY TNHH PHẦN MỀM MẪU THỬ THĂNG LONG - MST: 0108877665")
    c.drawString(50, height - 160, "Tổng cộng thanh toán: 49.500.000 VND (Thuế GTGT 10%: 4.500.000 VND)")
    c.showPage()

    # Trang 2: Thông báo thuế
    draw_pdf_watermark(c, width, height)
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(width / 2.0, height - 50, "CHỨNG TỪ 2: THÔNG BÁO NỘP TIỀN THUẾ CỦA CƠ QUAN THUẾ")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2.0, height - 70, "Số thông báo: 14285/TB-CCT-GIẢ LẬP | Ngày: 10/05/2026")
    c.drawString(50, height - 120, "Cơ quan phát hành: Chi cục Thuế Khu Vực Giả Định Alpha")
    c.drawString(50, height - 140, "Người nộp thuế: CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN - MST: 0109988776")
    c.drawString(50, height - 160, "Số tiền thuế GTGT phải nộp: 4.500.000 VND")
    c.showPage()

    # Trang 3: Giấy nộp tiền NSNN
    draw_pdf_watermark(c, width, height)
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(width / 2.0, height - 50, "CHỨNG TỪ 3: GIẤY NỘP TIỀN VÀO NGÂN SÁCH NHÀ NƯỚC")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2.0, height - 70, "Số chứng từ: GNT-2026-GIẢ LẬP-01 | Mẫu C1-02/NS")
    c.drawString(50, height - 120, "Đơn vị nộp: CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN - MST: 0109988776")
    c.drawString(50, height - 140, "Kho bạc tiếp nhận: Kho bạc Nhà nước Giả Định Alpha")
    c.drawString(50, height - 160, "Số tiền nộp NSNN: 4.500.000 VND")
    c.save()


make_mixed_multipage_pdf(os.path.join(PDF_DIR, "mixed_documents_multi_page.pdf"))


# ==========================================
# 3. GENERATE IMAGES & SCANNED PDF (NO TEXT)
# ==========================================

def create_invoice_image(mode="clean"):
    img = Image.new("RGB", (900, 1200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        f_large = ImageFont.truetype("arial.ttf", 28)
        f_med = ImageFont.truetype("arial.ttf", 18)
        f_small = ImageFont.truetype("arial.ttf", 15)
        f_wm = ImageFont.truetype("arial.ttf", 40)
    except Exception:
        f_large = ImageFont.load_default()
        f_med = ImageFont.load_default()
        f_small = ImageFont.load_default()
        f_wm = ImageFont.load_default()

    # Watermark text on image
    draw.text((150, 500), "DỮ LIỆU GIẢ LẬP - TEST ONLY", fill=(225, 225, 225), font=f_wm)

    draw.text((250, 40), "HOA DON GIA TRI GIA TANG", fill=(0, 0, 0), font=f_large)
    draw.text((310, 80), "(BAN THE HIEN HOA DON SCAN GIA LAP)", fill=(80, 80, 80), font=f_small)
    draw.text((340, 105), "Ngay 18 thang 05 nam 2026", fill=(50, 50, 50), font=f_small)

    draw.text((620, 130), "Ky hieu: 1C26TDA", fill=(0, 0, 0), font=f_med)
    draw.text((620, 155), "So: 0000305", fill=(0, 0, 0), font=f_med)

    draw.line([(50, 190), (850, 190)], fill=(0, 0, 0), width=2)
    draw.text((50, 210), "Don vi ban: CONG TY TNHH XNK THU NGHIEM DAI TAY DUONG", fill=(0, 0, 0), font=f_med)
    draw.text((50, 240), "Ma so thue (MST): 0401882233", fill=(0, 0, 0), font=f_med)
    draw.text((50, 270), "Dia chi: So 789 Duong Cang Thu Nghiem, Quan Kich Ban, TP Da Nang", fill=(0, 0, 0), font=f_small)

    draw.line([(50, 310), (850, 310)], fill=(120, 120, 120), width=1)
    draw.text((50, 330), "Don vi mua: CONG TY CP DAU TU KICH BAN SAO BIEN", fill=(0, 0, 0), font=f_med)
    draw.text((50, 360), "Ma so thue (MST): 0402998877", fill=(0, 0, 0), font=f_med)
    draw.text((50, 390), "Dia chi: So 250 Duong Thu Nghiem, Quan Gia Lap, TP Da Nang", fill=(0, 0, 0), font=f_small)

    draw.line([(50, 430), (850, 430)], fill=(0, 0, 0), width=2)
    draw.text((60, 445), "STT", fill=(0, 0, 0), font=f_small)
    draw.text((120, 445), "Ten hang hoa, dich vu", fill=(0, 0, 0), font=f_small)
    draw.text((540, 445), "So luong", fill=(0, 0, 0), font=f_small)
    draw.text((640, 445), "Don gia", fill=(0, 0, 0), font=f_small)
    draw.text((740, 445), "Thanh tien", fill=(0, 0, 0), font=f_small)

    draw.line([(50, 475), (850, 475)], fill=(0, 0, 0), width=1)
    draw.text((65, 495), "1", fill=(0, 0, 0), font=f_small)
    draw.text((120, 495), "Dich vu van chuyen logistics mo phong", fill=(0, 0, 0), font=f_small)
    draw.text((560, 495), "2", fill=(0, 0, 0), font=f_small)
    draw.text((630, 495), "10.000.000", fill=(0, 0, 0), font=f_small)
    draw.text((730, 495), "20.000.000", fill=(0, 0, 0), font=f_small)

    draw.line([(50, 540), (850, 540)], fill=(0, 0, 0), width=2)
    draw.text((50, 560), "Cong tien hang: 20.000.000 VND", fill=(0, 0, 0), font=f_med)
    draw.text((50, 595), "Thue suat GTGT: 10%       Tien thue GTGT: 2.000.000 VND", fill=(0, 0, 0), font=f_med)
    draw.text((50, 630), "Tong tien thanh toan: 22.000.000 VND", fill=(0, 0, 0), font=f_large)
    draw.text((50, 670), "So tien viet bang chu: Hai muoi hai trieu dong chan.", fill=(0, 0, 0), font=f_small)

    if mode == "blurred":
        img = img.filter(ImageFilter.GaussianBlur(radius=2.5))

    return img


img_clean = create_invoice_image("clean")
img_clean_path = os.path.join(IMG_DIR, "invoice_scan_clean.png")
img_clean.save(img_clean_path)

img_blurred = create_invoice_image("blurred")
img_blurred.save(os.path.join(IMG_DIR, "invoice_scan_blurred.png"))

img_jpg = create_invoice_image("clean")
img_jpg.save(os.path.join(IMG_DIR, "invoice_vat10_retail.jpg"), "JPEG", quality=90)

# Scanned PDF without text layer (only draws image)
c_scan = canvas.Canvas(os.path.join(PDF_DIR, "invoice_scanned_no_text.pdf"), pagesize=A4)
w_a4, h_a4 = A4
c_scan.drawImage(img_clean_path, 0, 0, width=w_a4, height=h_a4)
c_scan.save()

# ==========================================
# 4. GENERATE MIXED PACK (BATCH REPOSITORY)
# ==========================================
shutil.copy(os.path.join(XML_DIR, "tct_hdon_01_vat10_standard.xml"), os.path.join(MIXED_DIR, "01_invoice_vat10.xml"))
shutil.copy(os.path.join(PDF_DIR, "invoice_digital_text_layer.pdf"), os.path.join(MIXED_DIR, "02_invoice_digital.pdf"))
shutil.copy(os.path.join(PDF_DIR, "invoice_scanned_no_text.pdf"), os.path.join(MIXED_DIR, "03_invoice_scanned.pdf"))
shutil.copy(os.path.join(IMG_DIR, "invoice_vat10_retail.jpg"), os.path.join(MIXED_DIR, "04_retail_receipt.jpg"))
shutil.copy(os.path.join(PDF_DIR, "non_tax_contract.pdf"), os.path.join(MIXED_DIR, "05_commercial_contract.pdf"))
shutil.copy(os.path.join(PDF_DIR, "tax_notice_cqt.pdf"), os.path.join(MIXED_DIR, "06_tax_notice.pdf"))
shutil.copy(os.path.join(PDF_DIR, "tax_payment_receipt_nsnn.pdf"), os.path.join(MIXED_DIR, "07_tax_payment.pdf"))

manifest = {
    "package_name": "mixed_tax_batch_01",
    "batch_type": "MIXED",
    "description": "Lô hồ sơ đa định dạng (Batch) gồm 7 tài liệu riêng biệt phục vụ kiểm thử xử lý hàng đợi G4T-71",
    "total_documents": 7,
    "items": [
        {"file": "01_invoice_vat10.xml", "format": "XML", "expected_document_type": "INVOICE"},
        {"file": "02_invoice_digital.pdf", "format": "PDF_TEXT", "expected_document_type": "INVOICE"},
        {"file": "03_invoice_scanned.pdf", "format": "PDF_SCAN", "expected_document_type": "INVOICE"},
        {"file": "04_retail_receipt.jpg", "format": "JPG", "expected_document_type": "INVOICE"},
        {"file": "05_commercial_contract.pdf", "format": "PDF_TEXT", "expected_document_type": "UNKNOWN"},
        {"file": "06_tax_notice.pdf", "format": "PDF_TEXT", "expected_document_type": "TAX_NOTICE"},
        {"file": "07_tax_payment.pdf", "format": "PDF_TEXT", "expected_document_type": "TAX_PAYMENT_RECEIPT"},
    ],
}

with open(os.path.join(MIXED_DIR, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

# ==========================================
# 5. GENERATE SINGLE CANONICAL GROUND TRUTH
# (Saved at fixtures/ground_truth.json)
# ==========================================

ground_truth = {
    "version": "3.1.0",
    "description": "Ground Truth đối soát toàn diện cho bộ dữ liệu Synthetic Tax Dataset (G4T-42). Tuân thủ nguyên tắc dữ liệu giả lập 100% không MST/địa chỉ thật, có watermark, chuẩn hóa nhãn theo G4T-24.",
    "legal_basis": "RFP 2026 - Nghị định 254/2026/NĐ-CP & Thông tư 91/2026/TT-BTC",
    "classification_standard": "G4T-24 (INVOICE, TAX_NOTICE, TAX_PAYMENT_RECEIPT, UNKNOWN, MIXED)",
    "default_client_tax_id": "0108877665",
    "files": {
        "tct_hdon_01_vat10_standard.xml": {
            "relative_path": "xml/tct_hdon_01_vat10_standard.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn GTGT 10% tiêu chuẩn, độc lập với dữ liệu dev",
            "client_tax_id": "0108877665",
            "expected_direction": "incoming",
            "schema_passed": True,
            "fields": {
                "invoice_form": "1",
                "invoice_series": "1C26TNN",
                "invoice_number": "0000045",
                "issue_date": "2026-03-15",
                "currency": "VND",
                "exchange_rate": "1",
                "seller_name": "CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN",
                "seller_tax_id": "0109988776",
                "seller_address": "Số 123 Đường Giả Định Alpha, Phường Thử Nghiệm 1, Quận Kịch Bản, TP. Hà Nội",
                "buyer_name": "CÔNG TY TNHH PHẦN MỀM MẪU THỬ THĂNG LONG",
                "buyer_tax_id": "0108877665",
                "buyer_address": "Số 45 Phố Kịch Bản Thử Nghiệm, Phường Giả Định, Quận Khảo Sát, TP. Hà Nội",
                "net_total": "45000000",
                "tax_total": "4500000",
                "gross_total": "49500000",
                "gross_total_in_words": "Bốn mươi chín triệu năm trăm nghìn đồng",
                "tax_authority_code": "TCT010998877620261C26TNN0000045",
                "direction": "incoming",
                "tax_breakdown[1].rate": "10%",
                "tax_breakdown[1].net_amount": "45000000",
                "tax_breakdown[1].tax_amount": "4500000",
            },
        },
        "tct_hdon_02_vat8_multi_rate.xml": {
            "relative_path": "xml/tct_hdon_02_vat8_multi_rate.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn đa thuế suất (8% và 10%) kết hợp",
            "client_tax_id": "0317665544",
            "expected_direction": "incoming",
            "schema_passed": True,
            "fields": {
                "invoice_form": "1",
                "invoice_series": "1C26MHK",
                "invoice_number": "0001289",
                "issue_date": "2026-04-20",
                "currency": "VND",
                "exchange_rate": "1",
                "seller_name": "TẬP ĐOÀN CÔNG NGHIỆP THỬ NGHIỆM NAM PHÁT",
                "seller_tax_id": "0318991122",
                "seller_address": "Số 456 Đại Lộ Kịch Bản Beta, Phường Thử Nghiệm 2, Quận Giả Lập, TP. Hồ Chí Minh",
                "buyer_name": "CÔNG TY CỔ PHẦN XÂY DỰNG MẪU THỬ KHANG ĐIỀN",
                "buyer_tax_id": "0317665544",
                "buyer_address": "Số 78 Đường Thử Nghiệm Tân Tạo, Phường Giả Lập 2, Quận Khảo Sát, TP. Hồ Chí Minh",
                "net_total": "50000000",
                "tax_total": "4400000",
                "gross_total": "54400000",
                "gross_total_in_words": "Năm mươi tư triệu bốn trăm nghìn đồng",
                "tax_authority_code": "TCT031899112220261C26MHK0001289",
                "direction": "incoming",
                "tax_breakdown[1].rate": "8%",
                "tax_breakdown[1].net_amount": "30000000",
                "tax_breakdown[1].tax_amount": "2400000",
                "tax_breakdown[2].rate": "10%",
                "tax_breakdown[2].net_amount": "20000000",
                "tax_breakdown[2].tax_amount": "2000000",
            },
        },
        "tct_hdon_03_vat0_export_foreign.xml": {
            "relative_path": "xml/tct_hdon_03_vat0_export_foreign.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn đầu ra xuất khẩu VAT 0%, ngoại tệ USD",
            "client_tax_id": "0401882233",
            "expected_direction": "outgoing",
            "schema_passed": True,
            "fields": {
                "invoice_form": "1",
                "invoice_series": "1C26TDA",
                "invoice_number": "0000305",
                "issue_date": "2026-05-18",
                "currency": "USD",
                "exchange_rate": "25450.00",
                "seller_name": "CÔNG TY TNHH XUẤT NHẬP KHẨU THỬ NGHIỆM ĐẠI TÂY DƯƠNG",
                "seller_tax_id": "0401882233",
                "seller_address": "Số 789 Đường Cảng Thử Nghiệm Gamma, Phường Giả Định 3, Quận Kịch Bản, TP. Đà Nẵng",
                "buyer_name": "SYNTHETIC GLOBAL LOGISTICS PTE. LTD.",
                "buyer_address": "Tòa nhà Giả Lập Alpha, Số 99 Đường Thử Nghiệm, Khu Tài Chính Giả Định, Singapore 999999",
                "net_total": "12500.00",
                "tax_total": "0.00",
                "gross_total": "12500.00",
                "gross_total_in_words": "Twelve thousand five hundred US Dollars",
                "tax_authority_code": "TCT040188223320261C26TDA0000305",
                "direction": "outgoing",
                "tax_breakdown[1].rate": "0%",
                "tax_breakdown[1].net_amount": "12500.00",
                "tax_breakdown[1].tax_amount": "0.00",
            },
        },
        "tct_hdon_04_outgoing_branch.xml": {
            "relative_path": "xml/tct_hdon_04_outgoing_branch.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn do Chi nhánh phụ thuộc phát hành (MST 10-3)",
            "client_tax_id": "0105667788-002",
            "expected_direction": "outgoing",
            "schema_passed": True,
            "fields": {
                "invoice_form": "1",
                "invoice_series": "1C26TDN",
                "invoice_number": "0000888",
                "issue_date": "2026-06-10",
                "currency": "VND",
                "exchange_rate": "1",
                "seller_name": "CHI NHÁNH CÔNG TY VIỄN THÔNG GIẢ LẬP SAO MAI",
                "seller_tax_id": "0105667788-002",
                "seller_address": "Số 88 Đại Lộ Thử Nghiệm 3, Phường Giả Định 3, Quận Kịch Bản, TP. Đà Nẵng",
                "buyer_name": "CÔNG TY TNHH KHÁCH SẠN MẪU THỬ BIỂN ĐÔNG",
                "buyer_tax_id": "0402113355",
                "buyer_address": "Số 12 Đường Ven Biển Giả Định, Quận Thử Nghiệm, TP. Đà Nẵng",
                "net_total": "18000000",
                "tax_total": "1800000",
                "gross_total": "19800000",
                "gross_total_in_words": "Mười chín triệu tám trăm nghìn đồng",
                "tax_authority_code": "TCT010566778800220261C26TDN0000888",
                "direction": "outgoing",
                "tax_breakdown[1].rate": "10%",
                "tax_breakdown[1].net_amount": "18000000",
                "tax_breakdown[1].tax_amount": "1800000",
            },
        },
        "tct_hdon_05_replacement.xml": {
            "relative_path": "xml/tct_hdon_05_replacement.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn điện tử thay thế cho hóa đơn sai sót có TTHDLQuan",
            "client_tax_id": "0201889900",
            "expected_direction": "incoming",
            "schema_passed": True,
            "fields": {
                "invoice_form": "1",
                "invoice_series": "1C26THG",
                "invoice_number": "0002560",
                "issue_date": "2026-07-25",
                "currency": "VND",
                "exchange_rate": "1",
                "seller_name": "CÔNG TY TNHH PHẦN MỀM THỬ NGHIỆM HOÀNG GIA",
                "seller_tax_id": "0201993344",
                "seller_address": "Số 101 Phố Thử Nghiệm Delta, Phường Giả Định 4, Quận Kịch Bản, TP. Hải Phòng",
                "buyer_name": "CÔNG TY CỔ PHẦN LOGISTICS MẪU THỬ HẢI PHÒNG",
                "buyer_tax_id": "0201889900",
                "buyer_address": "Số 15 Đường Cảng Giả Định, Quận Thử Nghiệm, TP. Hải Phòng",
                "net_total": "35000000",
                "tax_total": "3500000",
                "gross_total": "38500000",
                "gross_total_in_words": "Ba mươi tám triệu năm trăm nghìn đồng",
                "direction": "incoming",
                "related_invoice_nature": "1",
                "related_invoice_form": "1",
                "related_invoice_series": "1C26THG",
                "related_invoice_number": "0002100",
                "related_invoice_date": "2026-07-10",
                "tax_authority_code": "TCT020199334420261C26THG0002560",
                "tax_breakdown[1].rate": "10%",
                "tax_breakdown[1].net_amount": "35000000",
                "tax_breakdown[1].tax_amount": "3500000",
            },
        },
        "tct_hdon_06_wrapped_transmission.xml": {
            "relative_path": "xml/tct_hdon_06_wrapped_transmission.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn lồng trong gói thông điệp truyền nhận TDiep/DLieu",
            "client_tax_id": "0106554433",
            "expected_direction": "incoming",
            "schema_passed": True,
            "fields": {
                "invoice_form": "1",
                "invoice_series": "1C26TBV",
                "invoice_number": "0000789",
                "issue_date": "2026-08-15",
                "currency": "VND",
                "exchange_rate": "1",
                "seller_name": "CÔNG TY CP THIẾT BỊ Y TẾ GIẢ LẬP BÁCH VIỆT",
                "seller_tax_id": "0107778899",
                "seller_address": "Số 202 Đường Giả Lập Epsilon, Phường Thử Nghiệm 5, Quận Kịch Bản, TP. Hà Nội",
                "buyer_name": "BỆNH VIỆN ĐA KHOA MẪU THỬ BẠCH MAI",
                "buyer_tax_id": "0106554433",
                "buyer_address": "Số 100 Phố Thử Nghiệm Đồng Tâm, Quận Giả Định, TP. Hà Nội",
                "net_total": "60000000",
                "tax_total": "3000000",
                "gross_total": "63000000",
                "gross_total_in_words": "Sáu mươi ba triệu đồng",
                "direction": "incoming",
                "tax_authority_code": "TCT010777889920261C26TBV0000789",
                "tax_breakdown[1].rate": "5%",
                "tax_breakdown[1].net_amount": "60000000",
                "tax_breakdown[1].tax_amount": "3000000",
            },
        },
        "tct_hdon_07_missing_optional.xml": {
            "relative_path": "xml/tct_hdon_07_missing_optional.xml",
            "format": "xml",
            "variant": "tct-hdon-v1",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn tối giản thiếu các trường tùy chọn",
            "client_tax_id": "1801665544",
            "expected_direction": "outgoing",
            "schema_passed": True,
            "fields": {
                "invoice_form": "2",
                "invoice_series": "2C26TMT",
                "invoice_number": "0000150",
                "issue_date": "2026-09-02",
                "currency": "VND",
                "seller_name": "HỘ KINH DOANH NÔNG SẢN THỬ NGHIỆM MIỀN TÂY",
                "seller_tax_id": "1801665544",
                "buyer_name": "NGUYỄN VĂN AN (KHÁCH HÀNG GIẢ ĐỊNH)",
                "gross_total": "8500000",
                "direction": "outgoing",
            },
        },
        "malformed_invoice.xml": {
            "relative_path": "xml/malformed_invoice.xml",
            "format": "xml",
            "expected_document_type": "INVOICE",
            "description": "XML lỗi cú pháp thiếu thẻ đóng để kiểm thử lỗi xml_malformed",
            "schema_passed": False,
            "expected_error": "xml_malformed",
        },
        "invoice_digital_text_layer.pdf": {
            "relative_path": "pdf/invoice_digital_text_layer.pdf",
            "format": "pdf",
            "expected_document_type": "INVOICE",
            "description": "Hóa đơn điện tử PDF có text layer trích xuất trực tiếp (cho G4T-62)",
            "fields": {
                "invoice_series": "1C26TAA",
                "invoice_number": "00000088",
                "issue_date": "2026-04-12",
                "seller_tax_id": "0108998877",
                "buyer_tax_id": "0317654321",
                "gross_total": "55000000",
            },
        },
        "invoice_scanned_no_text.pdf": {
            "relative_path": "pdf/invoice_scanned_no_text.pdf",
            "format": "pdf",
            "expected_document_type": "INVOICE",
            "description": "PDF scan chỉ chứa ảnh raster không có text layer (cho G4T-62 và G4T-23)",
            "fields": {
                "invoice_series": "1C26TDA",
                "invoice_number": "0000305",
                "seller_tax_id": "0401882233",
                "gross_total": "22000000",
            },
        },
        "non_tax_contract.pdf": {
            "relative_path": "pdf/non_tax_contract.pdf",
            "format": "pdf",
            "expected_document_type": "UNKNOWN",
            "description": "Hợp đồng kinh tế dịch vụ tư vấn doanh nghiệp - Tài liệu phi thuế cho G4T-24",
            "fields": {
                "contract_number": "45/2026/HĐKT-GIẢ LẬP",
                "title": "HỢP ĐỒNG KINH TẾ DỊCH VỤ (MẪU THỬ)",
            },
        },
        "tax_notice_cqt.pdf": {
            "relative_path": "pdf/tax_notice_cqt.pdf",
            "format": "pdf",
            "expected_document_type": "TAX_NOTICE",
            "description": "Thông báo nộp tiền thuế của Chi cục Thuế Khu Vực Giả Định Alpha theo chuẩn G4T-24",
            "fields": {
                "notice_number": "14285/TB-CCT-GIẢ LẬP",
                "taxpayer_name": "CÔNG TY CỔ PHẦN CÔNG NGHỆ GIẢ LẬP BẢO AN",
                "taxpayer_mst": "0109988776",
                "total_tax_due": "16500000",
            },
        },
        "tax_payment_receipt_nsnn.pdf": {
            "relative_path": "pdf/tax_payment_receipt_nsnn.pdf",
            "format": "pdf",
            "expected_document_type": "TAX_PAYMENT_RECEIPT",
            "description": "Giấy nộp tiền vào Ngân sách Nhà nước Mẫu C1-02/NS theo chuẩn G4T-24",
            "fields": {
                "receipt_number": "GNT-2026-GIẢ LẬP-01",
                "taxpayer_mst": "0109988776",
                "treasury": "Kho bạc Nhà nước Giả Định Alpha",
                "amount_paid": "4500000",
            },
        },
        "mixed_documents_multi_page.pdf": {
            "relative_path": "pdf/mixed_documents_multi_page.pdf",
            "format": "pdf",
            "expected_document_type": "MIXED",
            "description": "1 file PDF đa trang chứa nhiều loại chứng từ (Trang 1 HĐ, Trang 2 Thông báo thuế, Trang 3 Giấy nộp tiền) theo chuẩn nhãn MIXED của G4T-24",
            "total_pages": 3,
            "contained_types": ["INVOICE", "TAX_NOTICE", "TAX_PAYMENT_RECEIPT"],
        },
        "invoice_scan_clean.png": {
            "relative_path": "images/invoice_scan_clean.png",
            "format": "image_png",
            "expected_document_type": "INVOICE",
            "description": "Ảnh PNG scan hóa đơn rõ nét phục vụ OCR (cho G4T-23)",
            "fields": {
                "invoice_number": "0000305",
                "invoice_series": "1C26TDA",
                "seller_tax_id": "0401882233",
                "gross_total": "22000000",
            },
        },
        "invoice_scan_blurred.png": {
            "relative_path": "images/invoice_scan_blurred.png",
            "format": "image_png",
            "expected_document_type": "INVOICE",
            "quality": "blurred",
            "expected_field_status": "needs_review",
            "description": "Ảnh scan hóa đơn bị làm mờ để test độ bền OCR; kỳ vọng kết quả là needs_review",
            "fields": {
                "status": "needs_review",
            },
        },
        "invoice_vat10_retail.jpg": {
            "relative_path": "images/invoice_vat10_retail.jpg",
            "format": "image_jpg",
            "expected_document_type": "INVOICE",
            "description": "Ảnh JPG hóa đơn GTGT phục vụ AC G4T-42 (bổ sung ảnh JPG)",
            "fields": {
                "invoice_number": "0000305",
                "invoice_series": "1C26TDA",
                "seller_tax_id": "0401882233",
                "gross_total": "22000000",
            },
        },
        "mixed_pack": {
            "relative_path": "mixed_pack/manifest.json",
            "format": "mixed_pack",
            "expected_document_type": "MIXED",
            "description": "Lô hồ sơ hỗn hợp đa định dạng kèm manifest theo tiêu chí AC G4T-42",
            "fields": {
                "package_name": "mixed_tax_batch_01",
                "total_documents": 7,
            },
        },
    },
}

gt_target = os.path.join(BASE_DIR, "ground_truth.json")
with open(gt_target, "w", encoding="utf-8") as f:
    json.dump(ground_truth, f, ensure_ascii=False, indent=2)

print(f"ground_truth.json written to {gt_target} with {len(ground_truth['files'])} entries.")


def main():
    print("All fixtures generated successfully!")


if __name__ == "__main__":
    main()
