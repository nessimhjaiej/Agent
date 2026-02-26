from pathlib import Path

from app.input_adapters.base import BaseInputAdapter
from app.input_adapters.pdf import PdfInputAdapter
from app.input_adapters.text import TextInputAdapter


class InputAdapterFactory:
    _registry: dict[str, type[BaseInputAdapter]] = {
        "pdf": PdfInputAdapter,
        "txt": TextInputAdapter,
        "md": TextInputAdapter,
        "text": TextInputAdapter,
    }

    @classmethod
    def create(cls, source_type: str) -> BaseInputAdapter:
        key = source_type.strip().lower()
        adapter_cls = cls._registry.get(key)
        if not adapter_cls:
            supported = ", ".join(sorted(cls._registry))
            raise ValueError(f"Unknown source type '{source_type}'. Supported: {supported}")
        return adapter_cls()

    @classmethod
    def infer_source_type(cls, source_path: str) -> str:
        suffix = Path(source_path).suffix.lstrip(".").lower()
        if not suffix:
            return "text"
        return suffix

