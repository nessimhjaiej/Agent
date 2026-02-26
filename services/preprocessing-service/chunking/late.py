import re
from pathlib import Path

from app.models import ChunkMetadata, ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.base import BaseChunker


class LateChunker(BaseChunker):
    @property
    def name(self) -> str:
        return "late"

    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        base_size = context.chunk_size
        base_overlap = context.chunk_overlap
        if base_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if base_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if base_overlap >= base_size:
            raise ValueError("chunk_overlap must be < chunk_size")

        size_multiplier = float(context.strategy_params.get("late_size_multiplier", 2.0))
        overlap_multiplier = float(context.strategy_params.get("late_overlap_multiplier", 2.0))
        effective_size = max(int(base_size * size_multiplier), base_size)
        effective_overlap = min(max(int(base_overlap * overlap_multiplier), base_overlap), effective_size - 1)

        text = document.normalized_text
        if not text:
            return []

        breakpoints = self._collect_breakpoints(text)
        n = len(text)
        chunks: list[ChunkRecord] = []
        start = 0
        index = 0

        while start < n:
            target_end = min(start + effective_size, n)
            end = self._snap_end(breakpoints, start, target_end)
            if end <= start:
                end = target_end
            chunk_text = text[start:end]
            chunks.append(self._build_chunk(document, index, start, end, chunk_text))
            if end == n:
                break

            desired_start = max(end - effective_overlap, 0)
            next_start = self._snap_start(breakpoints, desired_start)
            if next_start >= end:
                next_start = desired_start
            if next_start <= start:
                next_start = min(start + max(1, effective_size - effective_overlap), n)
            start = next_start
            index += 1

        return chunks

    def _collect_breakpoints(self, text: str) -> list[int]:
        points: set[int] = {0, len(text)}
        # prioritize paragraph boundaries for larger windows
        for match in re.finditer(r"\n\s*\n+", text):
            points.add(match.end())
        for match in re.finditer(r"[.!?]+(?:\s+|$)", text):
            points.add(match.end())
        return sorted(points)

    def _snap_end(self, breakpoints: list[int], start: int, target_end: int) -> int:
        candidates = [p for p in breakpoints if start < p <= target_end]
        if candidates:
            return candidates[-1]
        return target_end

    def _snap_start(self, breakpoints: list[int], desired_start: int) -> int:
        candidates = [p for p in breakpoints if p <= desired_start]
        if candidates:
            return candidates[-1]
        return desired_start

    def _build_chunk(
        self,
        document: NormalizedDocument,
        index: int,
        start: int,
        end: int,
        chunk_text: str,
    ) -> ChunkRecord:
        metadata = ChunkMetadata(
            source_type=document.source_type,
            source_uri=document.source_uri,
            language=document.language,
            chunk_index=index,
            start_char=start,
            end_char=end,
            char_count=len(chunk_text),
            token_count_estimate=len(chunk_text.split()),
            chunking_strategy=self.name,
            source_filename=Path(document.source_uri).name,
            document_checksum=document.checksum,
            normalization_version=document.normalization_version,
        )
        return ChunkRecord(
            chunk_id=f"{document.document_id}:{index}",
            document_id=document.document_id,
            chunk_text=chunk_text,
            metadata=metadata,
        )
