import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./app.css";

const API = import.meta.env.VITE_API ?? "http://localhost:8000";
const LABEL = {
  received: "Đã nhận", needs_review: "Chờ duyệt", processing: "Đang xử lý", quarantined: "Cách ly",
  rejected: "Từ chối", approved: "Đã duyệt", superseded: "Đã thay thế",
};

function App() {
  const [form, setForm] = useState({ name: "", tax_id: "", engagement: "" });
  const [session, setSession] = useState(null);
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  const headers = (ids) => ({ "X-User": "nhanvien.dev", "X-Client-Ids": ids ?? "" });

  async function call(path, init) {
    const res = await fetch(API + path, init);
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(body?.message ?? `Lỗi ${res.status}`);
    return body;
  }

  async function start(e) {
    e.preventDefault();
    setError("");
    try {
      const client = await call("/clients", {
        method: "POST",
        headers: { ...headers(), "Content-Type": "application/json" },
        body: JSON.stringify({ name: form.name, tax_id: form.tax_id }),
      });
      const batch = await call("/batches", {
        method: "POST",
        headers: { ...headers(client.id), "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: client.id, engagement_id: form.engagement }),
      });
      setSession({ clientId: client.id, batchId: batch.id, name: client.name });
    } catch (err) { setError(err.message); }
  }

  async function refresh(s) {
    const m = await call(`/batches/${s.batchId}/manifest`, { headers: headers(s.clientId) });
    setItems(m.items);
  }

  async function upload(e) {
    const failures = [];
    setError("");
    for (const file of e.target.files) {
      const body = new FormData();
      body.append("file", file);
      try {
        await call(`/batches/${session.batchId}/documents`, {
          method: "POST",
          headers: { ...headers(session.clientId), "Idempotency-Key": crypto.randomUUID() },
          body,
        });
      } catch (err) { failures.push(`${file.name}: ${err.message}`); }
    }
    setError(failures.join(" | "));
    await refresh(session);
    e.target.value = "";
  }

  return (
    <main>
      <h1>Tiếp nhận hồ sơ thuế</h1>
      <p className="note">Bản phát triển: chỉ dùng dữ liệu giả, chưa có đăng nhập thật.</p>
      {error && <p role="alert" className="error">{error}</p>}
      {!session ? (
        <form onSubmit={start}>
          <label>Tên khách hàng<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>Mã số thuế<input required value={form.tax_id} onChange={(e) => setForm({ ...form, tax_id: e.target.value })} /></label>
          <label>Mã hợp đồng dịch vụ<input required value={form.engagement} onChange={(e) => setForm({ ...form, engagement: e.target.value })} /></label>
          <button>Tạo lô hồ sơ</button>
        </form>
      ) : (
        <>
          <p>Khách hàng: <strong>{session.name}</strong></p>
          <label className="upload">Chọn file XML, PDF, JPG hoặc PNG
            <input type="file" multiple onChange={upload} />
          </label>
          <div className="scroll">
            <table>
              <thead><tr><th>Tên file</th><th>Kết quả</th><th>Trạng thái</th><th>Lý do</th><th>Document ID</th></tr></thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.submission_id}>
                    <td>{r.file_name}</td><td>{r.outcome}</td><td>{LABEL[r.status] ?? "Không xử lý"}</td>
                    <td>{r.reason ?? ""}</td><td className="hash">{r.document_id ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
