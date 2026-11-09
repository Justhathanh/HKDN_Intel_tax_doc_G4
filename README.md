# HKDN_Intel_tax_doc_G4
 Intelligent tax document ingestion. Separate field accuracy from whole-document correctness and preserve original signed evidence

# THTax Intelligent Tax Document Ingestion

Khung khởi đầu cho dự án. Đã có API tải tài liệu (ST01): tạo lô theo khách hàng, kiểm tra file, lưu bản gốc ghi một lần, tạo Document ID, chống gửi trùng, biên nhận và manifest. Thiết kế: `docs/G4T-10-thiet-ke-api-upload.md`, đặc tả: `docs/openapi.yaml`.

## Chạy thử

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Mở http://localhost:5173. Không đặt `DATABASE_URL` thì dùng SQLite; `docker compose up` chạy API với PostgreSQL.

## Chưa làm, không được dùng với dữ liệu thật

| Hạng mục | Hiện tại | Sprint |
| --- | --- | --- |
| Đăng nhập, MFA, 4 vai trò (SEC 01) | Header giả `X-User`, `X-Client-Ids` | 1 |
| Row Level Security | Có `backend/sql/rls.sql`, chưa áp dụng và chưa test | 1 |
| Quét mã độc, sandbox (ING 03) | Chưa có | 1 |
| Kho có object lock | Thư mục cục bộ ghi một lần | 1 |
| Mã hóa, audit chống sửa đổi (SEC 02, SEC 04) | Chưa có; mới có log trạng thái | 1, 3 |
| OCR, phân loại, hàng đợi Celery | Tài liệu dừng ở `received`; `xml_parser.py` chưa nối vào luồng | 2 |
| Mapping XML | `tt-generic-v0`, chưa đối chiếu với file thật; chốt 2 biến thể tại G0 | 0, 2 |
| Duyệt, sửa, phê duyệt, xuất dữ liệu | Chưa có | 3 |

Backlog: xem `THTax_Product_Backlog.xlsx`. Mọi story gắn mã yêu cầu RFP.
