from __future__ import annotations

import json
from pathlib import Path

import pytest

from ttsready.models import (
    ContextRecord,
    ConversionReport,
    Document,
    Section,
    SectionStats,
    SentenceContext,
    SourceInfo,
    SpokenChange,
    SpokenformStats,
)
from ttsready.output import OutputArtifact, OutputPlan
from ttsready.pipeline import prepare as prepare_document
from ttsready.reporting import (
    format_preflight,
    json_report,
    markdown_report,
    render_report,
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
        total_sections=2,
        selected_sections=1,
        input_chars=10,
        source_paragraphs=1,
        sections=[SectionStats("s2", 2, "Chapter 2", 1, 10, 1, 1, 1, 20)],
        source_sha256="abc123",
        tool_versions={"ttsready": "0.2.0", "spokenform": "0.4.5"},
        contexts=[
            ContextRecord(
                id="ctx:v1:11111111111111111111",
                section_id="s2",
                section_locator="ref:chapter2.xhtml",
                section_index=2,
                source_paragraph=0,
                is_title=False,
                source_text="Dr. Smith is here.",
                spoken_text="Doctor Smith is here.",
                source_sentences=(SentenceContext("sent:v1:1", 0, "Dr. Smith is here.", 0, 18),),
                spoken_sentences=(SentenceContext("sent:v1:2", 0, "Doctor Smith is here.", 0, 21),),
            )
        ],
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
                id="chg:v1:0123456789abcdefabcd",
                context_id="ctx:v1:11111111111111111111",
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

    assert data["schema"] == "ttsready.report.v2"
    assert data["source_sha256"] == "abc123"
    assert data["tool_versions"]["spokenform"] == "0.4.5"
    assert data["contexts"][0]["source_sentences"][0]["text"] == "Dr. Smith is here."
    assert data["contexts"][0]["spoken_sentences"][0]["end"] == 21
    assert data["changes"][0]["context_id"] == "ctx:v1:11111111111111111111"
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
    assert "| ID | Paragraph | Source | Replacement" in rendered
    assert "`chg:v1:0123456789abcdefabcd`" in rendered
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

    assert json.loads(json_path.read_text())["schema"] == "ttsready.report.v2"
    assert markdown_path.read_text().startswith("# ttsready report\n")


def test_preflight_lists_exact_single_and_chapter_destinations(tmp_path: Path) -> None:
    report = make_report()
    single_plan = OutputPlan("single", tmp_path, (OutputArtifact(None, tmp_path / "book.txt"),))
    chapter_plan = OutputPlan(
        "chapters",
        tmp_path / "chapters",
        (OutputArtifact("s2", tmp_path / "chapters" / "002-chapter-2.txt"),),
    )

    assert "Would write:\n  " + str(tmp_path / "book.txt") in format_preflight(report, single_plan)
    assert str(tmp_path / "chapters" / "002-chapter-2.txt") in format_preflight(
        report, chapter_plan
    )


def test_report_only_markdown_uses_prepared_preview_wording() -> None:
    report = make_report()
    report.output_files = 0
    report.destinations = []

    rendered = markdown_report(report)

    assert "## Prepared text preview" in rendered
    assert "- Files written: 0" in rendered
    assert "- Preview format: txt" in rendered
    assert "## Output" not in rendered


def test_render_report_selects_markdown_or_json() -> None:
    report = make_report()

    assert render_report(report, "md").startswith("# ttsready report\n")
    assert json.loads(render_report(report, "json"))["schema"] == "ttsready.report.v2"
    with pytest.raises(ValueError, match="format"):
        render_report(report, "txt")


def test_write_report_accepts_explicit_format_without_suffix_and_rejects_conflict(
    tmp_path: Path,
) -> None:
    report = make_report()
    extensionless = tmp_path / "reports" / "report"
    write_report(extensionless, report, format="json")

    assert json.loads(extensionless.read_text(encoding="utf-8"))["schema"] == ("ttsready.report.v2")
    with pytest.raises(ValueError, match="conflicts"):
        write_report(tmp_path / "report.md", report, format="json")


def test_markdown_report_omits_residual_fallback_from_real_pipeline() -> None:
    source_text = "in-system target/destination Barish-Estranza ART EVAC"
    document = Document(
        SourceInfo(Path("residual.txt"), "text", "text/plain"),
        [Section("section-1", source_text)],
        {"title": "Residual prose", "language": "en"},
    )
    prepared = prepare_document(document, language="en")
    report = prepared.report
    assert report is not None
    rendered = markdown_report(report)

    assert all(
        phrase in prepared.text
        for phrase in ("in-system", "target/destination", "Barish-Estranza", "ART", "EVAC")
    )
    assert "fallback.sequence" not in rendered
    assert "| sequence_fallback |" not in rendered
    assert "fallback.sequence" not in report.spokenform.rules
    assert "sequence_fallback" not in report.spokenform.stage_edits
