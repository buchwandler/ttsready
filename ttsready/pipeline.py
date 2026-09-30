"""TTS preparation pipeline."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .models import ConversionResult, Document, OutputFormat, PreparedParagraph
from .readers import load
from .writers import render

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n+")
_INLINE_LINE_BREAK = re.compile(r"[ \t]*\n[ \t]*")


def source_paragraphs(text: str) -> list[str]:
    """Return prose paragraphs while joining soft line wraps inside a paragraph."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs: list[str] = []
    for block in _PARAGRAPH_BREAK.split(normalized):
        paragraph = _INLINE_LINE_BREAK.sub(" ", block).strip()
        paragraph = re.sub(r"[ \t]{2,}", " ", paragraph)
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def _spoken(text: str, *, language: str, enabled: bool) -> tuple[str, list[str]]:
    if not enabled:
        return text.strip(), []
    from spokenform import prepare as prepare_spokenform

    result = prepare_spokenform(text, language=language, use_spacy=False)
    return result.spoken_text.strip(), list(result.warnings)


def _split_oversized(text: str, *, max_chars: int | None, language: str) -> list[str]:
    if not text:
        return []
    if max_chars is None or len(text) <= max_chars:
        return [text]
    if max_chars < 1:
        raise ValueError("max_paragraph_chars must be at least 1")

    from phrasplit import split_long_lines

    parts = split_long_lines(
        text,
        max_length=max_chars,
        use_spacy=False,
        language=language,
    )
    return [part.strip() for part in parts if part.strip()]


def _iter_section_inputs(document: Document, include_titles: bool) -> Iterable[tuple[str, int, bool, str]]:
    for section in document.sections:
        if include_titles and section.title and section.title.strip():
            yield section.id, -1, True, section.title.strip()
        for index, paragraph in enumerate(source_paragraphs(section.text)):
            yield section.id, index, False, paragraph


def prepare(
    document: Document,
    *,
    output_format: OutputFormat = "txt",
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
) -> ConversionResult:
    """Prepare a loaded document for TTS and render it."""
    if output_format not in {"txt", "ssmd"}:
        raise ValueError(f"Unsupported output format: {output_format!r}")
    if max_paragraph_chars is not None and max_paragraph_chars < 1:
        raise ValueError("max_paragraph_chars must be at least 1")

    selected_language = str(language or document.metadata.get("language") or "en")
    prepared: list[PreparedParagraph] = []
    warnings: list[str] = []

    for section_id, source_index, is_title, raw in _iter_section_inputs(document, include_titles):
        spoken, spoken_warnings = _spoken(
            raw,
            language=selected_language,
            enabled=apply_spokenform,
        )
        warnings.extend(spoken_warnings)
        for part_index, part in enumerate(
            _split_oversized(
                spoken,
                max_chars=max_paragraph_chars,
                language=selected_language,
            )
        ):
            prepared.append(
                PreparedParagraph(
                    text=part,
                    section_id=section_id,
                    source_paragraph=source_index,
                    part=part_index,
                    is_title=is_title,
                )
            )

    rendered = render(
        output_format,
        prepared,
        metadata=document.metadata,
        language=selected_language,
    )
    return ConversionResult(
        document=document,
        paragraphs=prepared,
        text=rendered,
        output_format=output_format,
        language=selected_language,
        warnings=warnings,
    )


def convert(
    source: str | Path,
    *,
    output_format: OutputFormat = "txt",
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
) -> ConversionResult:
    """Load, prepare, and render one supported document."""
    document = load(source)
    return prepare(
        document,
        output_format=output_format,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        apply_spokenform=apply_spokenform,
        include_titles=include_titles,
    )
