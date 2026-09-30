from __future__ import annotations

import json
from pathlib import Path

import pytest

from ttsready.models import ConversionReport, SectionStats, SpokenChange, SpokenformStats
from ttsready.output import OutputArtifact, OutputPlan
from ttsready.reporting import (
    format_preflight,
    json_report,
    markdown_report,
    report_format,
    validate_report_path,
    write_report,
)


def make_report() -> ConversionReport:
    return ConversionReport(
        source_path="book.epub",
        input_format="epub",
        document_title="Book",
        metadata_language="en",
        requested_language="en-US",
        effective_language="en-US",
        output_format="txt",
        total_sections=2,
        selected_sections=1,
        input_chars=10,
        source_paragraphs=1,
        sections=[SectionStats("s2", 2, "Chapter 2", 1, 10, 1, 1, 1, 20)],
        spokenform=SpokenformStats(
            calls=1,
            changed_calls=1,
            source_replacements=1,
            stage_edits={"abbreviations": 1},
            rules={"abbr:Dr.": 1},
            domains={"medical": 1},
            warnings=2,
        ),
        changes=[
            SpokenChange(
                section_id="s2",
                section_index=2,
                source_paragraph=0,
                source="Dr. |\nSmith",
                replacement="Doctor Smith",
                stages=("abbreviations",),
                kind="abbreviation",
                rule="abbr:Dr.",
                recognition_domain="medical",
                source_start=0,
                source_end=11,
                output_start=0,
                output_end=13,
            )
        ],
        warnings=["warning | one\ncontinued", "warning | one\ncontinued"],
        source_prepared_items=1,
        split_source_items=1,
        prepared_paragraphs=2,
        added_split_parts=1,
        max_prepared_paragraph_chars=20,
        output_chars=20,
        output_lines=2,
        output_files=1,
        destinations=["book.txt"],
    )


def test_json_report_preserves_schema_provenance_and_raw_warnings() -> None:
    data = json.loads(json_report(make_report()))

    assert data["schema"] == "ttsready.report.v1"
    assert data["spokenform"]["abbreviation_edits"] == 1
    assert data["changes"][0]["source"] == "Dr. |\nSmith"
    assert data["changes"][0]["source_start"] == 0
    assert data["changes"][0]["rule"] == "abbr:Dr."
    assert data["sections"][0]["index"] == 2
    assert data["warnings"] == ["warning | one\ncontinued"] * 2


def test_markdown_report_escapes_table_cells_and_groups_warnings() -> None:
    rendered = markdown_report(make_report())

    assert "Dr. \\|<br>Smith" in rendered
    assert "Doctor Smith" in rendered
    assert "warning \\| one<br>continued (x2)" in rendered
    assert "Source span | Output span" in rendered
    assert "Abbreviation edits: 1" in rendered


def test_report_path_format_and_validation(tmp_path: Path) -> None:
    assert report_format(tmp_path / "report.md") == "md"
    assert report_format(tmp_path / "report.json") == "json"
    with pytest.raises(ValueError, match="suffix"):
        report_format(tmp_path / "report.txt")

    directory = tmp_path / "directory.md"
    directory.mkdir()
    with pytest.raises(ValueError, match="directory"):
        validate_report_path(directory)


def test_write_report_outputs_json_and_markdown(tmp_path: Path) -> None:
    report = make_report()
    json_path = tmp_path / "reports" / "report.json"
    markdown_path = tmp_path / "reports" / "report.md"

    write_report(json_path, report)
    write_report(markdown_path, report)

    assert json.loads(json_path.read_text())["schema"] == "ttsready.report.v1"
    assert markdown_path.read_text().startswith("# ttsready report\n")


def test_preflight_lists_exact_single_and_chapter_destinations(tmp_path: Path) -> None:
    report = make_report()
    single_plan = OutputPlan(
        "single", tmp_path, (OutputArtifact(None, tmp_path / "book.txt", "txt"),)
    )
    chapter_plan = OutputPlan(
        "chapters",
        tmp_path / "chapters",
        (OutputArtifact("s2", tmp_path / "chapters" / "002-chapter-2.txt", "txt"),),
    )

    assert "Would write:\n  " + str(tmp_path / "book.txt") in format_preflight(
        report, single_plan
    )
    assert str(tmp_path / "chapters" / "002-chapter-2.txt") in format_preflight(
        report, chapter_plan
    )
