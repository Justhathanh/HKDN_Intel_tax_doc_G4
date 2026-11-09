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
