from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ttsready.models import Document, Section, SourceInfo
from ttsready.readers import EpubReader
from ttsready.selection import format_section_listing, parse_section_range, select_document_sections


def make_document(sections: list[Section] | None = None) -> Document:
    return Document(
        source=SourceInfo(Path("sample.md"), "markdown"),
        sections=sections
        or [
            Section("s1", "First paragraph.\n\nSecond paragraph.", "One"),
            Section("s2", "Nested prose.", "Interlude", level=2, parent_id="s1"),
            Section("s3", ""),
        ],
        metadata={"title": "Sample"},
    )


def test_parse_section_range_preserves_order_and_removes_duplicates() -> None:
    assert parse_section_range("3,1-2,2", 4) == [2, 0, 1]
    assert parse_section_range("all", 3) == [0, 1, 2]


@pytest.mark.parametrize("spec", ["0", "-1", "3-1", "1,,2", "abc", "6"])
def test_parse_section_range_rejects_invalid_selectors(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_section_range(spec, 5)


def test_select_document_sections_preserves_document_and_requested_order() -> None:
    document = make_document()
    selected = select_document_sections(document, [2, 0])

    assert [section.id for section in selected.sections] == ["s3", "s1"]
    assert selected.source is document.source
    assert selected.metadata is document.metadata
    assert [section.id for section in document.sections] == ["s1", "s2", "s3"]


def test_format_section_listing_includes_order_hierarchy_counts_and_fallback_title() -> None:
    listing = format_section_listing(make_document())

    assert "#  Level  Characters  Paragraphs  Title" in listing
    assert "1      1          35           2  One" in listing
    assert "2      2          13           1    Interlude" in listing
    assert "3      1           0           0  Section 3" in listing


def test_epub_reader_preserves_chapter_hierarchy(monkeypatch, tmp_path: Path) -> None:
    chapter = SimpleNamespace(
        id="chapter-2",
        text="Nested chapter text.",
        title="Interlude",
        href="text/chapter2.xhtml",
        parent_id="chapter-1",
        level=2,
    )
    metadata = SimpleNamespace(
        title="Book", authors=[], language=None, publisher=None, identifier=None
    )

    class FakeParser:
        def __init__(self, source: str) -> None:
            assert source.endswith("book.epub")

        def get_chapter_documents(self):
            return [chapter]

        def get_metadata(self):
            return metadata

    monkeypatch.setitem(sys.modules, "epub2text", SimpleNamespace(EPUBParser=FakeParser))
    document = EpubReader().load(tmp_path / "book.epub")

    assert document.sections[0].parent_id == "chapter-1"
    assert document.sections[0].level == 2
