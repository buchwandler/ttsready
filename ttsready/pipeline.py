"""TTS preparation pipeline."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .identifiers import change_id, file_sha256, section_locator, stable_id, text_sha256
from .identifiers import context_id as make_context_id
from .models import (
    ContextRecord,
    ConversionReport,
    ConversionResult,
    Document,
    PreparedParagraph,
    RenderOptions,
    Section,
    SectionStats,
    SentenceContext,
    SpokenChange,
    SpokenformStats,
)
from .overrides import apply_overrides, find_overrides
from .readers import load
from .sidecar import Sidecar
from .writers import render_txt

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


@dataclass(frozen=True, slots=True)
class SourceItem:
    section: Section
    section_index: int
    source_paragraph: int
    is_title: bool
    text: str


def _spoken(
    text: str,
    *,
    context_id: str,
    language: str,
    enabled: bool,
    section_id: str,
    section_locator_value: str,
    section_index: int,
    source_paragraph: int,
    sidecar: Sidecar | None,
) -> SpokenOutcome:
    overrides = sidecar.lexicon if sidecar else ()
    matches = find_overrides(
        text,
        overrides,
        context_id=context_id,
        section_id=section_id,
        section_locator=section_locator_value,
    )
    if enabled:
        from spokenform import prepare as prepare_spokenform

        prepared = prepare_spokenform(
            text,
            language=language,
            use_spacy=False,
            protected_spans=tuple((match.start, match.end) for match in matches),
        )
        stage_edit_counts: dict[str, int] = {}
        for stage in prepared.stages:
            stage_edit_counts[stage.name] = stage_edit_counts.get(stage.name, 0) + len(
                stage.mapped_edits
            )
        replacements = prepared.source_replacements
        base_changes = tuple(
            SpokenChange(
                id=change_id(
                    context_id,
                    source_start=replacement.source_start,
                    source_end=replacement.source_end,
                    source=replacement.source,
                ),
                context_id=context_id,
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
            for replacement in replacements
        )
        warnings = tuple(prepared.warnings)
        output_text = prepared.spoken_text.strip()
    else:
        replacements = ()
        base_changes = ()
        stage_edit_counts = {}
        warnings = ()
        output_text = text.strip()

    spoken_text, applied = apply_overrides(output_text, matches, replacements)
    custom_changes = tuple(
        SpokenChange(
            id=change_id(
                context_id,
                source_start=item.match.start,
                source_end=item.match.end,
                source=text[item.match.start : item.match.end],
            ),
            context_id=context_id,
            section_id=section_id,
            section_index=section_index,
            source_paragraph=source_paragraph,
            source=text[item.match.start : item.match.end],
            replacement=item.match.override.spoken,
            stages=("custom",),
            kind=item.match.override.kind,
            rule=f"sidecar:{item.match.override.id}",
            recognition_domain=None,
            source_start=item.match.start,
            source_end=item.match.end,
            output_start=item.output_start,
            output_end=item.output_end,
            provenance=item.match.override.provenance,
        )
        for item in applied
    )
    if applied:
        stage_edit_counts["custom"] = len(applied)
        shifted_changes = []
        for change in base_changes:
            delta = sum(
                len(item.match.override.spoken) - (item.match.end - item.match.start)
                for item in applied
                if item.match.end <= change.source_start
            )
            shifted_changes.append(
                replace(
                    change,
                    output_start=change.output_start + delta,
                    output_end=change.output_end + delta,
                )
            )
        base_changes = tuple(shifted_changes)

    changes = (*base_changes, *custom_changes)
    return SpokenOutcome(
        text=spoken_text,
        warnings=warnings,
        changed=spoken_text != text.strip(),
        stage_edit_counts=stage_edit_counts,
        changes=changes,
    )


def _sentence_contexts(
    context_id: str, text: str, *, kind: str, language: str
) -> tuple[SentenceContext, ...]:
    from phrasplit import split_with_offsets

    segments = split_with_offsets(
        text,
        mode="sentence",
        use_spacy=False,
        language=language,
    )
    return tuple(
        SentenceContext(
            id=stable_id(
                "sent",
                {
                    "context_id": context_id,
                    "kind": kind,
                    "index": index,
                    "start": segment.char_start,
                    "end": segment.char_end,
                    "text": text[segment.char_start : segment.char_end],
                },
            ),
            index=index,
            text=text[segment.char_start : segment.char_end],
            start=segment.char_start,
            end=segment.char_end,
        )
        for index, segment in enumerate(segments)
    )


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in ("ttsready", "spokenform", "phrasplit", "epub2text"):
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            continue
    return versions


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


def _iter_section_inputs(document: Document, include_titles: bool) -> Iterable[SourceItem]:
    for output_index, section in enumerate(document.sections, start=1):
        section_index = section.source_index or output_index
        if include_titles and section.title and section.title.strip():
            yield SourceItem(section, section_index, -1, True, section.title.strip())
        for index, paragraph in enumerate(source_paragraphs(section.text)):
            yield SourceItem(section, section_index, index, False, paragraph)


def prepare(
    document: Document,
    *,
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
    render_options: RenderOptions | None = None,
    sidecar: Sidecar | None = None,
) -> ConversionResult:
    """Prepare a loaded document for TTS and render it."""
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
        total_sections=document.original_section_count or len(document.sections),
        selected_sections=len(document.sections),
        input_chars=sum(len(section.text) for section in document.sections),
        source_paragraphs=sum(item.source_paragraphs for item in section_stats),
        sections=section_stats,
        source_sha256=file_sha256(str(document.source.path)),
        tool_versions=_tool_versions(),
    )
    prepared: list[PreparedParagraph] = []
    spokenform_stats: SpokenformStats = report.spokenform

    duplicate_ordinals: dict[tuple[str, str, str], int] = {}
    for source_item in _iter_section_inputs(document, include_titles):
        section = source_item.section
        section_id = section.id
        section_index = source_item.section_index
        source_index = source_item.source_paragraph
        is_title = source_item.is_title
        raw = source_item.text
        locator = section_locator(section)
        kind = "title" if is_title else "paragraph"
        source_digest = text_sha256(raw)
        duplicate_key = (locator, kind, source_digest)
        duplicate_ordinal = duplicate_ordinals.get(duplicate_key, 0)
        duplicate_ordinals[duplicate_key] = duplicate_ordinal + 1
        context_key = make_context_id(
            section,
            kind=kind,
            source_text=raw,
            duplicate_ordinal=duplicate_ordinal,
        )
        outcome = _spoken(
            raw,
            context_id=context_key,
            language=selected_language,
            enabled=apply_spokenform,
            section_id=section_id,
            section_index=section_index,
            source_paragraph=source_index,
            section_locator_value=locator,
            sidecar=sidecar,
        )
        report.contexts.append(
            ContextRecord(
                id=context_key,
                section_id=section_id,
                section_locator=locator,
                section_index=section_index,
                source_paragraph=source_index,
                is_title=is_title,
                source_text=raw,
                spoken_text=outcome.text,
                source_sentences=_sentence_contexts(
                    context_key, raw, kind="source", language=selected_language
                ),
                spoken_sentences=_sentence_contexts(
                    context_key, outcome.text, kind="spoken", language=selected_language
                ),
            )
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
            spokenform_stats.stage_edits[stage] = spokenform_stats.stage_edits.get(stage, 0) + count
        section_stats_by_id[section_id].spokenform_changes += len(outcome.changes)
        for change in outcome.changes:
            report.changes.append(change)
            if change.rule:
                spokenform_stats.rules[change.rule] = spokenform_stats.rules.get(change.rule, 0) + 1
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

    rendered = render_txt(
        prepared,
        options=render_options or RenderOptions(),
    )
    report.output_chars = len(rendered)
    report.output_lines = len(rendered.splitlines())
    return ConversionResult(
        document=document,
        paragraphs=prepared,
        text=rendered,
        language=selected_language,
        warnings=report.warnings,
        report=report,
    )


def convert(
    source: str | Path,
    *,
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
    render_options: RenderOptions | None = None,
    sidecar: Sidecar | None = None,
) -> ConversionResult:
    """Load, prepare, and render one supported document."""
    document = load(source)
    return prepare(
        document,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        apply_spokenform=apply_spokenform,
        include_titles=include_titles,
        render_options=render_options,
        sidecar=sidecar,
    )
