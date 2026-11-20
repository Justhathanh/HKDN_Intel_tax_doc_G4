"""Kiểm thử tích hợp hàng đợi nền và enqueue khi tải tài liệu (G4T-69, G4T-70, G4T-71)."""
import hashlib
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main, safety
from app.db import Base
from app.errors import ApiError
from app.jobs import JobStatus
from app.models import Batch, Client, Document, ProcessingJob
from app.states import State
from app.storage import LocalWriteOnceStore
from app.worker import process_one

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HSoThueDTu><HSoKhaiThue><TTinChung><TTinTKhaiThue><TKhaiThue><maTKhai>01/GTGT</maTKhai></TKhaiThue></TTinTKhaiThue></TTinChung></HSoKhaiThue></HSoThueDTu>
"""


def _setup_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(bind=engine, expire_on_commit=False)
    store = LocalWriteOnceStore(str(tmp_path / "originals"))

    with SessionTesting() as db:
        client = Client(name="Cong ty Test", tax_id="0101234567")
        db.add(client)
        db.flush()
        batch = Batch(client_id=client.id, engagement_id="ENG-2026", created_by="thuan")
        db.add(batch)
        db.commit()
        client_id, batch_id = client.id, batch.id

    user = SimpleNamespace(name="thuan")
    return SessionTesting, store, client_id, batch_id, user


def test_eligible_upload_enqueues_job_without_blocking(tmp_path, monkeypatch):
    SessionTesting, store, _, batch_id, user = _setup_env(tmp_path)
    monkeypatch.setattr(main, "store", store)

    digest = hashlib.sha256(SAMPLE_XML).hexdigest()
    verdict = safety.inspect("to_khai.xml", SAMPLE_XML)

    with SessionTesting() as db:
        batch = db.get(Batch, batch_id)
        resp = main._accept(db, batch, user, "idem-1", "to_khai.xml", SAMPLE_XML, digest, len(SAMPLE_XML), verdict)
        assert resp.status_code == 201

    with SessionTesting() as db:
        jobs_list = db.scalars(select(ProcessingJob)).all()
        assert len(jobs_list) == 1
        job = jobs_list[0]
        assert job.status == JobStatus.QUEUED
        assert job.attempt_no == 1
        assert job.input_sha256 == digest
        assert job.correlation_id


def test_quarantined_or_rejected_upload_does_not_enqueue(tmp_path, monkeypatch):
    SessionTesting, store, _, batch_id, user = _setup_env(tmp_path)
    monkeypatch.setattr(main, "store", store)

    bad_data = b"not-a-valid-tax-file"
    digest = hashlib.sha256(bad_data).hexdigest()

    with SessionTesting() as db:
        batch = db.get(Batch, batch_id)
        q_verdict = safety.Verdict(False, quarantine=True, reason="encrypted_pdf")
        with pytest.raises(ApiError):
            main._accept(db, batch, user, "idem-q", "locked.pdf", bad_data, digest, len(bad_data), q_verdict)

        r_verdict = safety.Verdict(False, quarantine=False, reason="unsupported_media_type")
        with pytest.raises(ApiError):
            main._accept(db, batch, user, "idem-r", "bad.exe", bad_data, digest, len(bad_data), r_verdict)

    with SessionTesting() as db:
        assert db.scalars(select(ProcessingJob)).all() == []


def test_duplicate_upload_does_not_create_duplicate_job(tmp_path, monkeypatch):
    SessionTesting, store, _, batch_id, user = _setup_env(tmp_path)
    monkeypatch.setattr(main, "store", store)

    digest = hashlib.sha256(SAMPLE_XML).hexdigest()
    verdict = safety.inspect("to_khai.xml", SAMPLE_XML)

    with SessionTesting() as db:
        batch = db.get(Batch, batch_id)
        main._accept(db, batch, user, "idem-1", "to_khai.xml", SAMPLE_XML, digest, len(SAMPLE_XML), verdict)
        resp_dup = main._accept(db, batch, user, "idem-2", "to_khai_copy.xml", SAMPLE_XML, digest, len(SAMPLE_XML), verdict)
        assert resp_dup.status_code == 200

    with SessionTesting() as db:
        assert len(db.scalars(select(ProcessingJob)).all()) == 1


def test_worker_processes_queued_job_and_verifies_original(tmp_path, monkeypatch):
    SessionTesting, store, _, batch_id, user = _setup_env(tmp_path)
    monkeypatch.setattr(main, "store", store)

    digest = hashlib.sha256(SAMPLE_XML).hexdigest()
    verdict = safety.inspect("to_khai.xml", SAMPLE_XML)

    with SessionTesting() as db:
        batch = db.get(Batch, batch_id)
        main._accept(db, batch, user, "idem-1", "to_khai.xml", SAMPLE_XML, digest, len(SAMPLE_XML), verdict)

    processed_id = process_one(SessionTesting, store, worker_id="test-worker")
    assert processed_id is not None

    with SessionTesting() as db:
        job = db.get(ProcessingJob, processed_id)
        doc = db.get(Document, job.document_id)
        assert job.status == JobStatus.SUCCEEDED
        assert job.processor_version is not None
        # Hành vi tạm ở G4T-69; sẽ cập nhật khi G4T-70 gắn logic chuyển trạng thái tài liệu
        assert doc.status == State.RECEIVED


def test_worker_moves_tampered_original_to_dead_letter(tmp_path, monkeypatch):
    SessionTesting, store, _, batch_id, user = _setup_env(tmp_path)
    monkeypatch.setattr(main, "store", store)

    digest = hashlib.sha256(SAMPLE_XML).hexdigest()
    verdict = safety.inspect("to_khai.xml", SAMPLE_XML)

    with SessionTesting() as db:
        batch = db.get(Batch, batch_id)
        main._accept(db, batch, user, "idem-1", "to_khai.xml", SAMPLE_XML, digest, len(SAMPLE_XML), verdict)

    stored_files = [p for p in (tmp_path / "originals").rglob("*") if p.is_file()]
    assert len(stored_files) == 1
    os.chmod(stored_files[0], 0o644)
    stored_files[0].write_bytes(b"tampered-content")

    processed_id = process_one(SessionTesting, store, worker_id="test-worker")
    assert processed_id is not None

    with SessionTesting() as db:
        job = db.get(ProcessingJob, processed_id)
        assert job.status == JobStatus.DEAD_LETTER
        assert job.last_error_code == "original_tampered"
