"""Source-neutral orchestration around spokenform's explicit-language API."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

import phrasplit
import spokenform

from .errors import InvalidUnitError, MappingError, PreparationError
from .identifiers import source_change_id
from .models import (
    PreparationIssue,
    PreparationProfile,
    PreparationResult,
    PreparationStats,
    PreparedUnit,
    ProtectedSpan,
    SentenceSpan,
    SpeechOverride,
    SpokenChange,
    TextChunk,
    TextUnit,
    UnitContext,
)
from .overrides import overlaps as _overlaps
from .overrides import resolve_overrides
from .reproducibility import (
    override_fingerprint,
    prepared_fingerprint,
    profile_fingerprint,
    runtime_fingerprint,
)


def _backend_options(profile: PreparationProfile, *, strict: bool) -> dict[str, Any]:
    return {
        "use_spacy": profile.use_spacy,
        "symbol_mode": profile.symbol_mode,
        "normalize_unicode": profile.normalize_unicode,
        "normalize_whitespace": profile.normalize_whitespace,
        "strip_outer_whitespace": profile.strip_outer_whitespace,
        "collapse_horizontal_whitespace": profile.collapse_horizontal_whitespace,
        "normalize_line_whitespace": profile.normalize_line_whitespace,
        "collapse_blank_lines": profile.collapse_blank_lines,
        "generic_acronym_mode": profile.generic_acronym_mode,
        "sequence_fallback_mode": profile.sequence_fallback_mode,
        "expand_abbreviations": profile.expand_abbreviations,
        "expand_structured": profile.expand_structured,
        "expand_numbers": profile.expand_numbers,
        "strict": strict,
    }


def _replacement_value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _normalize_backend_changes(
    unit: TextUnit,
    backend: Any,
) -> tuple[tuple[Any, ...], ...]:
    output = getattr(backend, "spoken_text", getattr(backend, "text", None))
    if not isinstance(output, str):
        raise MappingError("spokenform result does not expose spoken_text")
    raw_changes = getattr(backend, "source_replacements", None)
    if raw_changes is None:
        raise MappingError("spokenform result does not expose source_replacements")

    normalized: list[tuple[Any, ...]] = []
    cursor = 0
    delta = 0
    for item in sorted(
        raw_changes, key=lambda value: _replacement_value(value, "source_start", -1)
    ):
        start = _replacement_value(item, "source_start")
        end = _replacement_value(item, "source_end")
        source = _replacement_value(item, "source")
        replacement = _replacement_value(item, "replacement")
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(source, str):
            raise MappingError("spokenform returned a malformed source replacement")
        if (
            not isinstance(replacement, str)
            or start < cursor
            or end <= start
            or end > len(unit.text)
        ):
            raise MappingError(
                "spokenform returned overlapping or out-of-range source replacements"
            )
        if unit.text[start:end] != source:
            raise MappingError("spokenform source replacement does not match the input text")
        expected_start = start + delta
        expected_end = expected_start + len(replacement)
        if output[expected_start:expected_end] != replacement:
            raise MappingError("spokenform output span does not select its reported replacement")
        reported_start = _replacement_value(item, "output_start", expected_start)
        reported_end = _replacement_value(item, "output_end", expected_end)
        if reported_start != expected_start or reported_end != expected_end:
            raise MappingError("spokenform output coordinates are inconsistent with source edits")
        normalized.append((start, end, source, replacement, item))
        cursor = end
        delta += len(replacement) - (end - start)

    reconstructed = apply_changes(
        unit.text,
        tuple(
            _temporary_change(unit.id, start, end, source, replacement)
            for start, end, source, replacement, _item in normalized
        ),
    )
    if reconstructed != output:
        raise MappingError("spokenform changes do not reconstruct its spoken_text")
    return tuple(normalized)


def _temporary_change(
    unit_id: str, start: int, end: int, source: str, replacement: str
) -> SpokenChange:
    return SpokenChange(
        id="temporary",
        unit_id=unit_id,
        source_start=start,
        source_end=end,
        output_start=0,
        output_end=len(replacement),
        source=source,
        replacement=replacement,
    )


def _verify_protected_spans(
    unit: TextUnit,
    changes: tuple[tuple[Any, ...], ...],
    spoken_text: str,
) -> None:
    for span in unit.protected_spans:
        if any(_overlaps((item[0], item[1]), (span.start, span.end)) for item in changes):
            raise MappingError("spokenform changed a caller-protected source span")
        shift = sum(
            len(replacement) - (end - start)
            for start, end, _source, replacement, _item in changes
            if end <= span.start
        )
        output_start = span.start + shift
        if (
            spoken_text[output_start : output_start + (span.end - span.start)]
            != unit.text[span.start : span.end]
        ):
            raise MappingError("spokenform altered text inside a caller-protected span")


def _sentence_spans(text: str, language: str) -> tuple[SentenceSpan, ...]:
    if not text:
        return ()
    try:
        segments = phrasplit.split_with_offsets(
            text,
            mode="sentence",
            use_spacy=False,
            language=language,
            apply_corrections=False,
        )
    except Exception:
        return (SentenceSpan(0, text, 0, len(text)),)
    spans = tuple(
        SentenceSpan(index, segment.text, segment.char_start, segment.char_end)
        for index, segment in enumerate(segments)
    )
    if any(text[span.start : span.end] != span.text for span in spans):
        raise MappingError("sentence splitter returned inconsistent source coordinates")
    return spans or (SentenceSpan(0, text, 0, len(text)),)


def _change_from_backend(
    unit: TextUnit,
    normalized: tuple[Any, ...],
) -> tuple[int, int, str, str, tuple[str, ...], str, str | None, str | None, Mapping[str, Any]]:
    start, end, source, replacement, item = normalized
    stages = tuple(str(stage) for stage in (_replacement_value(item, "stages", ()) or ()))
    evidence: dict[str, Any] = {"origin": "spokenform", "language": unit.language}
    for name in ("recognition_evidence", "evidence_source", "evidence_score", "evidence_cues"):
        value = _replacement_value(item, name)
        if value is not None:
            evidence[name] = list(value) if name == "evidence_cues" else value
    return (
        start,
        end,
        source,
        replacement,
        stages,
        str(_replacement_value(item, "kind", "normalization")),
        _replacement_value(item, "rule"),
        _replacement_value(item, "recognition_domain"),
        evidence,
    )


def _prepare_unit(
    unit: TextUnit,
    overrides: tuple[SpeechOverride, ...],
    profile: PreparationProfile,
    *,
    strict: bool,
) -> PreparedUnit:
    resolved, resolution_issues = resolve_overrides(unit, overrides)
    backend_spans = tuple((span.start, span.end) for span in unit.protected_spans) + tuple(
        (match.start, match.end) for match in resolved
    )

    try:
        backend = spokenform.prepare_language(
            unit.text,
            language=unit.language,
            protected_spans=backend_spans,
            **_backend_options(profile, strict=strict),
        )
    except Exception as exc:
        raise PreparationError(f"spokenform failed to prepare unit {unit.id!r}: {exc}") from exc

    backend_text = getattr(backend, "spoken_text", getattr(backend, "text", None))
    if not isinstance(backend_text, str):
        raise MappingError("spokenform result does not expose spoken_text")
    backend_changes = _normalize_backend_changes(unit, backend)
    _verify_protected_spans(unit, backend_changes, backend_text)
    for match in resolved:
        start, end = match.start, match.end
        if any(_overlaps((start, end), (item[0], item[1])) for item in backend_changes):
            raise MappingError("spokenform changed a source span reserved for an explicit override")

    replacements: list[tuple[Any, ...]] = [
        _change_from_backend(unit, item) for item in backend_changes
    ]
    for match in resolved:
        start, end, override = match.start, match.end, match.override
        replacements.append(
            (
                start,
                end,
                unit.text[start:end],
                override.spoken,
                ("override",),
                "override",
                None,
                None,
                {
                    "origin": "override",
                    "override_id": str(override.id),
                    **dict(override.provenance),
                },
            )
        )
    replacements.sort(key=lambda item: (item[0], item[1]))

    changes: list[SpokenChange] = []
    cursor = 0
    output_parts: list[str] = []
    output_offset = 0
    for item in replacements:
        start, end, source, replacement, stages, kind, rule, domain, provenance = item
        if start < cursor:
            raise MappingError("backend and override changes overlap in source coordinates")
        output_parts.append(unit.text[cursor:start])
        output_offset += start - cursor
        out_start = output_offset
        output_parts.append(replacement)
        output_offset += len(replacement)
        out_end = output_offset
        change_id = source_change_id(
            unit.id,
            source_start=start,
            source_end=end,
            source=source,
        )
        changes.append(
            SpokenChange(
                id=change_id,
                unit_id=unit.id,
                source_start=start,
                source_end=end,
                output_start=out_start,
                output_end=out_end,
                source=source,
                replacement=replacement,
                stages=stages,
                kind=kind,
                rule=rule,
                recognition_domain=domain,
                provenance=provenance,
            )
        )
        cursor = end
    output_parts.append(unit.text[cursor:])
    spoken_text = "".join(output_parts)
    if not resolved and spoken_text != backend_text:
        raise MappingError(
            "ttsready merge differs from spokenform output without explicit overrides"
        )
    if apply_changes(unit.text, tuple(changes)) != spoken_text:
        raise MappingError("merged source-relative changes do not reconstruct spoken_text")

    issues = list(resolution_issues)
    issues.extend(
        PreparationIssue(
            code="spokenform.warning",
            severity="warning",
            unit_id=unit.id,
            source_start=None,
            source_end=None,
            text=None,
            message=str(warning),
            provenance={"origin": "spokenform", "language": unit.language},
        )
        for warning in (getattr(backend, "warnings", ()) or ())
    )
    context = UnitContext(
        unit_id=unit.id,
        role=unit.role,
        language=unit.language,
        source_text=unit.text,
        spoken_text=spoken_text,
        source_sentences=_sentence_spans(unit.text, unit.language),
        spoken_sentences=_sentence_spans(spoken_text, unit.language),
    )
    prepared = PreparedUnit(
        unit_id=unit.id,
        source_text=unit.text,
        spoken_text=spoken_text,
        language=unit.language,
        role=unit.role,
        changes=tuple(changes),
        issues=tuple(issues),
        context=context,
    )
    from .qa import _check_prepared_unit

    return _check_prepared_unit(unit, prepared, profile, strict=strict)


def apply_changes(text: str, changes: Iterable[SpokenChange]) -> str:
    """Apply source-relative changes, rejecting stale or overlapping coordinates."""
    ordered = tuple(sorted(changes, key=lambda item: (item.source_start, item.source_end)))
    parts: list[str] = []
    cursor = 0
    for change in ordered:
        if change.source_start < cursor or change.source_end > len(text):
            raise MappingError("changes overlap or fall outside the supplied source text")
        if text[change.source_start : change.source_end] != change.source:
            raise MappingError("change source does not match the supplied source text")
        parts.append(text[cursor : change.source_start])
        parts.append(change.replacement)
        cursor = change.source_end
    parts.append(text[cursor:])
    return "".join(parts)


def prepare_text(
    text: str,
    *,
    language: str,
    unit_id: str = "text",
    role: str = "prose",
    protected_spans: Iterable[ProtectedSpan | tuple[int, int]] = (),
    overrides: Iterable[SpeechOverride] = (),
    metadata: Mapping[str, Any] | None = None,
    profile: PreparationProfile | None = None,
    strict: bool = False,
) -> PreparedUnit:
    """Prepare one caller-owned text unit without reading or writing any files."""
    unit = TextUnit(
        id=unit_id,
        text=text,
        language=language,
        role=role,
        protected_spans=tuple(protected_spans),
        metadata=metadata or {},
    )
    return _prepare_unit(
        unit,
        tuple(overrides),
        profile or PreparationProfile(),
        strict=strict,
    )


def prepare_units(
    units: Iterable[TextUnit],
    *,
    overrides: Iterable[SpeechOverride] = (),
    profile: PreparationProfile | None = None,
    strict: bool = False,
) -> PreparationResult:
    """Prepare ordered caller-owned units with pure aggregate fingerprints."""
    unit_list = tuple(units)
    if any(not isinstance(unit, TextUnit) for unit in unit_list):
        raise InvalidUnitError("prepare_units accepts only TextUnit values")
    identifiers = [unit.id for unit in unit_list]
    if len(identifiers) != len(set(identifiers)):
        raise InvalidUnitError("TextUnit IDs must be unique within one preparation result")
    override_list = tuple(overrides)
    if any(not isinstance(item, SpeechOverride) for item in override_list):
        raise PreparationError("overrides must contain only SpeechOverride values")
    effective_profile = profile or PreparationProfile()
    if not isinstance(effective_profile, PreparationProfile):
        raise PreparationError("profile must be a PreparationProfile")

    prepared = tuple(
        _prepare_unit(unit, override_list, effective_profile, strict=strict) for unit in unit_list
    )
    changes = tuple(change for unit in prepared for change in unit.changes)
    issues = tuple(issue for unit in prepared for issue in unit.issues)
    stages = Counter(stage for change in changes for stage in change.stages)
    rules = Counter(change.rule for change in changes if change.rule is not None)
    domains = Counter(change.recognition_domain for change in changes if change.recognition_domain)
    stats = PreparationStats(
        units_processed=len(prepared),
        units_changed=sum(unit.changed for unit in prepared),
        changes=len(changes),
        stage_edits=dict(stages),
        rules=dict(rules),
        recognition_domains=dict(domains),
        structured_numeric_edits=sum(
            "structured" in change.stages or change.kind == "structured" for change in changes
        ),
        source_digit_replacements=sum(
            any(char.isdigit() for char in change.source) for change in changes
        ),
        warning_count=sum(issue.severity == "warning" for issue in issues),
        error_count=sum(issue.severity == "error" for issue in issues),
    )
    profile_hash = profile_fingerprint(effective_profile)
    override_hash = override_fingerprint(override_list)
    runtime_hash = runtime_fingerprint()
    return PreparationResult(
        units=prepared,
        changes=changes,
        issues=issues,
        stats=stats,
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
        prepared_fingerprint=prepared_fingerprint(prepared),
    )


def split_prepared_text(
    text: str,
    *,
    language: str,
    max_chars: int,
) -> tuple[TextChunk, ...]:
    """Split text into sentence-aware chunks with exact offsets into ``text``."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not language:
        raise ValueError("language must be non-empty")
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if not text:
        return ()
    segments = phrasplit.split_with_offsets(
        text,
        mode="sentence",
        use_spacy=False,
        language=language,
        apply_corrections=False,
        max_chars=max_chars,
    )
    if not segments:
        return (TextChunk(text, 0, len(text), 0),)
    chunks: list[TextChunk] = []
    for index, segment in enumerate(segments):
        start = 0 if index == 0 else segment.char_start
        end = segments[index + 1].char_start if index + 1 < len(segments) else len(text)
        if text[start:end] == "":
            continue
        chunks.append(TextChunk(text[start:end], start, end, len(chunks)))
    return tuple(chunks)


__all__ = ["apply_changes", "prepare_text", "prepare_units", "split_prepared_text"]
