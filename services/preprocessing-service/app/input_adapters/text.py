from pathlib import Path

from app.input_adapters.base import BaseInputAdapter
from app.models import RawDocument, text_sha256


class TextInputAdapter(BaseInputAdapter):
    @property
    def name(self) -> str:
        return "text"

    def load(self, source_path: str) -> RawDocument:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = path.read_text(encoding="latin-1")

        checksum = text_sha256(raw_text)
        document_id = f"{path.stem}-{checksum[:12]}"
        return RawDocument(
            document_id=document_id,
            source_type=path.suffix.lstrip(".").lower() or "text",
            source_uri=str(path),
            raw_text=raw_text,
            checksum=checksum,
        )

