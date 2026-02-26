from app.models import ChunkMetadata, ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.base import BaseChunker


class OverlapChunker(BaseChunker):
    @property
    def name(self) -> str:
        return "overlap"

    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        if context.chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if context.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if context.chunk_overlap >= context.chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")

        text = document.normalized_text
        if not text:
            return []

        step = context.chunk_size - context.chunk_overlap
        chunks: list[ChunkRecord] = []
        start = 0
        index = 0

        while start < len(text):
            end = min(start + context.chunk_size, len(text))
            chunk_text = text[start:end]
            token_count_estimate = len(chunk_text.split())
            metadata = ChunkMetadata(
                source_type=document.source_type,
                source_uri=document.source_uri,
                language=document.language,
                chunk_index=index,
                start_char=start,
                end_char=end,
                char_count=len(chunk_text),
                token_count_estimate=token_count_estimate,
                chunking_strategy=self.name,
                source_filename=document.source_uri.split("/")[-1].split("\\")[-1],
                document_checksum=document.checksum,
                normalization_version=document.normalization_version,
            )
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{document.document_id}:{index}",
                    document_id=document.document_id,
                    chunk_text=chunk_text,
                    metadata=metadata,
                )
            )
            if end == len(text):
                break
            start += step
            index += 1

        return chunks
