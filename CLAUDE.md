# Dự án THTax: Intelligent Tax Document Ingestion (nhóm G4)

Hệ thống tiếp nhận hồ sơ thuế cho THTax: nhận file, kiểm tra, lưu bản gốc, trích xuất, nhân viên duyệt, xuất dữ liệu.
Người dùng phiên này: Lương Quốc An, dev Backend & Kiến trúc. Chỉ làm task Jira giao cho An, không sửa phần của người khác.

## Công nghệ
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 (thư mục `backend/`)
- Frontend: React + Vite (thư mục `frontend/`, do Tâm phụ trách)
- Test: pytest; CI GitHub Actions chạy trên Python 3.12 và PostgreSQL

## Lệnh thường dùng (Windows, Git Bash)
```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
pytest -q
alembic upgrade head
uvicorn app.main:app --reload --port 8000
python -m scripts.export_openapi   # chạy lại mỗi khi đổi API
```

## Quy trình Git
- Branch tạo từ Jira, tên không dấu, ví dụ `G4T-16-kiem-tra-dinh-dang`
- Mỗi subtask một commit, message bắt đầu bằng mã task: `G4T-16 Noi dung khong dau`
- Không commit hay push thẳng lên `main`; mở PR và chờ người Approve
- Không tự chạy `git push` khi chưa được An đồng ý

## Quy tắc bắt buộc (theo RFP)
- Không ghi đè bản gốc; mọi bản xử lý là bản mới (ING 04)
- Mọi truy vấn phải lọc theo `client_id`; truy cập khách hàng khác trả 404 (SEC 01)
- Mọi lần gửi file đều được ghi lại trong `submissions`, kể cả file bị từ chối (ING 02)
- Thiếu giá trị là chưa biết, không phải 0; số tiền dùng Decimal (EXT 06)
- Không có đường tự động duyệt; đổi trạng thái qua `check_transition` và ghi `state_events`
- Lỗi API trả `error_code` khai báo trong `app/errors.py`

## Dữ liệu
- Chỉ dùng dữ liệu giả. Không đưa hóa đơn thật, mật khẩu hay file `.env` vào repo hoặc vào chat.

## Tài liệu
- Thiết kế API: `docs/G4T-10-thiet-ke-api-upload.md`, đặc tả: `docs/openapi.yaml`
- Code mới phải có test; chạy `pytest -q` trước khi commit