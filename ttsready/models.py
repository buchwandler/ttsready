"""Small source-neutral models used by the ttsready pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

OutputFormat = Literal["txt", "ssmd"]


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


@dataclass(slots=True)
class Document:
    source: SourceInfo
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreparedParagraph:
    text: str
    section_id: str
    source_paragraph: int
    part: int = 0
    is_title: bool = False


@dataclass(slots=True)
class ConversionResult:
    document: Document
    paragraphs: list[PreparedParagraph]
    text: str
    output_format: OutputFormat
    language: str
    warnings: list[str] = field(default_factory=list)
