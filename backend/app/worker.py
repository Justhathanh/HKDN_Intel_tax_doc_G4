"""Tiến trình chạy nền lấy việc từ hàng đợi processing_jobs (G4T-69, G4T-70).

Tuân thủ:
- Đọc bản gốc ở chế độ chỉ đọc và kiểm tra lại SHA-256 trước khi xử lý (ING 04).
- Không ghi log hay lưu nội dung tài liệu / stack trace thô vào database (SEC 04).
"""
import logging
import os
import signal
import socket
import time
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from . import jobs
from .db import SessionLocal
from .extraction import extract_processor
from .models import ProcessingJob
from .storage import LocalWriteOnceStore

logger = logging.getLogger("thtax.worker")

ProcessorFn = Callable[[ProcessingJob, bytes], str]


def default_processor(job: ProcessingJob, data: bytes) -> str:
    """Bộ xử lý mặc định: trích xuất thật (app/extraction.py, G4T-61).

    Trước đây hàm này chỉ trả PROCESSOR_VERSION nên job luôn SUCCEEDED dù không trích xuất gì
    (nhận xét P0 "worker báo thành công giả"). Nay XML hóa đơn được parse (G4T-61), PDF được đọc lớp chữ theo
    trang (G4T-62); ảnh (chờ OCR) trả lỗi `unsupported_document` thay vì báo thành công.
    """
    return extract_processor(job, data)


def process_one(
    session_factory: sessionmaker[Session],
    store: LocalWriteOnceStore,
    worker_id: str,
    job_type: str = "extract",
    processor: ProcessorFn = default_processor,
) -> str | None:
    """Nhận và xử lý tối đa một job đến hạn; trả về job_id nếu có việc, ngược lại trả None."""
    with session_factory() as db:
        job = jobs.claim_next(db, worker_id=worker_id, job_type=job_type)
        db.commit()
        if job is None:
            return None
        job_id = job.id

    with session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return None
        try:
            data = jobs.read_original(store, db, job)
            version = processor(job, data)
            jobs.succeed(db, job, processor_version=version)
        except jobs.JobError as exc:
            jobs.fail(db, job, exc.code)
            logger.warning("job_failed job_id=%s code=%s", job_id, exc.code)
        except Exception as exc:
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job is not None:
                jobs.fail(db, job, "internal_error")
            logger.error("job_unexpected_error job_id=%s type=%s", job_id, type(exc).__name__)
        db.commit()
    return job_id


def run_forever(
    session_factory: sessionmaker[Session] = SessionLocal,
    store: LocalWriteOnceStore | None = None,
    worker_id: str | None = None,
    poll_interval: float = 1.0,
    reclaim_interval: float = 30.0,
    processor: ProcessorFn = default_processor,
) -> None:
    """Vòng lặp chạy nền liên tục; dừng an toàn khi nhận SIGINT hoặc SIGTERM."""
    store = store or LocalWriteOnceStore()
    worker_id = worker_id or f"worker-{socket.gethostname()}-{os.getpid()}"
    stop = False

    def _handle_stop(signum: int, _frame: object) -> None:
        nonlocal stop
        logger.info("worker_stopping worker_id=%s signal=%s", worker_id, signum)
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info("worker_started worker_id=%s poll_interval=%ss", worker_id, poll_interval)
    last_reclaim = 0.0

    while not stop:
        now = time.monotonic()
        if now - last_reclaim >= reclaim_interval:
            with session_factory() as db:
                reclaimed = jobs.reclaim_expired(db)
                db.commit()
                if reclaimed:
                    logger.info("reclaimed_expired_jobs count=%s", len(reclaimed))
            last_reclaim = now

        processed = process_one(session_factory, store, worker_id=worker_id, processor=processor)
        if processed is None and not stop:
            time.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    interval = float(os.getenv("QUEUE_POLL_INTERVAL", "1.0"))
    run_forever(poll_interval=interval)
