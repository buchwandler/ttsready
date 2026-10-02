"""Canonical SSMD preparation, review, and text export."""

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
from .input import load, load_ssmd
from .models import (
    ContextRecord,
    ConversionReport,
    ConversionResult,
    Document,
    NormalizationProfile,
    PreparedParagraph,
    PreparedSegment,
    RenderOptions,
    Section,
    SectionStats,
    SourceInfo,
    SpokenChange,
    SpokenformStats,
    TTSPlan,
)
from .pipeline import convert, prepare, prepare_tts_plan, source_paragraphs
from .planning import render_preview
from .selection import parse_section_range

__all__ = [
    "ConversionResult",
    "Document",
    "ContextRecord",
    "ConversionReport",
    "PreparedParagraph",
    "PreparedSegment",
    "RenderOptions",
    "NormalizationProfile",
    "SectionStats",
    "SpokenChange",
    "SpokenformStats",
    "Section",
    "TTSPlan",
    "SourceInfo",
    "TTSReadyError",
    "UnsupportedInputError",
    "__version__",
    "convert",
    "load",
    "load_ssmd",
    "prepare",
    "prepare_tts_plan",
    "render_preview",
    "source_paragraphs",
    "parse_section_range",
]
