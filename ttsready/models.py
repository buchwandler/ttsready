"""Small source-neutral models used by the ttsready pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssmd import ParseStructureResult

from .errors import TTSReadyError

SEQUENCE_FALLBACK_MODES = frozenset({"spell", "preserve"})
DEFAULT_SEQUENCE_FALLBACK_MODE = "spell"
_MISSING_SEQUENCE_FALLBACK_MODE = object()


def resolve_sequence_fallback_mode(value: object = _MISSING_SEQUENCE_FALLBACK_MODE) -> str:
    if value is _MISSING_SEQUENCE_FALLBACK_MODE:
        return DEFAULT_SEQUENCE_FALLBACK_MODE
    if not isinstance(value, str) or value not in SEQUENCE_FALLBACK_MODES:
        raise TTSReadyError("sequence_fallback_mode must be 'spell' or 'preserve'")
    return value


@dataclass(frozen=True, slots=True)
class RenderOptions:
    line_width: int | None = None
    paragraph_breaks: int = 2

    def __post_init__(self) -> None:
        if self.line_width is not None and self.line_width < 1:
            raise ValueError("line_width must be at least 1")
        if self.paragraph_breaks not in {0, 1, 2}:
            raise ValueError("paragraph_breaks must be 0, 1, or 2")


@dataclass(frozen=True, slots=True)
class SourceInfo:
    path: Path
    format: str
    media_type: str | None = None


@dataclass(slots=True)
class Section:
    id: str
    text: str
    title: str | None = None
    source_ref: str | None = None
    parent_id: str | None = None
    level: int = 1
    source_index: int | None = None

    ssmd: str | None = None
    structure: ParseStructureResult | None = None
    chapter_sha256: str | None = None


@dataclass(slots=True)
class Document:
    source: SourceInfo
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)
    original_section_count: int | None = None
    source_sha256: str | None = None
    content_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationProfile:
    language: str
    use_spacy: bool = False
    symbol_mode: str = "none"
    normalize_unicode: bool = False
    normalize_whitespace: bool = False
    strip_outer_whitespace: bool = False
    collapse_horizontal_whitespace: bool = False
    normalize_line_whitespace: bool = False
    collapse_blank_lines: bool = False
    generic_acronym_mode: str = "known_only"
    sequence_fallback_mode: str = DEFAULT_SEQUENCE_FALLBACK_MODE
    expand_structured: bool = True
    expand_numbers: bool = True


@dataclass(frozen=True, slots=True)
class PreparedSegment:
    text: str
    chapter_id: str
    source_paragraph: int
    part: int = 0
    is_title: bool = False
    language: str = "en"
    voice: str | None = None
    source_context_id: str | None = None
    render_group: str | None = None

    @property
    def section_id(self) -> str:
        return self.chapter_id


PreparedParagraph = PreparedSegment


@dataclass(frozen=True, slots=True)
class SentenceContext:
    id: str
    index: int
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ContextRecord:
    id: str
    section_id: str
    section_locator: str
    section_index: int
    source_paragraph: int
    is_title: bool
    source_text: str
    spoken_text: str
    source_sentences: tuple[SentenceContext, ...]
    spoken_sentences: tuple[SentenceContext, ...]


@dataclass(frozen=True, slots=True)
class LexicalOccurrence:
    context_id: str
    start: int
    end: int
    sentence_id: str | None


@dataclass(frozen=True, slots=True)
class LexicalFinding:
    id: str
    surface: str
    normalized: str
    count: int
    known: bool | None
    frequency_rank: int | None
    frequency_count: int | None
    reasons: tuple[str, ...]
    occurrences: tuple[LexicalOccurrence, ...]


@dataclass(frozen=True, slots=True)
class LexicalReviewReport:
    source_path: str
    language: str
    source_sha256: str | None
    tool_versions: dict[str, str]
    findings: tuple[LexicalFinding, ...]
    schema: str = "ttsready.lexical-review.v1"


@dataclass(frozen=True, slots=True)
class SpokenChange:
    id: str
    context_id: str
    section_id: str
    section_index: int
    source_paragraph: int
    source: str
    replacement: str
    stages: tuple[str, ...]
    kind: str
    rule: str | None
    recognition_domain: str | None
    source_start: int
    source_end: int
    output_start: int
    output_end: int
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SpokenformStats:
    calls: int = 0
    changed_calls: int = 0
    paragraphs_processed: int = 0
    paragraphs_changed: int = 0
    source_replacements: int = 0
    stage_edits: dict[str, int] = field(default_factory=dict)
    rules: dict[str, int] = field(default_factory=dict)
    domains: dict[str, int] = field(default_factory=dict)
    warnings: int = 0
    structured_numeric_edits: int = 0
    source_digit_replacements: int = 0

    @property
    def abbreviation_edits(self) -> int:
        return self.stage_edits.get("abbreviations", 0)

    @property
    def number_edits(self) -> int:
        return self.stage_edits.get("numbers", 0)

    @property
    def structured_edits(self) -> int:
        return self.stage_edits.get("structured", 0)


@dataclass(slots=True)
class SectionStats:
    section_id: str
    index: int
    title: str | None
    level: int
    input_chars: int
    source_paragraphs: int
    chapter_sha256: str | None = None
    prepared_paragraphs: int = 0
    spokenform_changes: int = 0
    output_chars: int = 0


@dataclass(slots=True)
class ConversionReport:
    source_path: str
    input_format: str
    document_title: str | None
    metadata_language: str | None
    requested_language: str | None
    effective_language: str
    total_sections: int
    selected_sections: int
    input_chars: int
    source_paragraphs: int
    sections: list[SectionStats] = field(default_factory=list)

    workspace_type: str | None = None
    workspace_status: str | None = None
    dirty_chapters: list[str] = field(default_factory=list)
    stored_sequence_fallback_mode: str | None = None
    effective_sequence_fallback_mode: str | None = None
    ssmd_semantics: dict[str, Any] = field(default_factory=dict)
    preparation_trace: dict[str, Any] | None = None
    source_sha256: str | None = None
    tool_versions: dict[str, str] = field(default_factory=dict)
    content_fingerprint: str | None = None
    analysis_id: str | None = None
    normalization_profile: dict[str, Any] = field(default_factory=dict)
    normalization_options_sha256: str | None = None
    pronunciation_profile_sha256: str | None = None
    normalization_profile_sha256: str | None = None
    runtime_fingerprint: str | None = None
    prepared_output_sha256: str | None = None
    spokenform: SpokenformStats = field(default_factory=SpokenformStats)
    contexts: list[ContextRecord] = field(default_factory=list)
    changes: list[SpokenChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_prepared_items: int = 0
    split_source_items: int = 0
    prepared_paragraphs: int = 0
    added_split_parts: int = 0
    max_prepared_paragraph_chars: int = 0
    output_chars: int = 0
    output_lines: int = 0
    output_files: int = 1
    output_layout: str = "single"
    destinations: list[str] = field(default_factory=list)
    schema: str = "ttsready.report.v2"


@dataclass(frozen=True, slots=True)
class TTSPlan:
    document: Document
    segments: tuple[PreparedSegment, ...]
    language: str
    report: ConversionReport


@dataclass(slots=True)
class ConversionResult:
    document: Document
    paragraphs: list[PreparedParagraph]
    text: str
    language: str
    warnings: list[str] = field(default_factory=list)
    report: ConversionReport | None = None
    plan: TTSPlan | None = None
