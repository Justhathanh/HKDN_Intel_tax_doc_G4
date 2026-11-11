
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./app.css";

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
const FORMATS = ["pdf", "jpg", "jpeg", "png", "xml"];

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

  const headers = (ids) => ({
    "X-User": "nhanvien.dev",
    "X-Client-Ids": ids ?? "",
  });

  async function call(path, init) {
    const res = await fetch(API + path, init);
    const body = await res.json().catch(() => null);

    if (!res.ok) {
      throw new Error(body?.message ?? `Lỗi ${res.status}`);
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

      setSession({
        clientId: client.id,
        batchId: batch.id,
        name: client.name,
      });
      setItems([]);
      setMessage("Tạo lô hồ sơ thành công!");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function refresh(s) {
    const manifest = await call(
      `/batches/${s.batchId}/manifest`,
      { headers: headers(s.clientId) }
    );
    setItems(manifest.items ?? []);
  }

  function selectFiles(e) {
    setError("");
    setMessage("");

    const selected = Array.from(e.target.files ?? []);
    const valid = [];
    const invalid = [];

    selected.forEach((file) => {
      const ext = file.name.split(".").pop().toLowerCase();

      if (!FORMATS.includes(ext)) {
        invalid.push(`${file.name}: Định dạng không hỗ trợ`);
      } else {
        valid.push(file);
      }
    });

    setFiles(valid);
    if (invalid.length) setError(invalid.join(" | "));
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
        const body = new FormData();
        body.append("file", file);

        try {
          await call(`/batches/${session.batchId}/documents`, {
            method: "POST",
            headers: {
              ...headers(session.clientId),
              "Idempotency-Key": crypto.randomUUID(),
            },
            body,
          });
          success++;
        } catch (err) {
          failures.push(`${file.name}: ${err.message}`);
        }
      }

      if (success) {
        setMessage(`Đã gửi thành công ${success} tài liệu.`);
      }

      if (failures.length) {
        setError(failures.join(" | "));
      }

      if (success) {
        setFiles([]);
      }

      try {
        await refresh(session);
      } catch (err) {
        setError((prev) =>
          [prev, `Không tải được danh sách: ${err.message}`]
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
        <div className="alert error" role="alert">{error}</div>
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
                  setForm({ ...form, name: e.target.value })
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
                  setForm({ ...form, tax_id: e.target.value })
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
                  setForm({ ...form, engagement: e.target.value })
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
              <strong>Khách hàng:</strong> {session.name}
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
              <strong>Nhấn để chọn tài liệu</strong>
              <span>Có thể chọn nhiều file cùng lúc</span>
              <input
                type="file"
                accept={ACCEPT}
                multiple
                disabled={uploading}
                onChange={selectFiles}
                onClick={(e) => { e.target.value = ""; }}
              />
            </label>

            {files.length > 0 && (
              <div className="selected-files">
                <h3>File đã chọn ({files.length})</h3>
                {files.map((file, index) => (
                  <div className="file-row" key={index}>
                    <span>{file.name}</span>
                    <span>
                      {(file.size / 1024 / 1024).toFixed(2)} MB
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
                className="secondary"
                disabled={uploading}
                onClick={async () => {
                  try {
                    await refresh(session);
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                Làm mới
              </button>
            </div>

            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Tên file</th>
                    <th>Kết quả</th>
                    <th>Trạng thái</th>
                    <th>Lý do</th>
                    <th>Document ID</th>
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="empty">
                        Chưa có tài liệu để hiển thị
                      </td>
                    </tr>
                  ) : (
                    items.map((r, index) => (
                      <tr key={r.submission_id ?? index}>
                        <td>{r.file_name}</td>
                        <td>{r.outcome}</td>
                        <td>{LABEL[r.status] ?? r.status ?? "Không xử lý"}</td>
                        <td>{r.reason ?? ""}</td>
                        <td className="hash">{r.document_id ?? ""}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <footer>
        TH Tax Document Management — Development
      </footer>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
