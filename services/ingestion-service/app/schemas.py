from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    service: str
    version: str


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    original_name: str
    storage_path: str
    status: str
    embedded: bool
    size_bytes: int
    created_at: str
    embedded_at: str | None = None


class ListDocumentsResponse(BaseModel):
    status: str = "ok"
    documents: list[DocumentResponse]


class UpdateDocumentStatusRequest(BaseModel):
    target_status: str = Field(..., pattern="^(pending|validated|rejected)$")


class SignedUrlResponse(BaseModel):
    status: str = "ok"
    document_id: str
    storage_path: str
    signed_url: str
    expires_in: int


class DeleteDocumentResponse(BaseModel):
    status: str
    document_id: str
    storage_path: str
