"""Document-to-TTS text preparation."""

from __future__ import annotations

try:
    from ._version import version as __version__
except (ImportError, AttributeError):
    try:
        from importlib.metadata import version

        __version__ = version("ttsready")
    except Exception:  # pragma: no cover - bare source tree
        __version__ = "0.1.0.dev0"

from .errors import TTSReadyError, UnsupportedInputError
from .models import (
    ConversionReport,
    ConversionResult,
    Document,
    PreparedParagraph,
    RenderOptions,
    Section,
    SectionStats,
    SourceInfo,
    SpokenChange,
    SpokenformStats,
)
from .pipeline import convert, prepare, source_paragraphs
from .readers import load, reader_for
from .selection import parse_section_range

__all__ = [
    "ConversionResult",
    "Document",
    "ConversionReport",
    "PreparedParagraph",
    "RenderOptions",
    "SectionStats",
    "SpokenChange",
    "SpokenformStats",
    "Section",
    "SourceInfo",
    "TTSReadyError",
    "UnsupportedInputError",
    "__version__",
    "convert",
    "load",
    "prepare",
    "reader_for",
    "source_paragraphs",
    "parse_section_range",
]
