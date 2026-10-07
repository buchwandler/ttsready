"""Immutable, source-neutral data models for the ttsready 0.2 API."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _json_value(value: Any, path: str = "metadata") -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise ValueError(f"{path} contains a non-JSON value: {type(value).__name__}")


def _json_mapping(value: Mapping[str, Any] | None, name: str) -> Mapping[str, JsonValue]:
    normalized = _json_value(value or {}, name)
    if not isinstance(normalized, dict):
        raise ValueError(f"{name} must be a mapping")
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class ProtectedSpan:
    start: int
    end: int
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("protected span must satisfy 0 <= start < end")


@dataclass(frozen=True, slots=True)
class TextUnit:
    id: str
    text: str
    language: str
    role: str = "prose"
    protected_spans: tuple[ProtectedSpan, ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("unit id must be a non-empty string")
        if not isinstance(self.text, str):
            raise TypeError("unit text must be a string")
        if not isinstance(self.language, str) or not self.language.strip():
            raise ValueError("unit language must be a non-empty string")
        if not isinstance(self.role, str) or not self.role:
            raise ValueError("unit role must be a non-empty string")
        spans = tuple(
            span if isinstance(span, ProtectedSpan) else ProtectedSpan(*span)
            for span in self.protected_spans
        )
        spans = tuple(sorted(spans, key=lambda span: (span.start, span.end)))
        previous_end = -1
        for span in spans:
            if span.end > len(self.text):
                raise ValueError("protected span is outside the unit text")
            if span.start < previous_end:
                raise ValueError("protected spans must not overlap")
            previous_end = span.end
        object.__setattr__(self, "protected_spans", spans)
        object.__setattr__(self, "metadata", _json_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class OverrideScope:
    kind: Literal["all", "unit", "occurrence"] = "all"
    unit_id: str | None = None
    source_start: int | None = None
    source_end: int | None = None

    def __post_init__(self) -> None:
        if self.kind == "all":
            valid = self.unit_id is None and self.source_start is None and self.source_end is None
        elif self.kind == "unit":
            valid = bool(self.unit_id) and self.source_start is None and self.source_end is None
        elif self.kind == "occurrence":
            valid = (
                bool(self.unit_id)
                and self.source_start is not None
                and self.source_end is not None
                and 0 <= self.source_start < self.source_end
            )
        else:
            valid = False
        if not valid:
            raise ValueError(f"invalid {self.kind!r} override scope fields")


@dataclass(frozen=True, slots=True)
class SpeechOverride:
    surface: str
    spoken: str
    match: Literal["literal", "word"] = "word"
    case_sensitive: bool = True
    scope: OverrideScope = field(default_factory=OverrideScope)
    id: str | None = None
    provenance: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.surface, str) or not self.surface:
            raise ValueError("override surface must be a non-empty string")
        if not isinstance(self.spoken, str):
            raise TypeError("override spoken text must be a string")
        if self.match not in {"literal", "word"}:
            raise ValueError("override match must be 'literal' or 'word'")
        if not isinstance(self.scope, OverrideScope):
            raise TypeError("override scope must be an OverrideScope")
        object.__setattr__(self, "provenance", _json_mapping(self.provenance, "provenance"))
        if self.id is None:
            from .identifiers import override_id

            object.__setattr__(self, "id", override_id(self))


@dataclass(frozen=True, slots=True)
class PreparationProfile:
    use_spacy: bool = False
    symbol_mode: str = "none"
    normalize_unicode: bool = False
    normalize_whitespace: bool = False
    strip_outer_whitespace: bool = False
    collapse_horizontal_whitespace: bool = False
    normalize_line_whitespace: bool = False
    collapse_blank_lines: bool = False
    generic_acronym_mode: str = "known_only"
    sequence_fallback_mode: Literal["preserve", "spell"] = "preserve"
    expand_abbreviations: bool = True
    expand_structured: bool = True
    expand_numbers: bool = True

    def __post_init__(self) -> None:
        if self.sequence_fallback_mode not in {"preserve", "spell"}:
            raise ValueError("sequence_fallback_mode must be 'preserve' or 'spell'")
        if not isinstance(self.symbol_mode, str) or not self.symbol_mode:
            raise ValueError("symbol_mode must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SpokenChange:
    id: str
    unit_id: str
    source_start: int
    source_end: int
    output_start: int
    output_end: int
    source: str
    replacement: str
    stages: tuple[str, ...] = ()
    kind: str = "normalization"
    rule: str | None = None
    recognition_domain: str | None = None
    provenance: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_start < 0 or self.source_end <= self.source_start:
            raise ValueError("change source span must satisfy 0 <= start < end")
        if self.output_start < 0 or self.output_end < self.output_start:
            raise ValueError("change output span must satisfy 0 <= start <= end")
        if not isinstance(self.source, str) or not isinstance(self.replacement, str):
            raise TypeError("change source and replacement must be strings")
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "provenance", _json_mapping(self.provenance, "provenance"))


@dataclass(frozen=True, slots=True)
class PreparationIssue:
    code: str
    severity: Literal["info", "warning", "error"]
    unit_id: str
    source_start: int | None
    source_end: int | None
    text: str | None
    message: str
    provenance: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("issue severity must be 'info', 'warning', or 'error'")
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("issue source_start and source_end must be provided together")
        if self.source_start is not None and (
            self.source_start < 0 or self.source_end is None or self.source_end < self.source_start
        ):
            raise ValueError("issue source span is invalid")
        object.__setattr__(self, "provenance", _json_mapping(self.provenance, "provenance"))


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    index: int
    text: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.index < 0 or self.start < 0 or self.end < self.start:
            raise ValueError("sentence span has invalid indices")


@dataclass(frozen=True, slots=True)
class UnitContext:
    unit_id: str
    role: str
    language: str
    source_text: str
    spoken_text: str
    source_sentences: tuple[SentenceSpan, ...]
    spoken_sentences: tuple[SentenceSpan, ...]


@dataclass(frozen=True, slots=True)
class ChangeContext:
    change: SpokenChange
    unit: UnitContext
    source_sentences: tuple[SentenceSpan, ...]
    spoken_sentences: tuple[SentenceSpan, ...]


@dataclass(frozen=True, slots=True)
class PreparedUnit:
    unit_id: str
    source_text: str
    spoken_text: str
    language: str
    role: str
    changes: tuple[SpokenChange, ...]
    issues: tuple[PreparationIssue, ...]
    context: UnitContext

    def __post_init__(self) -> None:
        changes = tuple(sorted(self.changes, key=lambda item: item.source_start))
        cursor = 0
        delta = 0
        rendered: list[str] = []
        for change in changes:
            if change.unit_id != self.unit_id:
                raise ValueError("prepared change belongs to a different unit")
            if change.source_start < cursor or change.source_end > len(self.source_text):
                raise ValueError("prepared changes overlap or exceed source text")
            if self.source_text[change.source_start : change.source_end] != change.source:
                raise ValueError("prepared change source does not match source text")
            expected_output_start = change.source_start + delta
            expected_output_end = expected_output_start + len(change.replacement)
            if (change.output_start, change.output_end) != (
                expected_output_start,
                expected_output_end,
            ):
                raise ValueError("prepared change output coordinates are inconsistent")
            if self.spoken_text[change.output_start : change.output_end] != change.replacement:
                raise ValueError("prepared change output span does not select its replacement")
            rendered.extend((self.source_text[cursor : change.source_start], change.replacement))
            cursor = change.source_end
            delta += len(change.replacement) - len(change.source)
        rendered.append(self.source_text[cursor:])
        if "".join(rendered) != self.spoken_text:
            raise ValueError("prepared changes do not reconstruct spoken_text")
        if self.context.unit_id != self.unit_id:
            raise ValueError("prepared context belongs to a different unit")
        if (self.context.source_text, self.context.spoken_text) != (
            self.source_text,
            self.spoken_text,
        ):
            raise ValueError("prepared context text differs from its unit")
        object.__setattr__(self, "changes", changes)
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def changed(self) -> bool:
        return self.source_text != self.spoken_text

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(issue.message for issue in self.issues if issue.severity == "warning")

    @property
    def errors(self) -> tuple[PreparationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")


@dataclass(frozen=True, slots=True)
class PreparationStats:
    units_processed: int = 0
    units_changed: int = 0
    changes: int = 0
    stage_edits: Mapping[str, int] = field(default_factory=dict)
    rules: Mapping[str, int] = field(default_factory=dict)
    recognition_domains: Mapping[str, int] = field(default_factory=dict)
    structured_numeric_edits: int = 0
    source_digit_replacements: int = 0
    warning_count: int = 0
    error_count: int = 0

    def __post_init__(self) -> None:
        for name in (
            "units_processed",
            "units_changed",
            "changes",
            "structured_numeric_edits",
            "source_digit_replacements",
            "warning_count",
            "error_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        for name in ("stage_edits", "rules", "recognition_domains"):
            values = dict(getattr(self, name))
            if any(
                not isinstance(key, str) or not isinstance(value, int) or value < 0
                for key, value in values.items()
            ):
                raise ValueError(f"{name} must map strings to non-negative integers")
            object.__setattr__(self, name, MappingProxyType(values))

    @property
    def abbreviation_edits(self) -> int:
        return self.stage_edits.get("abbreviations", 0)

    @property
    def number_edits(self) -> int:
        return self.stage_edits.get("numbers", 0)

    @property
    def structured_edits(self) -> int:
        return self.stage_edits.get("structured", 0)


@dataclass(frozen=True, slots=True)
class PreparationResult:
    units: tuple[PreparedUnit, ...]
    changes: tuple[SpokenChange, ...]
    issues: tuple[PreparationIssue, ...]
    stats: PreparationStats
    profile_fingerprint: str
    override_fingerprint: str
    runtime_fingerprint: str
    prepared_fingerprint: str
    schema: str = "ttsready.preparation.v2"

    def to_dict(self) -> dict[str, JsonValue]:
        from .serialization import result_to_dict

        return result_to_dict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonValue]) -> PreparationResult:
        from .serialization import result_from_dict

        return result_from_dict(data)


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    start: int
    end: int
    part: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start or self.part < 0:
            raise ValueError("text chunk has invalid coordinates")
