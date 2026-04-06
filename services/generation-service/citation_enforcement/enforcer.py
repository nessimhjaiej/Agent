from app.errors import GenerationValidationError
from app.models import Citation, RetrievedChunk


class CitationEnforcer:
    def __init__(self, require_citations: bool = True, strict_validation: bool = True) -> None:
        self._require_citations = require_citations
        self._strict_validation = strict_validation

    def enforce(self, raw_citation_ids: list[str], chunks_by_id: dict[str, RetrievedChunk]) -> list[Citation]:
        valid_ids: list[str] = []
        unknown_ids: list[str] = []
        for chunk_id in raw_citation_ids:
            if chunk_id in chunks_by_id:
                if chunk_id not in valid_ids:
                    valid_ids.append(chunk_id)
            elif chunk_id not in unknown_ids:
                unknown_ids.append(chunk_id)

        if unknown_ids and self._strict_validation:
            raise GenerationValidationError(
                f"Model produced unknown citation ids: {', '.join(unknown_ids)}"
            )

        if self._require_citations and not valid_ids:
            raise GenerationValidationError("Model response must cite at least one valid chunk_id")

        return [
            Citation(
                chunk_id=chunk_id,
                document_id=chunks_by_id[chunk_id].document_id,
                document_name=chunks_by_id[chunk_id].document_name,
                chunk_text=chunks_by_id[chunk_id].chunk_text,
                storage_path=self._extract_storage_path(chunks_by_id[chunk_id]),
            )
            for chunk_id in valid_ids
        ]

    @staticmethod
    def _extract_storage_path(chunk: RetrievedChunk) -> str | None:
        source_uri = chunk.metadata.get("source_uri")
        if not isinstance(source_uri, str) or not source_uri.strip():
            return None

        normalized = source_uri.replace("\\", "/")
        marker = "/supabase/"
        marker_index = normalized.rfind(marker)
        if marker_index == -1:
            return None

        storage_path = normalized[marker_index + len(marker):].strip("/")
        return storage_path or None
