import re

from app.models import NormalizedDocument, RawDocument, text_sha256
from normalization.base import BaseNormalizer
from normalization.language import LightweightLanguageDetector


class BasicTextNormalizer(BaseNormalizer):
    def __init__(self, detector: LightweightLanguageDetector | None = None) -> None:
        self._detector = detector or LightweightLanguageDetector()

    @property
    def name(self) -> str:
        return "basic"

    def normalize(self, raw_document: RawDocument) -> NormalizedDocument:
        text = raw_document.raw_text
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        text = self._normalize_whitespace(text)
        language = self._detector.detect(text)
        normalized_checksum = text_sha256(text)
        return NormalizedDocument(
            document_id=raw_document.document_id,
            source_type=raw_document.source_type,
            source_uri=raw_document.source_uri,
            normalized_text=text,
            checksum=normalized_checksum,
            language=language,
            normalization_version="basic-v1",
        )

    def _normalize_whitespace(self, text: str) -> str:
        lines = text.split("\n")
        cleaned = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
        joined = "\n".join(cleaned)
        # Collapse 3+ consecutive blank lines to a max of 2.
        return re.sub(r"\n{3,}", "\n\n", joined).strip()
