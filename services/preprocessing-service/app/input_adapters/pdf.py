from pathlib import Path

from app.input_adapters.base import BaseInputAdapter
from app.models import RawDocument, text_sha256


class PdfInputAdapter(BaseInputAdapter):
    @property
    def name(self) -> str:
        return "pdf"

    def load(self, source_path: str) -> RawDocument:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "pypdf is required for PDF ingestion. Install with: pip install pypdf"
            ) from exc

        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")

        raw_text = "\n\n".join(pages)
        checksum = text_sha256(raw_text)
        document_id = f"{path.stem}-{checksum[:12]}"
        return RawDocument(
            document_id=document_id,
            source_type="pdf",
            source_uri=str(path),
            raw_text=raw_text,
            checksum=checksum,
        )

