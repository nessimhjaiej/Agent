"""Language detection used to tag chunks (returns an ISO code or "und")."""

import re
from abc import ABC, abstractmethod


class BaseLanguageDetector(ABC):
    """Interface: map text to a language code (or "und" when unknown)."""

    @abstractmethod
    def detect(self, text: str) -> str:
        raise NotImplementedError


class LightweightLanguageDetector(BaseLanguageDetector):
    """`langdetect` when available, with a regex/stop-word heuristic fallback."""

    def __init__(self, min_chars: int = 50, min_confidence: float = 0.65) -> None:
        self._min_chars = min_chars
        self._min_confidence = min_confidence

    def detect(self, text: str) -> str:
        """Return an ISO code; "und" if the text is too short or confidence is low."""
        cleaned = text.strip()
        if len(cleaned) < self._min_chars:
            return "und"

        detected = self._detect_with_langdetect(cleaned)
        if detected:
            return detected

        return self._heuristic_detect(cleaned)

    def _detect_with_langdetect(self, text: str) -> str | None:
        """Try the `langdetect` library; None if unavailable, "und" if low-confidence."""
        try:
            from langdetect import DetectorFactory, detect_langs
        except ImportError:
            return None

        try:
            DetectorFactory.seed = 0
            guesses = detect_langs(text)
            if not guesses:
                return None
            top = guesses[0]
            if top.prob < self._min_confidence:
                return "und"
            return str(top.lang).lower()
        except Exception:
            return None

    def _heuristic_detect(self, text: str) -> str:
        """Fallback: Arabic vs Latin script, then French/English stop-word counts."""
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        latin_chars = len(re.findall(r"[A-Za-z]", text))
        if arabic_chars > latin_chars:
            return "ar"
        if latin_chars == 0:
            return "und"

        lowered = f" {text.lower()} "
        fr_markers = [" le ", " la ", " les ", " des ", " une ", " et ", " est "]
        en_markers = [" the ", " and ", " of ", " to ", " is ", " for ", " in "]
        fr_hits = sum(1 for marker in fr_markers if marker in lowered)
        en_hits = sum(1 for marker in en_markers if marker in lowered)
        if fr_hits > en_hits:
            return "fr"
        if en_hits > 0:
            return "en"
        return "und"

