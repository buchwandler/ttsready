from __future__ import annotations

from pathlib import Path

import pytest

from ttsready.models import Document, PreparedParagraph, Section, SourceInfo
from ttsready.output import (
    OutputArtifact,
    OutputPlan,
    paragraphs_for_section,
    plan_output,
    render_artifacts,
    validate_output_plan,
    write_artifacts,
)


def make_document(source: Path) -> Document:
    return Document(
        source=SourceInfo(source, "epub"),
        sections=[
            Section("s3", "Third body.", "Same / title\n"),
            Section("s1", "First body.", "Same / title\n"),
            Section("s4", "No title body."),
        ],
        metadata={"title": "Book", "author": "Author", "publisher": "Press"},
    )


def test_single_output_plan_defaults_to_txt_and_rejects_ssmd_suffix(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    document = make_document(source)

    plan = plan_output(document)
    assert plan.layout == "single"
    assert plan.artifacts[0].path == tmp_path / "book.txt"

    with pytest.raises(ValueError, match="SSMD output is no longer supported"):
        plan_output(document, output=tmp_path / "book.ssmd")


def test_chapter_output_plan_uses_selected_order_and_safe_unique_names(tmp_path: Path) -> None:
    document = make_document(tmp_path / "book.epub")
    plan = plan_output(document, output=tmp_path / "selected", layout="chapters")

    assert [artifact.path.name for artifact in plan.artifacts] == [
        "001-Same-title.txt",
        "002-Same-title.txt",
        "003-section.txt",
    ]
    assert [artifact.section_id for artifact in plan.artifacts] == ["s3", "s1", "s4"]


def test_chapter_artifacts_render_from_one_prepared_list_and_write(tmp_path: Path) -> None:
    document = make_document(tmp_path / "book.epub")
    plan = plan_output(document, output=tmp_path / "chapters", layout="chapters")
    paragraphs = [
        PreparedParagraph("Same / title", "s3", -1, is_title=True),
        PreparedParagraph("Third body.", "s3", 0),
        PreparedParagraph("Same / title", "s1", -1, is_title=True),
        PreparedParagraph("First body.", "s1", 0),
        PreparedParagraph("No title body.", "s4", 0),
    ]
    rendered = render_artifacts(plan, paragraphs)

    assert len(rendered) == 3
    assert rendered[0][1] == "Same / title\n\nThird body.\n"
    assert rendered[1][1] == "Same / title\n\nFirst body.\n"
    assert rendered[2][1] == "No title body.\n"
    assert [item.text for item in paragraphs_for_section(paragraphs, "s3")] == [
        "Same / title",
        "Third body.",
    ]
    write_artifacts(plan, rendered)
    assert (tmp_path / "chapters" / "001-Same-title.txt").read_text() == rendered[0][1]
    assert (tmp_path / "chapters" / "002-Same-title.txt").read_text() == rendered[1][1]


def test_output_plan_rejects_invalid_layout_path_types(tmp_path: Path) -> None:
    document = make_document(tmp_path / "book.epub")
    directory = tmp_path / "existing-dir"
    directory.mkdir()
    with pytest.raises(ValueError, match="file path"):
        plan_output(document, output=directory)

    file_path = tmp_path / "existing-file"
    file_path.write_text("x")
    with pytest.raises(ValueError, match="not a directory"):
        plan_output(document, output=file_path, layout="chapters")


def test_validate_output_plan_rejects_duplicate_paths(tmp_path: Path) -> None:
    path = tmp_path / "same.txt"
    plan = OutputPlan(
        "chapters",
        tmp_path,
        (
            OutputArtifact("s1", path),
            OutputArtifact("s2", path),
        ),
    )

    with pytest.raises(ValueError, match="duplicate"):
        validate_output_plan(plan)
