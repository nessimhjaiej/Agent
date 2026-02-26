from app.config import Settings
from app.models import ChunkRecord, ChunkingContext
from app.orchestrator import PreprocessingOrchestrator


class PreprocessingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def process_source(
        self,
        source_path: str,
        source_type: str | None = None,
        chunk_strategy: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[ChunkRecord]:
        strategy = chunk_strategy or self._settings.chunk_strategy
        context = ChunkingContext(
            chunk_size=chunk_size or self._settings.chunk_size,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else self._settings.chunk_overlap,
        )
        orchestrator = PreprocessingOrchestrator(
            chunk_strategy=strategy,
            pipeline_version=self._settings.pipeline_version,
        )
        return orchestrator.process_source(
            source_path=source_path,
            source_type=source_type,
            context=context,
        )

