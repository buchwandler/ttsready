"""Section selection helpers."""

from __future__ import annotations

import re
from dataclasses import replace

from .models import Document
from .pipeline import source_paragraphs

_RANGE_TOKEN = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_section_range(spec: str, count: int) -> list[int]:
    """Return ordered unique zero-based section indexes from a 1-based selector."""
    value = spec.strip()
    if value.lower() == "all":
        return list(range(count))
    if not value:
        raise ValueError("Section selection cannot be empty")

    selected: list[int] = []
    seen: set[int] = set()
    for token in value.split(","):
        match = _RANGE_TOKEN.fullmatch(token.strip())
        if match is None:
            raise ValueError(f"Invalid section selector token: {token!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < 1:
            raise ValueError("Section indexes are 1-based and must be at least 1")
        if end < start:
            raise ValueError(f"Section range is reversed: {token!r}")
        for index in range(start, end + 1):
            if index > count:
                raise ValueError(
                    f"Section {index} is out of range; this document has {count} sections."
                )
            zero_based = index - 1
            if zero_based not in seen:
                seen.add(zero_based)
                selected.append(zero_based)
    return selected

def select_document_sections(document: Document, indices: list[int]) -> Document:
    """Return a document view containing sections in the requested order."""
    selected = [
        replace(
            document.sections[index],
            source_index=document.sections[index].source_index or index + 1,
        )
        for index in indices
    ]
    return replace(
        document,
        sections=selected,
        original_section_count=document.original_section_count or len(document.sections),
    )


def format_section_listing(document: Document) -> str:
    """Render a stable table of source sections without preparing their text."""
    rows = []
    for index, section in enumerate(document.sections, start=1):
        title = (
            section.title.strip()
            if section.title and section.title.strip()
            else f"Section {index}"
        )
        title = f"{'  ' * max(section.level - 1, 0)}{title}"
        rows.append(
            (index, section.level, len(section.text), len(source_paragraphs(section.text)), title)
        )

    index_width = max(len("#"), len(str(len(rows))))
    level_width = max(len("Level"), *(len(str(row[1])) for row in rows))
    chars_width = max(len("Characters"), *(len(f"{row[2]:,}") for row in rows))
    paragraphs_width = max(len("Paragraphs"), *(len(str(row[3])) for row in rows))
    lines = [
        f"{'#':>{index_width}}  {'Level':>{level_width}}  "
        f"{'Characters':>{chars_width}}  {'Paragraphs':>{paragraphs_width}}  Title"
    ]
    for index, level, char_count, paragraph_count, title in rows:
        lines.append(
            f"{index:>{index_width}}  {level:>{level_width}}  "
            f"{char_count:>{chars_width},}  {paragraph_count:>{paragraphs_width}}  {title}"
        )
    return "\n".join(lines)
