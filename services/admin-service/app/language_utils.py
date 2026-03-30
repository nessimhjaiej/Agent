from __future__ import annotations

import re
import unicodedata


_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_TOKEN_RE = re.compile(r"[a-zA-Z\u00C0-\u024F']+")

_LANGUAGE_MARKERS: dict[str, set[str]] = {
    "en": {
        "the", "what", "how", "why", "current", "show", "explain", "change", "apply",
        "which", "should", "system", "status", "options", "current", "please",
    },
    "fr": {
        "le", "la", "les", "des", "une", "un", "que", "quoi", "comment", "pourquoi",
        "quel", "quelle", "quelles", "actuel", "actuelle", "strategie", "decoupage",
        "configuration", "changer", "appliquer", "cout", "sans", "avec",
    },
    "es": {
        "el", "la", "los", "las", "que", "como", "por", "para", "actual", "configuracion",
        "cambiar", "aplicar", "opciones", "estrategia",
    },
    "pt": {
        "o", "a", "os", "as", "que", "como", "para", "atual", "configuracao", "mudar",
        "aplicar", "opcoes", "estrategia",
    },
    "de": {
        "der", "die", "das", "wie", "was", "warum", "aktuell", "konfiguration", "andern",
        "anwenden", "optionen", "strategie",
    },
    "it": {
        "il", "lo", "la", "gli", "come", "cosa", "perche", "attuale", "configurazione",
        "cambiare", "applicare", "opzioni", "strategia",
    },
}

_ACCENT_HINTS: dict[str, tuple[str, ...]] = {
    "fr": ("é", "è", "ê", "à", "ç", "ù", "œ"),
    "es": ("ñ", "á", "í", "ó", "ú", "¿", "¡"),
    "pt": ("ã", "õ", "ç", "á", "ê", "ô"),
    "de": ("ä", "ö", "ü", "ß"),
    "it": ("à", "è", "é", "ì", "ò", "ù"),
}


def detect_language(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "unknown"
    if _ARABIC_RE.search(raw):
        return "ar"

    lowered = raw.lower()
    tokens = _TOKEN_RE.findall(lowered)
    if not tokens:
        return "unknown"

    scores: dict[str, int] = {lang: 0 for lang in _LANGUAGE_MARKERS}
    for token in tokens:
        normalized = unicodedata.normalize("NFKC", token)
        for lang, markers in _LANGUAGE_MARKERS.items():
            if normalized in markers:
                scores[lang] += 2

    for lang, hints in _ACCENT_HINTS.items():
        for hint in hints:
            if hint in lowered:
                scores[lang] += 1

    best_language = max(scores, key=scores.get)
    if scores[best_language] <= 0:
        return "en"
    return best_language
