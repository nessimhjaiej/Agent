from app.input_adapters.factory import InputAdapterFactory
from app.models import ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.factory import ChunkerFactory
from metadata.builder import DefaultMetadataBuilder
from normalization.basic import BasicTextNormalizer


class PreprocessingOrchestrator:
    def __init__(
        self,
        chunk_strategy: str = "overlap",
        pipeline_version: str = "v1",
    ) -> None:
        self._chunker = ChunkerFactory.create(chunk_strategy)
        self._normalizer = BasicTextNormalizer()
        self._metadata_builder = DefaultMetadataBuilder(pipeline_version=pipeline_version)

    @property
    def chunker_name(self) -> str:
        return self._chunker.name

    def process_source(
        self,
        source_path: str,
        source_type: str | None = None,
        context: ChunkingContext | None = None,
    ) -> list[ChunkRecord]:
        resolved_source_type = source_type or InputAdapterFactory.infer_source_type(source_path)
        adapter = InputAdapterFactory.create(resolved_source_type)
        raw_document = adapter.load(source_path)
        normalized_document = self._normalizer.normalize(raw_document)
        chunking_context = context or ChunkingContext()
        chunks = self._chunker.chunk(normalized_document, chunking_context)
        return self._metadata_builder.enrich(chunks, normalized_document, raw_document)

    def process_document(
        self, document: NormalizedDocument, context: ChunkingContext | None = None
    ) -> list[ChunkRecord]:
        chunking_context = context or ChunkingContext()
        chunks = self._chunker.chunk(document, chunking_context)
        return self._metadata_builder.enrich(chunks, document)
