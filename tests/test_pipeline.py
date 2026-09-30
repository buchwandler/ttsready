from __future__ import annotations

from pathlib import Path

import ttsready.pipeline as pipeline
from ttsready.models import Document, Section, SourceInfo


def document(text: str, *, title: str | None = None) -> Document:
    return Document(
        source=SourceInfo(Path("sample.txt"), "text", "text/plain"),
        sections=[Section("section-1", text, title=title)],
        metadata={"title": "Sample", "language": "en"},
    )


def test_source_paragraphs_join_soft_line_wraps() -> None:
    text = "First line\ncontinues here.\n\nSecond paragraph."
    assert pipeline.source_paragraphs(text) == [
        "First line continues here.",
        "Second paragraph.",
    ]


def test_prepare_without_spokenform_keeps_short_paragraphs() -> None:
    result = pipeline.prepare(
        document("One paragraph.\n\nTwo paragraph."),
        apply_spokenform=False,
        max_paragraph_chars=100,
    )
    assert [p.text for p in result.paragraphs] == ["One paragraph.", "Two paragraph."]
    assert result.text == "One paragraph.\n\nTwo paragraph.\n"


def test_title_is_optional() -> None:
    with_title = pipeline.prepare(
        document("Body.", title="Chapter One"),
        apply_spokenform=False,
        include_titles=True,
    )
    without_title = pipeline.prepare(
        document("Body.", title="Chapter One"),
        apply_spokenform=False,
        include_titles=False,
    )
    assert [p.text for p in with_title.paragraphs] == ["Chapter One", "Body."]
    assert [p.text for p in without_title.paragraphs] == ["Body."]


def test_spokenform_runs_before_length_split(monkeypatch) -> None:
    calls: list[str] = []

    def fake_spoken(text: str, *, language: str, enabled: bool):
        calls.append(text)
        return text + " expanded", []

    def fake_split(text: str, *, max_chars: int | None, language: str):
        assert text.endswith(" expanded")
        return ["part one", "part two"]

    monkeypatch.setattr(pipeline, "_spoken", fake_spoken)
    monkeypatch.setattr(pipeline, "_split_oversized", fake_split)

    result = pipeline.prepare(document("source"), max_paragraph_chars=10)
    assert calls == ["source"]
    assert [p.text for p in result.paragraphs] == ["part one", "part two"]
