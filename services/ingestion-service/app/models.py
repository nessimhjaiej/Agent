from dataclasses import dataclass


@dataclass(slots=True)
class DocumentRecord:
    id: str
    user_id: str
    original_name: str
    storage_path: str
    status: str
    embedded: bool
    size_bytes: int
    created_at: str
    embedded_at: str | None = None


@dataclass(slots=True)
class UploadDocumentParams:
    user_id: str
    original_name: str
    content: bytes
    content_type: str
    size_bytes: int


@dataclass(slots=True)
class UpdateDocumentStatusParams:
    document_id: str
    target_status: str


@dataclass(slots=True)
class SignedUrlResult:
    document_id: str
    storage_path: str
    signed_url: str
    expires_in: int


@dataclass(slots=True)
class DeleteDocumentResult:
    status: str
    document_id: str
    storage_path: str
