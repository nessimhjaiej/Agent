from dataclasses import replace
from pathlib import Path

from app.models import ChunkRecord, NormalizedDocument, RawDocument
from metadata.base import BaseMetadataBuilder


class DefaultMetadataBuilder(BaseMetadataBuilder):
    def __init__(self, pipeline_version: str = "v1") -> None:
        self._pipeline_version = pipeline_version

    def enrich(
        self,
        chunks: list[ChunkRecord],
        normalized_document: NormalizedDocument,
        raw_document: RawDocument | None = None,
    ) -> list[ChunkRecord]:
        source_filename = Path(normalized_document.source_uri).name
        checksum = normalized_document.checksum
        enriched: list[ChunkRecord] = []

        for chunk in chunks:
            updated_metadata = replace(
                chunk.metadata,
                source_filename=source_filename,
                document_checksum=checksum,
                normalization_version=normalized_document.normalization_version,
                pipeline_version=self._pipeline_version,
            )
            enriched.append(
                replace(
                    chunk,
                    metadata=updated_metadata,
                )
            )
        return enriched

