# HƯỚNG DẪN Ý NGHĨA CÁC FILE TEST (TIẾNG VIỆT)

Thư mục: `docs/test/files/`

Dưới đây là bảng tra cứu toàn bộ các file mẫu dùng để kiểm thử (test) hệ thống Tiếp nhận hồ sơ thuế thông minh (THTax Group 4):

| STT | Tên file | Loại file / Đặc điểm | Mục đích kiểm thử | Kết quả mong đợi |
|:---:|:---|:---|:---|:---|
| 1 | `valid_invoice_2p.pdf` | File PDF hóa đơn chuẩn 2 trang | Test luồng upload thành công (Happy Path) | Status 201, `accepted`, trạng thái "Đã nhận" |
| 2 | `exactly_30p_invoice.pdf` | File PDF đúng 30 trang (ngưỡng tối đa) | Test giá trị biên (Boundary Value Analysis - tối đa 30 trang) | Status 201, `accepted`, trạng thái "Đã nhận" |
| 3 | `over_30p_invoice.pdf` | File PDF 31 trang (vượt quá 30 trang) | Test vượt giới hạn số trang cho phép | Status 422, `rejected`, lỗi: *"PDF vượt quá 30 trang..."* |
| 4 | `password_protected.pdf` | File PDF bị cài mật khẩu bảo vệ | Test bảo mật: từ chối file có mật khẩu không đọc được | Status 422, `rejected`, lỗi: *"PDF có mật khẩu..."* |
| 5 | `corrupt_invoice.pdf` | File PDF bị hỏng cấu trúc (nội dung rác) | Test độ tin cậy: từ chối file hỏng | Status 422, `rejected`, lỗi: *"File bị hỏng, không đọc được..."* |
| 6 | `empty_file.pdf` | File rỗng dung lượng 0 byte | Test file rỗng | Bị chặn ngay từ Frontend: *"File rỗng. Hãy chọn file khác."* |
| 7 | `fake_pdf.pdf` | File thực chất là `.exe` đổi tên đuôi sang `.pdf` | Test bảo mật: phát hiện giả mạo phần mở rộng file (magic bytes) | Bị Backend từ chối / chặn tải |
| 8 | `unsafe_xxe.xml` | File XML chứa mã độc khai thác lỗ hổng XXE | Test an toàn thông tin: chống tấn công XML External Entity | Status 422, lỗi: `unsafe_xml` (cách ly hoặc từ chối) |
| 9 | `sample_invoice.xml` | File XML hóa đơn điện tử hợp lệ | Test upload hóa đơn XML | Status 201, `accepted` |
| 10 | `invalid_xml.xml` | File XML sai cú pháp (thiếu thẻ đóng...) | Test bắt lỗi cú pháp XML | Status 422, từ chối |
| 11 | `sample_image.png` / `.jpg` | Ảnh hóa đơn chụp | Test upload hóa đơn dạng hình ảnh | Status 201, `accepted` |
| 12 | `over_20mb.pdf` | File kích thước > 20 MiB | Test vượt quá giới hạn dung lượng tối đa | Bị chặn: *"File vượt quá 20 MiB..."* |
