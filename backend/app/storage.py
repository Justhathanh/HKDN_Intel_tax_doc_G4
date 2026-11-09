"""Kho ban goc ghi mot lan (ING 04). Sprint 1 thay bang MinIO object lock."""
import os
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
        try:
            with open(path, "xb") as handle:  # "x" khong cho ghi de
                handle.write(data)
        except FileExistsError as exc:
            raise OriginalExists(key) from exc
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()
