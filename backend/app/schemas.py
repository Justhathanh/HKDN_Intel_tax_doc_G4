from pydantic import BaseModel


class ClientIn(BaseModel):
    name: str
    tax_id: str


class BatchIn(BaseModel):
    client_id: str
    engagement_id: str


class ClientOut(BaseModel):
    id: str
    name: str
    tax_id: str


class BatchOut(BaseModel):
    id: str
    client_id: str
    engagement_id: str


class ErrorBody(BaseModel):
    error_code: str
    message: str
    submission_id: str | None = None
    document_id: str | None = None


class DocumentReceipt(BaseModel):
    document_id: str
    submission_id: str
    batch_id: str
    file_name: str
    size: int
    sha256: str
    mime_type: str
    page_count: int | None
    channel: str
    uploaded_by: str
    status: str
    duplicate: bool
    received_at: str


class DocumentOut(BaseModel):
    document_id: str
    batch_id: str
    file_name: str
    size: int
    sha256: str
    mime_type: str
    page_count: int | None
    status: str
    uploaded_by: str
    received_at: str


class ManifestItem(BaseModel):
    submission_id: str
    file_name: str
    size: int
    sha256: str | None
    outcome: str
    reason: str | None
    document_id: str | None
    status: str | None
    uploaded_by: str
    received_at: str


class Manifest(BaseModel):
    batch_id: str
    submissions: int
    by_outcome: dict[str, int]
    items: list[ManifestItem]


class JobErrorOut(BaseModel):
    """Lỗi của một lần thử; chỉ gồm mã và câu thông báo trong danh sách cho phép (SEC 04)."""

    code: str
    message: str
    retryable: bool


class JobOut(BaseModel):
    """Trạng thái một lần thử xử lý (G4T-68). Không trả locked_by, lease, input_sha256: đó là dữ liệu nội bộ."""

    job_id: str
    document_id: str
    job_type: str
    status: str
    display_status: str
    will_retry: bool
    attempt_no: int
    max_attempts: int
    retry_of_job_id: str | None
    correlation_id: str
    processor_version: str | None
    created_at: str
    next_attempt_at: str
    started_at: str | None
    finished_at: str | None
    error: JobErrorOut | None


class JobList(BaseModel):
    document_id: str
    latest: JobOut | None
    items: list[JobOut]
