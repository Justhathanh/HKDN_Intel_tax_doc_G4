"""Kho bản gốc ghi một lần: nhiều request cùng file chạy đồng thời không được lỗi (sửa lỗi CI PR #10)."""
import hashlib
import threading

from app.storage import LocalWriteOnceStore

DATA = b"x" * (8 * 1024 * 1024)  # file lớn để việc ghi kéo dài, dễ lộ tranh chấp
DIGEST = hashlib.sha256(DATA).hexdigest()


def test_concurrent_put_never_exposes_partial_file(tmp_path):
    store = LocalWriteOnceStore(str(tmp_path))
    start, errors, seen = threading.Barrier(12), [], []

    def worker():
        start.wait()
        try:
            key = store.put("c1", DIGEST, DATA)
        except Exception as exc:  # OriginalExists là bình thường; phải đọc được bản đầy đủ
            key = str(exc)
        try:
            seen.append(hashlib.sha256(store.get(key)).hexdigest())
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and seen == [DIGEST] * 12
    assert [p.name for p in (tmp_path / "c1").iterdir()] == [DIGEST]  # không sót file tạm


def test_put_is_still_write_once(tmp_path):
    store = LocalWriteOnceStore(str(tmp_path))
    store.put("c1", DIGEST, DATA)
    try:
        store.put("c1", DIGEST, b"khac")
        raise AssertionError("phải báo OriginalExists")
    except Exception as exc:
        assert type(exc).__name__ == "OriginalExists"
    assert store.get(f"c1/{DIGEST}") == DATA
