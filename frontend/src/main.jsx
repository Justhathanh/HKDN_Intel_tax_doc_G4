
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./app.css";
import {
  uploadDocument,
  validateFile,
  messageFor,
} from "./uploadDocument";

const API = import.meta.env.VITE_API ?? "http://localhost:8000";

const LABEL = {
  received: "Đã nhận",
  needs_review: "Chờ duyệt",
  processing: "Đang xử lý",
  quarantined: "Cách ly",
  rejected: "Từ chối",
  approved: "Đã duyệt",
  superseded: "Đã thay thế",
};

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.xml";

function App() {
  const [form, setForm] = useState({
    name: "",
    tax_id: "",
    engagement: "",
  });

  const [session, setSession] = useState(null);
  const [items, setItems] = useState([]);
  const [files, setFiles] = useState([]);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [hasLoaded, setHasLoaded] = useState(false);

  const [selectedDocumentId, setSelectedDocumentId] = useState(null);

  const refreshInFlight = useRef(false);
  const refreshPending = useRef(false);
  const sessionRef = useRef(null);

  const selectedDocument = items.find(
    (item) => item.document_id === selectedDocumentId
  );

  const headers = (ids) => ({
    "X-User": "nhanvien.dev",
    "X-Client-Ids": ids ?? "",
  });

  async function call(path, init) {
    const res = await fetch(API + path, init);
    const body = await res.json().catch(() => null);

    if (!res.ok) {
      throw new Error(
        body?.message ??
        body?.detail ??
        `Lỗi HTTP ${res.status}`
      );
    }

    return body;
  }

  async function start(e) {
    e.preventDefault();

    setError("");
    setMessage("");
    setLoading(true);

    try {
      const client = await call("/clients", {
        method: "POST",
        headers: {
          ...headers(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: form.name,
          tax_id: form.tax_id,
        }),
      });

      const batch = await call("/batches", {
        method: "POST",
        headers: {
          ...headers(client.id),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_id: client.id,
          engagement_id: form.engagement,
        }),
      });

      setItems([]);
      setFiles([]);
      setHasLoaded(false);
      setRefreshError("");
      setSelectedDocumentId(null);

      const newSession = {
        clientId: client.id,
        batchId: batch.id,
        name: client.name,
      };

      sessionRef.current = newSession;
      setSession(newSession);
      setMessage("Tạo lô hồ sơ thành công!");
    } catch (err) {
      setError(err.message ?? "Không thể tạo lô hồ sơ.");
    } finally {
      setLoading(false);
    }
  }

  async function refresh(s, signal) {
    if (!s || signal?.aborted) return;

    if (refreshInFlight.current) {
      refreshPending.current = true;
      return;
    }

    refreshInFlight.current = true;
    setRefreshing(true);
    setRefreshError("");

    try {
      const manifest = await call(
        `/batches/${encodeURIComponent(s.batchId)}/manifest`,
        {
          headers: headers(s.clientId),
          signal,
        }
      );

      if (
        !signal?.aborted &&
        sessionRef.current?.batchId === s.batchId
      ) {
        setItems(manifest.items ?? []);
        setHasLoaded(true);
      }
    } catch (err) {
      if (
        err.name !== "AbortError" &&
        !signal?.aborted &&
        sessionRef.current?.batchId === s.batchId
      ) {
        setRefreshError(err.message ?? "Không thể cập nhật.");
        throw err;
      }
    } finally {
      refreshInFlight.current = false;

      if (
        !signal?.aborted &&
        sessionRef.current?.batchId === s.batchId
      ) {
        setRefreshing(false);

        if (refreshPending.current) {
          refreshPending.current = false;
          refresh(s, signal).catch(() => {});
        }
      }
    }
  }

  useEffect(() => {
    if (!session) return;

    const controller = new AbortController();

    sessionRef.current = session;

    refresh(session, controller.signal).catch(() => {});

    const interval = setInterval(() => {
      if (document.visibilityState === "visible") {
        refresh(session, controller.signal).catch(() => {});
      }
    }, 5000);

    return () => {
      clearInterval(interval);
      controller.abort();
      refreshPending.current = false;
    };
  }, [session]);

  function selectFiles(e) {
    setError("");
    setMessage("");

    const selected = Array.from(e.target.files ?? []);
    const valid = [];
    const invalid = [];

    selected.forEach((file) => {
      const errorCode = validateFile(file);

      if (errorCode) {
        invalid.push(
          `${file.name}: ${messageFor(
            errorCode,
            "File không hợp lệ."
          )}`
        );
      } else {
        valid.push(file);
      }
    });

    setFiles(valid);

    if (invalid.length) {
      setError(invalid.join(" | "));
    }
  }

  async function upload() {
    if (!session || !files.length || uploading) return;

    setUploading(true);
    setError("");
    setMessage("");

    const failures = [];
    let success = 0;

    try {
      for (const file of files) {
        try {
          await uploadDocument(
            session.batchId,
            file,
            crypto.randomUUID(),
            headers(session.clientId)
          );

          success++;
        } catch (err) {
          failures.push(
            `${file.name}: ${
              err.message ?? "Upload thất bại"
            }`
          );
        }
      }

      if (success) {
        setMessage(
          `Đã gửi thành công ${success} tài liệu.`
        );
        setFiles([]);
      }

      if (failures.length) {
        setError(failures.join(" | "));
      }

      try {
        await refresh(session);
      } catch (err) {
        setError((prev) =>
          [
            prev,
            `Không tải được danh sách: ${err.message}`,
          ]
            .filter(Boolean)
            .join(" | ")
        );
      }
    } finally {
      setUploading(false);
    }
  }

  return (
    <main>
      <header className="page-header">
        <div className="logo">TH</div>

        <div>
          <h1>Tiếp nhận hồ sơ thuế</h1>
          <p className="note">
            Hệ thống quản lý và tải lên tài liệu thuế
          </p>
        </div>
      </header>

      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}

      {message && (
        <div className="alert success" role="status">
          {message}
        </div>
      )}

      {!session ? (
        <section className="card">
          <h2>Tạo lô hồ sơ mới</h2>

          <p className="note">
            Nhập thông tin khách hàng để bắt đầu tải tài liệu.
          </p>

          <form onSubmit={start}>
            <label>
              Tên khách hàng
              <input
                required
                value={form.name}
                onChange={(e) =>
                  setForm({
                    ...form,
                    name: e.target.value,
                  })
                }
                placeholder="Nhập tên khách hàng"
              />
            </label>

            <label>
              Mã số thuế
              <input
                required
                value={form.tax_id}
                onChange={(e) =>
                  setForm({
                    ...form,
                    tax_id: e.target.value,
                  })
                }
                placeholder="Nhập mã số thuế"
              />
            </label>

            <label>
              Mã hợp đồng dịch vụ
              <input
                required
                value={form.engagement}
                onChange={(e) =>
                  setForm({
                    ...form,
                    engagement: e.target.value,
                  })
                }
                placeholder="Nhập mã hợp đồng"
              />
            </label>

            <button disabled={loading}>
              {loading ? "Đang tạo..." : "Tạo lô hồ sơ"}
            </button>
          </form>
        </section>
      ) : (
        <>
          <section className="card">
            <h2>Thông tin lô hồ sơ</h2>

            <p>
              <strong>Khách hàng:</strong>{" "}
              {session.name}
            </p>

            <p className="note">
              Mã lô: {session.batchId}
            </p>
          </section>

          <section className="card">
            <h2>Tải lên tài liệu</h2>

            <p className="note">
              Hỗ trợ PDF, JPG, PNG và XML.
            </p>

            <label className="upload-zone">
              <span className="upload-icon">↑</span>

              <strong>
                Nhấn để chọn tài liệu
              </strong>

              <span>
                Có thể chọn nhiều file cùng lúc
              </span>

              <input
                type="file"
                accept={ACCEPT}
                multiple
                disabled={uploading}
                onChange={selectFiles}
                onClick={(e) => {
                  e.target.value = "";
                }}
              />
            </label>

            {files.length > 0 && (
              <div className="selected-files">
                <h3>
                  File đã chọn ({files.length})
                </h3>

                {files.map((file, index) => (
                  <div
                    className="file-row"
                    key={`${file.name}-${index}`}
                  >
                    <span>{file.name}</span>

                    <span>
                      {(
                        file.size /
                        1024 /
                        1024
                      ).toFixed(2)}{" "}
                      MB
                    </span>
                  </div>
                ))}
              </div>
            )}

            <button
              className="upload-button"
              onClick={upload}
              disabled={!files.length || uploading}
            >
              {uploading
                ? "Đang tải tài liệu..."
                : "Tải tài liệu lên"}
            </button>
          </section>

          <section className="card">
            <div className="section-heading">
              <h2>Danh sách tài liệu</h2>

              <button
                type="button"
                className="secondary"
                disabled={uploading || refreshing}
                onClick={() => {
                  refresh(session).catch(() => {});
                }}
              >
                {refreshing
                  ? "Đang cập nhật..."
                  : "Làm mới"}
              </button>
            </div>

            <p className="note">
              Trạng thái tài liệu được tự động cập nhật
              mỗi 5 giây khi trang đang hiển thị.
            </p>

            {refreshing && (
              <p className="note" role="status">
                Đang cập nhật trạng thái tài liệu...
              </p>
            )}

            {refreshError && (
              <div
                className="alert error"
                role="alert"
              >
                Không thể cập nhật danh sách:{" "}
                {refreshError}
              </div>
            )}

            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Tên file</th>
                    <th>Kết quả</th>
                    <th>Trạng thái</th>
                    <th>Lý do</th>
                    <th>Document ID</th>
                    <th>Chi tiết</th>
                  </tr>
                </thead>

                <tbody>
                  {!hasLoaded && refreshing ? (
                    <tr>
                      <td
                        colSpan="6"
                        className="empty"
                      >
                        Đang tải danh sách tài liệu...
                      </td>
                    </tr>
                  ) : items.length === 0 ? (
                    <tr>
                      <td
                        colSpan="6"
                        className="empty"
                      >
                        {refreshError && !hasLoaded
                          ? "Chưa thể tải danh sách tài liệu"
                          : "Chưa có tài liệu để hiển thị"}
                      </td>
                    </tr>
                  ) : (
                    items.map((r, index) => (
                      <tr
                        key={r.submission_id ?? index}
                      >
                        <td>{r.file_name}</td>

                        <td>
                          {r.outcome ?? "—"}
                        </td>

                        <td>
                          {LABEL[r.status] ??
                            r.status ??
                            "Chưa có trạng thái"}
                        </td>

                        <td>
                          {r.reason ?? "—"}
                        </td>

                        <td className="hash">
                          {r.document_id ?? "—"}
                        </td>

                        <td>
                          <button
                            type="button"
                            className="secondary"
                            disabled={!r.document_id}
                            onClick={() =>
                              setSelectedDocumentId(
                                r.document_id
                              )
                            }
                          >
                            Xem chi tiết
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {selectedDocument && (
            <section className="card">
              <div className="section-heading">
                <h2>Chi tiết tài liệu</h2>

                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    setSelectedDocumentId(null)
                  }
                >
                  Đóng
                </button>
              </div>

              <p>
                <strong>Tên file:</strong>{" "}
                {selectedDocument.file_name}
              </p>

              <p>
                <strong>Document ID:</strong>{" "}
                {selectedDocument.document_id}
              </p>

              <p>
                <strong>Trạng thái tài liệu:</strong>{" "}
                {LABEL[selectedDocument.status] ??
                  selectedDocument.status ??
                  "Chưa có trạng thái"}
              </p>

              <p>
                <strong>Kết quả tiếp nhận:</strong>{" "}
                {selectedDocument.outcome ?? "Chưa có"}
              </p>

              <p>
                <strong>Lý do:</strong>{" "}
                {selectedDocument.reason ?? "Không có"}
              </p>

              <h3>Trạng thái xử lý nền</h3>

              <p className="note">
                Backend chưa cung cấp API để lấy trạng
                thái ProcessingJob cho tài liệu này.
              </p>

              <h3>Kết quả OCR</h3>

              <p className="note">
                Chưa có dữ liệu OCR từ API Backend.
                Nội dung văn bản theo từng trang sẽ
                được hiển thị tại đây khi API hỗ trợ.
              </p>

              <h3>Kết quả phân loại</h3>

              <p className="note">
                Chưa có dữ liệu phân loại từ API Backend.
                Loại tài liệu, độ tin cậy và lý do
                phân loại sẽ được hiển thị khi API
                cung cấp các trường tương ứng.
              </p>
            </section>
          )}
        </>
      )}

      <footer>
        TH Tax Document Management — Development
      </footer>
    </main>
  );
}

createRoot(
  document.getElementById("root")
).render(<App />);
