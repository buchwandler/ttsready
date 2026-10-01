"""Small source-neutral models used by the ttsready pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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

@dataclass(slots=True)
class Document:
    source: SourceInfo
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)
    original_section_count: int | None = None


@dataclass(frozen=True, slots=True)
class PreparedParagraph:
    text: str
    section_id: str
    source_paragraph: int
    part: int = 0
    is_title: bool = False


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

    source_sha256: str | None = None
    tool_versions: dict[str, str] = field(default_factory=dict)
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


@dataclass(slots=True)
class ConversionResult:
    document: Document
    paragraphs: list[PreparedParagraph]
    text: str
    language: str
    warnings: list[str] = field(default_factory=list)
    report: ConversionReport | None = None
