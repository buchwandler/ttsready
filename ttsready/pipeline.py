"""TTS preparation pipeline."""

from __future__ import annotations

import platform
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ssmd import AnnotationSpan

from .errors import TTSReadyError
from .identifiers import change_id, file_sha256, section_locator, stable_id, text_sha256
from .identifiers import context_id as make_context_id
from .input import load
from .models import (
    ContextRecord,
    ConversionReport,
    ConversionResult,
    Document,
    NormalizationProfile,
    PreparedSegment,
    RenderOptions,
    Section,
    SectionStats,
    SentenceContext,
    SpokenChange,
    SpokenformStats,
    TTSPlan,
)
from .overrides import apply_overrides, find_overrides
from .planning import render_preview
from .reproducibility import normalization_fingerprints, runtime_fingerprint
from .sidecar import Sidecar

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
    ssmd_annotations: tuple[AnnotationSpan, ...] = ()
    language: str | None = None
    voice_spans: tuple[tuple[int, int, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _SSMDReplacement:
    source_start: int
    source_end: int
    source: str
    replacement: str


def normalization_profile(language: str) -> NormalizationProfile:
    return NormalizationProfile(language=language)


def _authoritative_annotation(annotation: AnnotationSpan) -> bool:
    return bool(
        {"sub", "as", "say-as", "ph", "ipa", "sampa", "phonemes"}.intersection(annotation.attrs)
        or annotation.attrs.get("tag") in {"say-as", "phoneme"}
    )


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
    ssmd_annotations: tuple[AnnotationSpan, ...] = (),
) -> SpokenOutcome:
    authoritative = tuple(item for item in ssmd_annotations if _authoritative_annotation(item))
    protected_spans = tuple((item.char_start, item.char_end) for item in authoritative)
    overrides = sidecar.lexicon if sidecar else ()
    matches = find_overrides(
        text,
        overrides,
        context_id=context_id,
        section_id=section_id,
        section_locator=section_locator_value,
    )
    matches = tuple(
        match
        for match in matches
        if not any(match.start < end and start < match.end for start, end in protected_spans)
    )

    if enabled:
        from spokenform import prepare as prepare_spokenform

        prepared = prepare_spokenform(
            text,
            **asdict(normalization_profile(language)),
            protected_spans=(*protected_spans, *((match.start, match.end) for match in matches)),
        )
        stage_edit_counts: dict[str, int] = {}
        for stage in prepared.stages:
            stage_edit_counts[stage.name] = stage_edit_counts.get(stage.name, 0) + len(
                stage.mapped_edits
            )
        replacements = tuple(prepared.source_replacements)
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
        output_text = prepared.spoken_text
    else:
        replacements = ()
        base_changes = ()
        stage_edit_counts = {}
        warnings = ()
        output_text = text

    authoritative_replacements = tuple(
        _SSMDReplacement(
            source_start=item.char_start,
            source_end=item.char_end,
            source=text[item.char_start : item.char_end],
            replacement=item.attrs["sub"],
        )
        for item in authoritative
        if "sub" in item.attrs
    )
    authoritative_changes: list[SpokenChange] = []
    mapped_substitutions: list[tuple[_SSMDReplacement, int]] = []
    for substitution in authoritative_replacements:
        apply_output_start = substitution.source_start + sum(
            len(item.replacement) - len(item.source)
            for item in replacements
            if item.source_end <= substitution.source_start
        )
        output_start = apply_output_start + sum(
            len(item.replacement) - len(item.source)
            for item in authoritative_replacements
            if item.source_end <= substitution.source_start
        )
        mapped_substitutions.append((substitution, apply_output_start))
        authoritative_changes.append(
            SpokenChange(
                id=change_id(
                    context_id,
                    source_start=substitution.source_start,
                    source_end=substitution.source_end,
                    source=substitution.source,
                ),
                context_id=context_id,
                section_id=section_id,
                section_index=section_index,
                source_paragraph=source_paragraph,
                source=substitution.source,
                replacement=substitution.replacement,
                stages=("ssmd.sub",),
                kind="normalization",
                rule=None,
                recognition_domain=None,
                source_start=substitution.source_start,
                source_end=substitution.source_end,
                output_start=output_start,
                output_end=output_start + len(substitution.replacement),
                provenance={"origin": "ssmd.sub", "status": "authoritative"},
            )
        )
    for substitution, output_start in reversed(mapped_substitutions):
        output_end = output_start + len(substitution.source)
        output_text = (
            output_text[:output_start] + substitution.replacement + output_text[output_end:]
        )
    base_changes = (*base_changes, *authoritative_changes)
    if authoritative_changes:
        stage_edit_counts["ssmd.sub"] = len(authoritative_changes)

    all_replacements = (*replacements, *authoritative_replacements)
    spoken_text, applied = apply_overrides(output_text, matches, all_replacements)
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
        base_changes = tuple(
            replace(
                change,
                output_start=change.output_start
                + sum(
                    len(item.match.override.spoken) - (item.match.end - item.match.start)
                    for item in applied
                    if item.match.end <= change.source_start
                ),
                output_end=change.output_end
                + sum(
                    len(item.match.override.spoken) - (item.match.end - item.match.start)
                    for item in applied
                    if item.match.end <= change.source_start
                ),
            )
            for change in base_changes
        )

    return SpokenOutcome(
        text=spoken_text,
        warnings=warnings,
        changed=spoken_text != text,
        stage_edit_counts=stage_edit_counts,
        changes=(*base_changes, *custom_changes),
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
    versions["python"] = platform.python_version()
    for distribution in ("ttsready", "ssmd", "ssmdconvert", "spokenform", "phrasplit"):
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


def _voice_output_ranges(
    voice_spans: tuple[tuple[int, int, str], ...],
    changes: tuple[SpokenChange, ...],
    output_text: str,
) -> tuple[tuple[int, int, str], ...]:
    if not voice_spans:
        return ()

    def priority(change: SpokenChange) -> int:
        if "ssmd.sub" in change.stages:
            return 0
        return 1 if "custom" in change.stages else 2

    selected: list[SpokenChange] = []
    for change in sorted(
        changes,
        key=lambda item: (item.source_start, priority(item), item.source_end),
    ):
        overlapping = [
            item
            for item in selected
            if item.source_start < change.source_end and change.source_start < item.source_end
        ]
        if not overlapping:
            selected.append(change)
        elif priority(change) < min(priority(item) for item in overlapping):
            selected = [item for item in selected if item not in overlapping]
            selected.append(change)

    def map_offset(offset: int) -> int:
        for change in selected:
            if offset == change.source_start:
                return change.output_start
            if offset == change.source_end:
                return change.output_end
            if change.source_start < offset < change.source_end:
                raise TTSReadyError("A voice boundary crosses a speech replacement span")
        return offset + sum(
            change.output_end - change.output_start - (change.source_end - change.source_start)
            for change in selected
            if change.source_end < offset
        )

    output_ranges = tuple(
        (map_offset(start), map_offset(end), voice) for start, end, voice in voice_spans
    )
    if any(start < 0 or end > len(output_text) or start >= end for start, end, _ in output_ranges):
        raise TTSReadyError("A logical voice span no longer maps to prepared speech text")
    ordered = sorted(output_ranges)
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left[1] > right[0] and left[2] != right[2]:
            raise TTSReadyError("Overlapping SSMD voice annotations assign conflicting speakers")
    return output_ranges


def _voice_pieces(
    text: str, voice_ranges: tuple[tuple[int, int, str], ...]
) -> list[tuple[str, str | None]]:
    if not voice_ranges:
        return [(text, None)]
    boundaries = sorted(
        {0, len(text), *(point for start, end, _ in voice_ranges for point in (start, end))}
    )
    pieces: list[tuple[str, str | None]] = []
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        if start == end:
            continue
        active = {
            voice
            for voice_start, voice_end, voice in voice_ranges
            if voice_start <= start and end <= voice_end
        }
        if len(active) > 1:
            raise TTSReadyError("Overlapping SSMD voice annotations assign conflicting speakers")
        pieces.append((text[start:end], next(iter(active), None)))
    return pieces


def _paragraph_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        end = match.start()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            ranges.append((start, end))
        start = match.end()
    end = len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start < end:
        ranges.append((start, end))
    return ranges


def _iter_section_inputs(document: Document, include_titles: bool) -> Iterable[SourceItem]:
    for output_index, section in enumerate(document.sections, start=1):
        section_index = section.source_index or output_index
        if include_titles and section.title and section.title.strip():
            yield SourceItem(section, section_index, -1, True, section.title.strip())

        if section.structure is None:
            for index, paragraph in enumerate(source_paragraphs(section.text)):
                yield SourceItem(section, section_index, index, False, paragraph)
            continue

        annotations = section.structure.effective_annotations or section.structure.annotations
        for index, (start, end) in enumerate(_paragraph_ranges(section.text)):
            paragraph = section.text[start:end]
            local_annotations: list[AnnotationSpan] = []
            local_voice_spans = []
            for annotation in annotations:
                voice = annotation.attrs.get("voice")
                if (
                    not isinstance(voice, str)
                    or annotation.char_start >= end
                    or annotation.char_end <= start
                ):
                    continue
                local_voice_spans.append(
                    (
                        max(annotation.char_start, start) - start,
                        min(annotation.char_end, end) - start,
                        voice,
                    )
                )
            for annotation in annotations:
                if not _authoritative_annotation(annotation):
                    continue
                if annotation.char_start >= end or annotation.char_end <= start:
                    continue
                if annotation.char_start < start or annotation.char_end > end:
                    raise TTSReadyError(
                        "An authoritative SSMD annotation crosses a paragraph boundary"
                    )
                local_annotations.append(
                    AnnotationSpan(
                        char_start=annotation.char_start - start,
                        char_end=annotation.char_end - start,
                        attrs=dict(annotation.attrs),
                        kind=annotation.kind,
                    )
                )
            language_annotations = [
                annotation
                for annotation in annotations
                if annotation.language
                and annotation.char_start <= start
                and annotation.char_end >= end
            ]
            local_language = (
                min(language_annotations, key=lambda item: item.char_end - item.char_start).language
                if language_annotations
                else None
            )
            yield SourceItem(
                section,
                section_index,
                index,
                False,
                paragraph,
                tuple(local_annotations),
                local_language,
                tuple(local_voice_spans),
            )


def prepare_tts_plan(
    document: Document,
    *,
    language: str | None = None,
    max_paragraph_chars: int | None = 1000,
    apply_spokenform: bool = True,
    include_titles: bool = True,
    sidecar: Sidecar | None = None,
) -> TTSPlan:
    """Normalize SSMD content and build a structured TTS plan without rendering it."""
    if max_paragraph_chars is not None and max_paragraph_chars < 1:
        raise ValueError("max_paragraph_chars must be at least 1")

    metadata_language = document.metadata.get("language")
    selected_language = str(language or metadata_language or "en")
    requested_language = str(language) if language is not None else None
    profile_options = asdict(normalization_profile(selected_language))
    profile_hashes = normalization_fingerprints(selected_language, profile_options, sidecar)
    tool_versions = _tool_versions()
    section_stats = [
        SectionStats(
            section_id=section.id,
            index=section.source_index or index,
            title=section.title,
            level=section.level,
            input_chars=len(section.text),
            chapter_sha256=section.chapter_sha256 or text_sha256(section.ssmd or section.text),
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
        source_sha256=document.source_sha256 or file_sha256(str(document.source.path)),
        content_fingerprint=document.content_fingerprint,
        normalization_profile=profile_options,
        normalization_options_sha256=profile_hashes["options_sha256"],
        pronunciation_profile_sha256=profile_hashes["pronunciation_profile_sha256"],
        normalization_profile_sha256=profile_hashes["profile_sha256"],
        runtime_fingerprint=runtime_fingerprint(tool_versions),
        tool_versions=tool_versions,
    )
    prepared: list[PreparedSegment] = []
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
            language=source_item.language or selected_language,
            enabled=apply_spokenform,
            section_id=section_id,
            section_index=section_index,
            source_paragraph=source_index,
            section_locator_value=locator,
            sidecar=sidecar,
            ssmd_annotations=source_item.ssmd_annotations,
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
                    context_key,
                    raw,
                    kind="source",
                    language=source_item.language or selected_language,
                ),
                spoken_sentences=_sentence_contexts(
                    context_key,
                    outcome.text,
                    kind="spoken",
                    language=source_item.language or selected_language,
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
        voice_ranges = _voice_output_ranges(
            source_item.voice_spans,
            outcome.changes,
            outcome.text,
        )
        parts = _split_oversized(
            outcome.text,
            max_chars=max_paragraph_chars,
            language=source_item.language or selected_language,
        )
        if len(parts) > 1:
            report.split_source_items += 1
        report.added_split_parts += max(0, len(parts) - 1)
        part_search_start = 0
        for part_index, part in enumerate(parts):
            if voice_ranges:
                part_start = outcome.text.find(part, part_search_start)
                if part_start < 0:
                    raise TTSReadyError("Could not map a prepared chunk back to its voice spans")
                part_end = part_start + len(part)
                part_search_start = part_end
                clipped_voice_ranges = tuple(
                    (max(start, part_start) - part_start, min(end, part_end) - part_start, voice)
                    for start, end, voice in voice_ranges
                    if start < part_end and part_start < end
                )
                voice_pieces = _voice_pieces(part, clipped_voice_ranges)
            else:
                voice_pieces = [(part, None)]
            render_group = f"{context_key}:{part_index}"
            for text, voice in voice_pieces:
                prepared.append(
                    PreparedSegment(
                        text=text,
                        chapter_id=section_id,
                        source_paragraph=source_index,
                        part=part_index,
                        is_title=is_title,
                        language=source_item.language or selected_language,
                        voice=voice,
                        source_context_id=context_key,
                        render_group=render_group,
                    )
                )
                report.prepared_paragraphs += 1
                report.max_prepared_paragraph_chars = max(
                    report.max_prepared_paragraph_chars, len(text)
                )
                section_stats_by_id[section_id].prepared_paragraphs += 1
                section_stats_by_id[section_id].output_chars += len(text)

    return TTSPlan(
        document=document,
        segments=tuple(prepared),
        language=selected_language,
        report=report,
    )


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
    """Build a structured speech plan and render its plain-text preview."""
    plan = prepare_tts_plan(
        document,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        apply_spokenform=apply_spokenform,
        include_titles=include_titles,
        sidecar=sidecar,
    )
    rendered = render_preview(plan, options=render_options)
    report = plan.report
    report.output_chars = len(rendered)
    report.output_lines = len(rendered.splitlines())
    report.prepared_output_sha256 = text_sha256(rendered)
    return ConversionResult(
        document=plan.document,
        paragraphs=list(plan.segments),
        text=rendered,
        language=plan.language,
        warnings=report.warnings,
        report=report,
        plan=plan,
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
    """Load canonical SSMD, prepare speech, and render plain text."""
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
