"""Normalizacao deterministica de nomes publicos do LiberRotas."""

from __future__ import annotations

import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_NON_NAME = re.compile(r"[^a-z0-9 ]+")
_RESERVED_NAMES = frozenset(
    {
        "admin",
        "administrador",
        "administracao",
        "equipe liberrotas",
        "liberrotas",
        "seguranca",
        "security",
        "suporte",
        "suporte liberrotas",
        "support",
    }
)


def normalize_display_name(value: str) -> str:
    """Remove acentos, uniformiza caixa/espacos e elimina pontuacao enganosa."""

    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    folded = without_marks.casefold().replace("_", " ").replace("-", " ")
    return _WHITESPACE.sub(" ", _NON_NAME.sub("", folded)).strip()


def is_reserved_display_name(normalized_name: str) -> bool:
    if normalized_name in _RESERVED_NAMES:
        return True
    words = set(normalized_name.split())
    return "liberrotas" in words and bool(
        words.intersection({"admin", "administrador", "seguranca", "security", "suporte", "support"})
    )
