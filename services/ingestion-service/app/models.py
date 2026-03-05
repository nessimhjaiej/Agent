from dataclasses import dataclass, field


@dataclass(slots=True)
class IngestionRunParams:
    raw_dir: str
    source_root_in_preprocessing: str
    preprocessing_base_url: str
    embedding_base_url: str
    embedding_batch_size: int
    recursive: bool
    patterns: list[str]
    dry_run: bool = False


@dataclass(slots=True)
class IngestionDocumentResult:
    file_path: str
    source_path: str
    chunks_count: int
    indexed_count: int
    status: str
    error: str | None = None


@dataclass(slots=True)
class IngestionRunResult:
    documents_processed: int
    documents_failed: int
    chunks_total: int
    chunks_indexed: int
    failed_files: list[str]
    results: list[IngestionDocumentResult] = field(default_factory=list)


@dataclass(slots=True)
class IndexDocumentParams:
    source_url: str | None
    source_path: str | None
    target_relative_path: str
    source_root_in_preprocessing: str
    preprocessing_base_url: str
    embedding_base_url: str
    embedding_batch_size: int
    weaviate_http_url: str
    weaviate_collection: str
    skip_if_exists: bool = True


@dataclass(slots=True)
class IndexDocumentResult:
    status: str
    source_path: str
    exists_in_weaviate: bool
    indexed: bool
    chunks_count: int
    indexed_count: int
    message: str | None = None
