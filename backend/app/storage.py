"""Kho ban goc ghi mot lan (ING 04). Sprint 1 thay bang MinIO object lock."""
import os
import tempfile
from pathlib import Path


class OriginalExists(Exception):
    pass


class LocalWriteOnceStore:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.getenv("ORIGINALS_DIR", "./originals"))

    def put(self, client_id: str, sha256: str, data: bytes) -> str:
        key = f"{client_id}/{sha256}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        # Ghi ra file tam truoc roi moi gan ten chinh thuc bang os.link: link la thao tac nguyen tu va
        # bao loi neu ten da ton tai, nen khong ai doc thay file dang ghi do, va van khong ghi de duoc.
        # (Truoc day mo truc tiep bang "xb": request khac thay file da ton tai nhung moi ghi mot phan,
        # so ma bam khong khop va tra loi 500 -> CI chap chon o test_concurrent_uploads.)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(tmp, path)
        except FileExistsError as exc:
            raise OriginalExists(key) from exc
        finally:
            os.unlink(tmp)
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()
