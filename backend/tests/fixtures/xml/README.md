# XML hóa đơn mẫu (dữ liệu giả)

Toàn bộ tên công ty, MST, số hóa đơn trong thư mục này là **giả**, chỉ dùng để test (G4T-61, G4T-46).
Không đặt hóa đơn thật của khách hàng vào repo (repo công khai).

| File | Biến thể | Trường hợp |
|---|---|---|
| `tct_hdon_incoming.xml` | tct-hdon-v1 | Hóa đơn đầu vào đầy đủ: dấu tiếng Việt, số 0 đầu, 2 thuế suất, mã CQT, chữ ký |
| `tct_hdon_outgoing_ns.xml` | tct-hdon-v1 | Hóa đơn đầu ra có namespace, MST chi nhánh dạng 10-3, ngoại tệ |
| `tct_hdon_replacement.xml` | tct-hdon-v1 | Hóa đơn thay thế, có tham chiếu hóa đơn bị thay thế (TTHDLQuan) |
| `tct_hdon_wrapped.xml` | tct-hdon-v1 | Hóa đơn nằm trong thông điệp bọc ngoài (TDiep/DLieu) |
