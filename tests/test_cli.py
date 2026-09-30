from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import ttsready.cli as cli
from ttsready.models import Document, Section, SourceInfo

runner = CliRunner()


def make_document(source: Path) -> Document:
    return Document(
        source=SourceInfo(source, "markdown"),
        sections=[
            Section("s1", "First.", "One"),
            Section("s2", "Nested.", "Two", level=2),
            Section("s3", "Third.", "Three"),
        ],
        metadata={"title": "Book"},
    )


def test_list_sections_does_not_prepare_or_write_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(cli, "load", lambda _: make_document(source))

    def fail_prepare(*args, **kwargs):
        raise AssertionError("listing must not prepare content")

    monkeypatch.setattr(cli, "prepare_document", fail_prepare)
    result = runner.invoke(cli.app, [str(source), "--list-chapters"])

    assert result.exit_code == 0, result.output
    assert "One" in result.output
    assert "    Two" in result.output
    assert not (tmp_path / "book.txt").exists()


def test_chapter_selection_prepares_only_selected_sections_in_order(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    prepared_sections: list[str] = []

    real_prepare = cli.prepare_document

    def track_prepare(document: Document, **kwargs):
        prepared_sections.extend(section.id for section in document.sections)
        return real_prepare(document, **kwargs)
    monkeypatch.setattr(cli, "load", lambda _: make_document(source))
    monkeypatch.setattr(cli, "prepare_document", track_prepare)

    output = tmp_path / "selected.txt"
    result = runner.invoke(
        cli.app,
        [
            str(source),
            "--chapters",
            "3,1-2,2",
            "--no-spokenform",
            "--no-titles",
            "-o",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert prepared_sections == ["s3", "s1", "s2"]
    assert output.read_text(encoding="utf-8") == "Third.\n\nFirst.\n\nNested.\n"


def test_preflight_runs_conversion_and_writes_only_requested_report(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(cli, "load", lambda _: make_document(source))
    output = tmp_path / "planned.txt"
    report_path = tmp_path / "preflight.json"

    result = runner.invoke(
        cli.app,
        [
            str(source),
            "--preflight",
            "--no-spokenform",
            "--no-titles",
            "-o",
            str(output),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Preflight: no TTS files were written." in result.output
    assert f"Would write:\n  {output}" in result.output
    assert not output.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["schema"] == "ttsready.report.v1"
    assert data["destinations"] == [str(output)]
    assert data["prepared_paragraphs"] == 3


def test_chapter_cli_uses_selected_order_format_and_original_indexes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(cli, "load", lambda _: make_document(source))
    directory = tmp_path / "chapters.ssmd"
    report_path = tmp_path / "chapters.json"

    result = runner.invoke(
        cli.app,
        [
            str(source),
            "--chapters",
            "3,1",
            "--output-layout",
            "chapters",
            "--no-spokenform",
            "--no-titles",
            "-o",
            str(directory),
            "--report",
            str(report_path),
            "--stats",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Sections: 2 / 3" in result.output
    assert (directory / "001-Three.txt").read_text() == "Third.\n"
    assert (directory / "002-One.txt").read_text() == "First.\n"
    assert not list(directory.glob("*.ssmd"))
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["total_sections"] == 3
    assert data["selected_sections"] == 2
    assert [section["index"] for section in data["sections"]] == [3, 1]
    assert data["output_layout"] == "chapters"
    assert data["output_files"] == 2


def test_report_collision_and_bad_suffix_fail_before_tts_writes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(cli, "load", lambda _: make_document(source))

    collision = tmp_path / "same.json"
    collision_result = runner.invoke(
        cli.app,
        [
            str(source),
            "--no-spokenform",
            "--format",
            "txt",
            "-o",
            str(collision),
            "--report",
            str(collision),
        ],
    )
    assert collision_result.exit_code == 2
    assert "Report path must not match" in collision_result.output
    assert not collision.exists()

    output = tmp_path / "output.txt"
    suffix_result = runner.invoke(
        cli.app,
        [str(source), "--no-spokenform", "-o", str(output), "--report", "report.txt"],
    )
    assert suffix_result.exit_code == 2
    assert ".md or .json" in suffix_result.output
    assert not output.exists()


def test_single_explicit_format_overrides_output_suffix(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(cli, "load", lambda _: make_document(source))
    output = tmp_path / "output.ssmd"

    result = runner.invoke(
        cli.app,
        [str(source), "--no-spokenform", "--no-titles", "--format", "txt", "-o", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == "First.\n\nNested.\n\nThird.\n"
