"""Immutable, source-neutral data models for the ttsready 0.3 API."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
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
class LinguisticToken:
    start: int
    end: int
    text: str | None = None
    pos: str | None = None
    tag: str | None = None
    lemma: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.start, int) or isinstance(self.start, bool) or self.start < 0:
            raise ValueError("linguistic token start must be a non-negative integer")
        if not isinstance(self.end, int) or isinstance(self.end, bool) or self.end <= self.start:
            raise ValueError("linguistic token end must be an integer greater than start")
        for name in ("text", "pos", "tag", "lemma", "language"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"linguistic token {name} must be a string or None")


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
class SourceOutputMap:
    source_length: int
    output_length: int
    source_left: tuple[int, ...]
    source_right: tuple[int, ...]
    output_left: tuple[int, ...]
    output_right: tuple[int, ...]

    def __post_init__(self) -> None:
        for name in ("source_length", "output_length"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        for name in ("source_left", "source_right", "output_left", "output_right"):
            try:
                values = tuple(getattr(self, name))
            except TypeError as exc:
                raise ValueError(f"{name} must be a sequence of boundary integers") from exc
            if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                raise ValueError(f"{name} must contain only integers")
            object.__setattr__(self, name, values)

        expected_lengths = {
            "source_left": self.source_length + 1,
            "source_right": self.source_length + 1,
            "output_left": self.output_length + 1,
            "output_right": self.output_length + 1,
        }
        for name, expected in expected_lengths.items():
            if len(getattr(self, name)) != expected:
                raise ValueError(f"{name} must contain exactly {expected} boundaries")

        if any(
            left > right for left, right in zip(self.source_left, self.source_right, strict=True)
        ):
            raise ValueError("source_left boundaries must not exceed source_right boundaries")
        for name in ("source_left", "source_right"):
            values = getattr(self, name)
            if any(value < 0 or value > self.output_length for value in values):
                raise ValueError(f"{name} contains a value outside the output range")
            if any(left > right for left, right in zip(values, values[1:], strict=False)):
                raise ValueError(f"{name} must be monotonic non-decreasing")

        if any(
            left > right for left, right in zip(self.output_left, self.output_right, strict=True)
        ):
            raise ValueError("output_left boundaries must not exceed output_right boundaries")
        for name in ("output_left", "output_right"):
            values = getattr(self, name)
            if any(value < 0 or value > self.source_length for value in values):
                raise ValueError(f"{name} contains a value outside the source range")
            if any(left > right for left, right in zip(values, values[1:], strict=False)):
                raise ValueError(f"{name} must be monotonic non-decreasing")

    @classmethod
    def identity(cls, length: int) -> SourceOutputMap:
        if not isinstance(length, int) or isinstance(length, bool) or length < 0:
            raise ValueError("identity length must be a non-negative integer")
        boundaries = tuple(range(length + 1))
        return cls(length, length, boundaries, boundaries, boundaries, boundaries)

    @classmethod
    def concatenate(cls, maps: Iterable[SourceOutputMap]) -> SourceOutputMap:
        items = tuple(maps)
        if any(not isinstance(item, cls) for item in items):
            raise TypeError("concatenate accepts only SourceOutputMap values")
        items = tuple(item for item in items if item.source_length or item.output_length)
        if not items:
            return cls.identity(0)

        source_length = 0
        output_length = 0
        source_left: list[int] = []
        source_right: list[int] = []
        output_left: list[int] = []
        output_right: list[int] = []
        for index, item in enumerate(items):
            source_left_values = item.source_left if index == 0 else item.source_left[1:]
            source_right_values = item.source_right if index == 0 else item.source_right[1:]
            output_left_values = item.output_left if index == 0 else item.output_left[1:]
            output_right_values = item.output_right if index == 0 else item.output_right[1:]
            source_left.extend(value + output_length for value in source_left_values)
            source_right.extend(value + output_length for value in source_right_values)
            output_left.extend(value + source_length for value in output_left_values)
            output_right.extend(value + source_length for value in output_right_values)
            source_length += item.source_length
            output_length += item.output_length
        return cls(
            source_length,
            output_length,
            tuple(source_left),
            tuple(source_right),
            tuple(output_left),
            tuple(output_right),
        )

    def source_to_output(self, position: int, *, bias: Literal["left", "right"] = "left") -> int:
        return self._map_position(
            position, bias, self.source_length, self.source_left, self.source_right
        )

    def output_to_source(self, position: int, *, bias: Literal["left", "right"] = "left") -> int:
        return self._map_position(
            position, bias, self.output_length, self.output_left, self.output_right
        )

    @staticmethod
    def _map_position(
        position: int,
        bias: Literal["left", "right"],
        length: int,
        left: tuple[int, ...],
        right: tuple[int, ...],
    ) -> int:
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or not 0 <= position <= length
        ):
            raise ValueError(f"position must be an integer in 0..{length}")
        if bias != "left" and bias != "right":
            raise ValueError("bias must be 'left' or 'right'")
        return (left if bias == "left" else right)[position]

    def map_source_span(self, start: int, end: int) -> tuple[int, int]:
        self._validate_span(start, end, self.source_length)
        return self.source_to_output(start, bias="left"), self.source_to_output(end, bias="right")

    def map_output_span(self, start: int, end: int) -> tuple[int, int]:
        self._validate_span(start, end, self.output_length)
        return self.output_to_source(start, bias="left"), self.output_to_source(end, bias="right")

    @staticmethod
    def _validate_span(start: int, end: int, length: int) -> None:
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start <= end <= length
        ):
            raise ValueError(f"span must satisfy 0 <= start <= end <= {length}")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_length": self.source_length,
            "output_length": self.output_length,
            "source_left": list(self.source_left),
            "source_right": list(self.source_right),
            "output_left": list(self.output_left),
            "output_right": list(self.output_right),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SourceOutputMap:
        if not isinstance(data, Mapping):
            raise TypeError("source/output map data must be a mapping")
        try:
            return cls(
                source_length=data["source_length"],
                output_length=data["output_length"],
                source_left=tuple(data["source_left"]),
                source_right=tuple(data["source_right"]),
                output_left=tuple(data["output_left"]),
                output_right=tuple(data["output_right"]),
            )
        except KeyError as exc:
            raise ValueError(f"source/output map data is missing {exc.args[0]!r}") from exc
        except TypeError as exc:
            raise ValueError("source/output map boundary arrays must be iterable") from exc


@dataclass(frozen=True, slots=True)
class PreparedRun:
    unit_id: str
    source_text: str
    spoken_text: str
    language: str
    changes: tuple[SpokenChange, ...]
    issues: tuple[PreparationIssue, ...]
    source_map: SourceOutputMap

    def __post_init__(self) -> None:
        if not isinstance(self.unit_id, str) or not self.unit_id:
            raise ValueError("run unit_id must be a non-empty string")
        if not isinstance(self.language, str) or not self.language.strip():
            raise ValueError("run language must be a non-empty string")
        if not isinstance(self.source_text, str) or not isinstance(self.spoken_text, str):
            raise TypeError("run source_text and spoken_text must be strings")
        if not isinstance(self.source_map, SourceOutputMap):
            raise TypeError("run source_map must be a SourceOutputMap")
        if self.source_map.source_length != len(self.source_text):
            raise ValueError("run source map length differs from source_text")
        if self.source_map.output_length != len(self.spoken_text):
            raise ValueError("run source map length differs from spoken_text")

        changes = tuple(self.changes)
        issues = tuple(self.issues)
        cursor = 0
        delta = 0
        rendered: list[str] = []
        for change in changes:
            if not isinstance(change, SpokenChange):
                raise TypeError("run changes must contain only SpokenChange values")
            if change.unit_id != self.unit_id:
                raise ValueError("prepared change belongs to a different run")
            if change.source_start < cursor or change.source_end > len(self.source_text):
                raise ValueError("prepared changes overlap or exceed source text")
            if self.source_text[change.source_start : change.source_end] != change.source:
                raise ValueError("prepared change source does not match source_text")
            expected_start = change.source_start + delta
            expected_end = expected_start + len(change.replacement)
            if (change.output_start, change.output_end) != (expected_start, expected_end):
                raise ValueError("prepared change output coordinates are inconsistent")
            if self.spoken_text[change.output_start : change.output_end] != change.replacement:
                raise ValueError("prepared change output span does not select its replacement")
            rendered.extend((self.source_text[cursor : change.source_start], change.replacement))
            cursor = change.source_end
            delta += len(change.replacement) - len(change.source)
        rendered.append(self.source_text[cursor:])
        if "".join(rendered) != self.spoken_text:
            raise ValueError("prepared changes do not reconstruct spoken_text")
        if any(not isinstance(issue, PreparationIssue) for issue in issues):
            raise TypeError("run issues must contain only PreparationIssue values")
        object.__setattr__(self, "changes", changes)
        object.__setattr__(self, "issues", issues)

    @property
    def changed(self) -> bool:
        return self.source_text != self.spoken_text

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(issue.message for issue in self.issues if issue.severity == "warning")


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
