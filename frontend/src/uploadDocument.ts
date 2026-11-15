// G4T-13: API upload tài liệu

export const MAX_BYTES = 20 * 1024 * 1024;

export const ACCEPT = ".pdf,.jpg,.jpeg,.png,.xml";

const EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "xml"];

export type DocumentReceipt = {
  document_id: string;
  submission_id: string;
  batch_id: string;
  file_name: string;
  size: number;
  sha256: string;
  mime_type: string;
  page_count: number | null;
  channel: string;
  uploaded_by: string;
  status: string;
  duplicate: boolean;
  received_at: string;
};

type ApiErrorBody = {
  error_code: string;
  message: string;
  submission_id: string | null;
  document_id: string | null;
};

type AuthHeaders = Record<string, string>;

export class UploadError extends Error {
  code: string;
  status: number;
  documentId: string | null;

  constructor(
    code: string,
    message: string,
    status = 0,
    documentId: string | null = null,
  ) {
    super(message);
    this.name = "UploadError";
    this.code = code;
    this.status = status;
    this.documentId = documentId;
  }
}

const MESSAGES: Record<string, string> = {
  unauthenticated: "Bạn chưa đăng nhập.",
  empty_file: "File rỗng. Hãy chọn file khác.",
  file_too_large: "File vượt quá 20 MiB. Hãy chọn file nhỏ hơn.",
  unsupported_format: "Chỉ nhận file PDF, JPG, PNG hoặc XML.",
  too_many_pages: "PDF vượt quá 30 trang. Hãy tách nhỏ file rồi tải lại.",
  password_protected: "PDF có mật khẩu. Hãy bỏ mật khẩu rồi tải lại.",
  corrupt_file: "File bị hỏng, không đọc được. Hãy kiểm tra file rồi tải lại.",
  network_error: "Mất kết nối đến máy chủ. Hãy kiểm tra mạng rồi thử lại.",
  config_error: "Không tìm thấy cấu hình API.",
};

export function messageFor(code: string, fallback: string): string {
  return MESSAGES[code] ?? fallback;
}

/**
 * Kiểm tra định dạng, dung lượng và file rỗng trước khi upload.
 * Trả về error code nếu không hợp lệ, ngược lại trả về null.
 */
export function validateFile(file: File): string | null {
  const ext = file.name.includes(".")
    ? file.name.split(".").pop()!.toLowerCase()
    : "";

  if (!EXTENSIONS.includes(ext)) {
    return "unsupported_format";
  }

  if (file.size === 0) {
    return "empty_file";
  }

  if (file.size > MAX_BYTES) {
    return "file_too_large";
  }

  return null;
}

/**
 * Upload nguyên file gốc lên Backend.
 *
 * headers được truyền từ main.jsx để sử dụng session hiện tại.
 * onProgress là callback tùy chọn để cập nhật tiến độ upload.
 */
export function uploadDocument(
  batchId: string,
  file: File,
  idempotencyKey: string,
  requestHeaders: AuthHeaders,
  onProgress?: (percent: number) => void,
): Promise<DocumentReceipt> {
  return new Promise((resolve, reject) => {
    const base = (
      import.meta.env.VITE_API ?? "http://localhost:8000"
    ).replace(/\/+$/, "");

    if (!base) {
      reject(
        new UploadError(
          "config_error",
          messageFor("config_error", ""),
        ),
      );
      return;
    }

    const form = new FormData();

    // Gửi nguyên file gốc, không chỉnh sửa nội dung.
    form.append("file", file);

    const xhr = new XMLHttpRequest();

    xhr.open(
      "POST",
      `${base}/batches/${encodeURIComponent(batchId)}/documents`,
    );

    xhr.responseType = "json";

    xhr.setRequestHeader("Idempotency-Key", idempotencyKey);

    // Nhận headers từ session của main.jsx.
    for (const [name, value] of Object.entries(requestHeaders)) {
      xhr.setRequestHeader(name, value);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round(
          (event.loaded * 100) / event.total,
        );

        onProgress(percent);
      }
    };

    xhr.onload = () => {
      // 201: Upload file mới.
      // 200: File đã tồn tại, Backend trả về bản ghi cũ.
      if (xhr.status === 200 || xhr.status === 201) {
        resolve(xhr.response as DocumentReceipt);
        return;
      }

      const body = xhr.response as Partial<ApiErrorBody> | null;

      const code = body?.error_code ?? "server_error";

      const fallback =
        body?.message ?? "Máy chủ gặp lỗi. Hãy thử lại sau.";

      reject(
        new UploadError(
          code,
          messageFor(code, fallback),
          xhr.status,
          body?.document_id ?? null,
        ),
      );
    };

    xhr.onerror = () => {
      reject(
        new UploadError(
          "network_error",
          messageFor("network_error", ""),
        ),
      );
    };

    xhr.onabort = () => {
      reject(
        new UploadError(
          "network_error",
          "Yêu cầu upload đã bị hủy.",
        ),
      );
    };

    xhr.send(form);
  });
}