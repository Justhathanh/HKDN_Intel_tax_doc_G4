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


class RetryPolicyOut(BaseModel):
    default_max_attempts: int
    backoff_base_seconds: int
    backoff_max_seconds: int
    default_lease_seconds: int
    retryable_errors: list[str]
    non_retryable_errors: list[str]


class JobOut(BaseModel):
    job_id: str
    client_id: str
    document_id: str
    job_type: str
    status: str
    attempt_no: int
    max_attempts: int
    retry_of_job_id: str | None
    correlation_id: str
    input_sha256: str
    processor_version: str | None
    created_at: str
    next_attempt_at: str
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    error_retryable: bool | None


class JobHistoryOut(BaseModel):
    document_id: str
    total_attempts: int
    current_status: str | None
    items: list[JobOut]


class DeadLetterListOut(BaseModel):
    total: int
    items: list[JobOut]
