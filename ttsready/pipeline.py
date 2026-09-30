"""TTS preparation pipeline."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .models import (
    ConversionReport,
    ConversionResult,
    Document,
    OutputFormat,
    PreparedParagraph,
    RenderOptions,
    SectionStats,
    SpokenChange,
    SpokenformStats,
)
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


@dataclass(frozen=True, slots=True)
class SpokenOutcome:
    text: str
    warnings: tuple[str, ...]
    changed: bool
    stage_edit_counts: dict[str, int]
    changes: tuple[SpokenChange, ...]


def _spoken(
    text: str,
    *,
    language: str,
    enabled: bool,
    section_id: str,
    section_index: int,
    source_paragraph: int,
) -> SpokenOutcome:
    if not enabled:
        return SpokenOutcome(text.strip(), (), False, {}, ())
    from spokenform import prepare as prepare_spokenform

    prepared = prepare_spokenform(text, language=language, use_spacy=False)
    stage_edit_counts: dict[str, int] = {}
    for stage in prepared.stages:
        stage_edit_counts[stage.name] = stage_edit_counts.get(stage.name, 0) + len(
            stage.mapped_edits
        )
    changes = tuple(
        SpokenChange(
            section_id=section_id,
            section_index=section_index,
            source_paragraph=source_paragraph,
            source=replacement.source,
            replacement=replacement.replacement,
            stages=tuple(replacement.stages),
            kind=replacement.kind,
            rule=replacement.rule,
            recognition_domain=replacement.recognition_domain,
            source_start=replacement.source_start,
            source_end=replacement.source_end,
            output_start=replacement.output_start,
            output_end=replacement.output_end,
        )
        for replacement in prepared.source_replacements
    )
    spoken_text = prepared.spoken_text.strip()
    return SpokenOutcome(
        text=spoken_text,
        warnings=tuple(prepared.warnings),
        changed=spoken_text != text.strip(),
        stage_edit_counts=stage_edit_counts,
        changes=changes,
    )



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


def _iter_section_inputs(
    document: Document, include_titles: bool
) -> Iterable[tuple[str, int, int, bool, str]]:
    for output_index, section in enumerate(document.sections, start=1):
        section_index = section.source_index or output_index
        if include_titles and section.title and section.title.strip():
            yield section.id, section_index, -1, True, section.title.strip()
        for index, paragraph in enumerate(source_paragraphs(section.text)):
            yield section.id, section_index, index, False, paragraph


def prepare(
    document: Document,
    *,
    output_format: OutputFormat = "txt",
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
    render_options: RenderOptions | None = None,
) -> ConversionResult:
    """Prepare a loaded document for TTS and render it."""
    if output_format not in {"txt", "ssmd"}:
        raise ValueError(f"Unsupported output format: {output_format!r}")
    if max_paragraph_chars is not None and max_paragraph_chars < 1:
        raise ValueError("max_paragraph_chars must be at least 1")

    metadata_language = document.metadata.get("language")
    selected_language = str(language or metadata_language or "en")
    requested_language = str(language) if language is not None else None
    section_stats = [
        SectionStats(
            section_id=section.id,
            index=section.source_index or index,
            title=section.title,
            level=section.level,
            input_chars=len(section.text),
            source_paragraphs=len(source_paragraphs(section.text)),
        )
        for index, section in enumerate(document.sections, start=1)
    ]
    section_stats_by_id = {item.section_id: item for item in section_stats}
    report = ConversionReport(
        source_path=str(document.source.path),
        input_format=document.source.format,
        document_title=(
            str(document.metadata["title"]) if document.metadata.get("title") is not None else None
        ),
        metadata_language=str(metadata_language) if metadata_language is not None else None,
        requested_language=requested_language,
        effective_language=selected_language,
        output_format=output_format,
        total_sections=document.original_section_count or len(document.sections),
        selected_sections=len(document.sections),
        input_chars=sum(len(section.text) for section in document.sections),
        source_paragraphs=sum(item.source_paragraphs for item in section_stats),
        sections=section_stats,
    )
    prepared: list[PreparedParagraph] = []
    spokenform_stats: SpokenformStats = report.spokenform

    for section_id, section_index, source_index, is_title, raw in _iter_section_inputs(
        document, include_titles
    ):
        outcome = _spoken(
            raw,
            language=selected_language,
            enabled=apply_spokenform,
            section_id=section_id,
            section_index=section_index,
            source_paragraph=source_index,
        )
        spokenform_stats.paragraphs_processed += 1
        if apply_spokenform:
            spokenform_stats.calls += 1
        if outcome.changed:
            spokenform_stats.changed_calls += 1
            spokenform_stats.paragraphs_changed += 1
        spokenform_stats.warnings += len(outcome.warnings)
        report.warnings.extend(outcome.warnings)
        for stage, count in outcome.stage_edit_counts.items():
            spokenform_stats.stage_edits[stage] = (
                spokenform_stats.stage_edits.get(stage, 0) + count
            )
        section_stats_by_id[section_id].spokenform_changes += len(outcome.changes)
        for change in outcome.changes:
            report.changes.append(change)
            if change.rule:
                spokenform_stats.rules[change.rule] = (
                    spokenform_stats.rules.get(change.rule, 0) + 1
                )
            if change.recognition_domain:
                spokenform_stats.domains[change.recognition_domain] = (
                    spokenform_stats.domains.get(change.recognition_domain, 0) + 1
                )
            contains_digit = any(char.isdecimal() for char in change.source)
            if contains_digit:
                spokenform_stats.source_digit_replacements += 1
                if "structured" in change.stages:
                    spokenform_stats.structured_numeric_edits += 1
        spokenform_stats.source_replacements += len(outcome.changes)

        report.source_prepared_items += 1
        parts = _split_oversized(
            outcome.text,
            max_chars=max_paragraph_chars,
            language=selected_language,
        )
        if len(parts) > 1:
            report.split_source_items += 1
        report.added_split_parts += max(0, len(parts) - 1)
        for part_index, part in enumerate(parts):
            prepared.append(
                PreparedParagraph(
                    text=part,
                    section_id=section_id,
                    source_paragraph=source_index,
                    part=part_index,
                    is_title=is_title,
                )
            )
            report.prepared_paragraphs += 1
            report.max_prepared_paragraph_chars = max(
                report.max_prepared_paragraph_chars, len(part)
            )
            section_stats_by_id[section_id].prepared_paragraphs += 1
            section_stats_by_id[section_id].output_chars += len(part)

    rendered = render(
        output_format,
        prepared,
        metadata=document.metadata,
        language=selected_language,
        options=render_options or RenderOptions(),
    )
    report.output_chars = len(rendered)
    report.output_lines = len(rendered.splitlines())
    return ConversionResult(
        document=document,
        paragraphs=prepared,
        text=rendered,
        output_format=output_format,
        language=selected_language,
        warnings=report.warnings,
        report=report,
    )


def convert(
    source: str | Path,
    *,
    output_format: OutputFormat = "txt",
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
    render_options: RenderOptions | None = None,
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
        render_options=render_options,
    )
