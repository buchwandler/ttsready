from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def prepare_source(monkeypatch, source: Path) -> Document:
    source.write_text("source", encoding="utf-8")
    cache_path = source.parent.parent / f"{source.parent.name}.cache"
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(cache_path))
    document = make_document(source)
    monkeypatch.setattr(cli, "load", lambda _: document)
    return document


def test_root_help_lists_commands_without_source_argument() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0, result.output
    for command in (
        "convert",
        "export",
        "preview",
        "chapters",
        "preflight",
        "report",
        "lock",
        "verify",
        "freeze",
        "context",
    ):
        assert command in result.output
    assert "--version" in result.output
    assert "Arguments:" not in result.output
    assert "--list-chapters" not in result.output
    assert "--preflight" not in result.output
    assert "--report" not in result.output


def test_root_without_args_shows_help() -> None:
    result = runner.invoke(cli.app, [])

    assert result.exit_code == 2
    for command in (
        "convert",
        "export",
        "preview",
        "chapters",
        "preflight",
        "report",
        "lock",
        "verify",
        "freeze",
        "context",
    ):
        assert command in result.output


def test_version_is_global() -> None:
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == cli.__version__


@pytest.mark.parametrize(
    ("command", "required", "forbidden"),
    [
        ("convert", ("--chapters", "--layout", "--stats"), ("--report", "--preflight", "--format")),
        ("chapters", ("List chapters/sections",), ("--language", "--output", "--spokenform")),
        (
            "preflight",
            ("--chapters", "--layout", "--fail-on-warning"),
            ("--stats", "--report", "--format"),
        ),
        ("report", ("md|json", "--chapters", "--output"), ("--layout", "--line-width", "--stats")),
        (
            "context",
            ("--json", "--bug-report", "--paragraph", "ID"),
            ("--format", "--unknown-only"),
        ),
        (
            "review",
            ("--unknown-only", "--max-frequency-rank", "--lexhint-variant", "md|json"),
            ("--spokenform", "--config"),
        ),
    ],
)
def test_command_help_exposes_only_relevant_options(
    command: str, required: tuple[str, ...], forbidden: tuple[str, ...]
) -> None:
    result = runner.invoke(cli.app, [command, "--help"])

    assert result.exit_code == 0, result.output
    for value in required:
        assert value in result.output
    for value in forbidden:
        assert value not in result.output


def test_chapters_command_does_not_prepare_or_write_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)

    def fail_prepare(*args, **kwargs):
        raise AssertionError("chapters must not prepare content")

    monkeypatch.setattr(cli, "prepare_document", fail_prepare)
    monkeypatch.setattr(
        cli,
        "plan_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not plan output")),
    )
    result = runner.invoke(cli.app, ["chapters", str(source)])

    assert result.exit_code == 0, result.output
    assert "One" in result.output
    assert "    Two" in result.output
    assert not (tmp_path / "book.txt").exists()


def test_convert_prepares_only_selected_sections_in_requested_order(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    document = prepare_source(monkeypatch, source)
    prepared_sections: list[str] = []
    real_prepare = cli.prepare_document

    def track_prepare(selected: Document, **kwargs):
        prepared_sections.extend(section.id for section in selected.sections)
        return real_prepare(selected, **kwargs)

    monkeypatch.setattr(cli, "prepare_document", track_prepare)
    output = tmp_path / "selected.txt"
    result = runner.invoke(
        cli.app,
        [
            "convert",
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
    assert "Converted book.md" in result.output
    assert "Chapters: 3" in result.output
    assert document.sections[0].id == "s1"


def test_convert_chapter_layout_uses_selected_order_and_safe_names(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    output_dir = tmp_path / "chapters"

    result = runner.invoke(
        cli.app,
        [
            "convert",
            str(source),
            "--chapters",
            "3,1",
            "--layout",
            "chapters",
            "--no-spokenform",
            "--no-titles",
            "-o",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / "001-Three.txt").read_text(encoding="utf-8") == "Third.\n"
    assert (output_dir / "002-One.txt").read_text(encoding="utf-8") == "First.\n"
    assert len(list(output_dir.iterdir())) == 2


def test_ssmd_is_not_an_output_choice(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    output = tmp_path / "output.ssmd"

    result = runner.invoke(
        cli.app,
        ["convert", str(source), "--no-spokenform", "--no-titles", "-o", str(output)],
    )

    assert result.exit_code == 2
    assert "SSMD output is no longer supported" in result.output
    assert not output.exists()


def test_preflight_runs_full_render_and_writes_nothing(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    output_dir = tmp_path / "not-created"
    prepared_sections: list[str] = []
    rendered_plans = []
    real_prepare = cli.prepare_document
    real_render = cli.render_artifacts

    def track_prepare(document: Document, **kwargs):
        prepared_sections.extend(section.id for section in document.sections)
        return real_prepare(document, **kwargs)

    def track_render(plan, *args, **kwargs):
        rendered_plans.append(plan)
        return real_render(plan, *args, **kwargs)

    monkeypatch.setattr(cli, "prepare_document", track_prepare)
    monkeypatch.setattr(cli, "render_artifacts", track_render)
    monkeypatch.setattr(
        cli,
        "write_artifacts",
        lambda *args: (_ for _ in ()).throw(AssertionError("preflight must not write")),
    )
    result = runner.invoke(
        cli.app,
        [
            "preflight",
            str(source),
            "--chapters",
            "3,1-2,2",
            "--layout",
            "chapters",
            "-o",
            str(output_dir),
            "--no-spokenform",
            "--no-titles",
        ],
    )

    assert result.exit_code == 0, result.output
    assert prepared_sections == ["s3", "s1", "s2"]
    assert len(rendered_plans) == 1
    assert len(rendered_plans[0].artifacts) == 3
    assert "Preflight passed." in result.output
    assert "Preflight: no TTS files were written." in result.output
    assert "Would write 3 files under:" in result.output
    assert not output_dir.exists()


def test_preflight_fail_on_warning_exits_nonzero_after_diagnostics(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    real_prepare = cli.prepare_document

    def prepare_with_warning(*args, **kwargs):
        result = real_prepare(*args, **kwargs)
        result.warnings.append("sample warning")
        return result

    monkeypatch.setattr(cli, "prepare_document", prepare_with_warning)
    monkeypatch.setattr(
        cli,
        "write_artifacts",
        lambda *args: (_ for _ in ()).throw(AssertionError("preflight must not write")),
    )
    result = runner.invoke(
        cli.app,
        ["preflight", str(source), "--no-spokenform", "--fail-on-warning"],
    )

    assert result.exit_code == 1
    assert "sample warning" in result.output
    assert "Preflight failed" in result.output


def test_report_defaults_to_markdown_stdout_without_tts_writes(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    monkeypatch.setattr(
        cli,
        "write_artifacts",
        lambda *args: (_ for _ in ()).throw(AssertionError("report must not write TTS")),
    )

    result = runner.invoke(cli.app, ["report", str(source), "--no-spokenform", "--no-titles"])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("# ttsready report\n")
    assert "## Prepared text preview" in result.output
    assert "- Files written: 0" in result.output
    assert "## Output" not in result.output
    assert not (tmp_path / "book.txt").exists()


def test_report_json_stdout_and_selected_chapters_preserve_original_indexes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    result = runner.invoke(
        cli.app,
        [
            "report",
            str(source),
            "--chapters",
            "3,1",
            "--format",
            "json",
            "--no-spokenform",
            "--no-titles",
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["schema"] == "ttsready.report.v2"
    assert data["output_files"] == 0
    assert data["destinations"] == []
    assert [section["index"] for section in data["sections"]] == [3, 1]
    assert not (tmp_path / "book.txt").exists()


@pytest.mark.parametrize("suffix", ["md", "json"])
def test_report_writes_only_inferred_report_file(monkeypatch, tmp_path: Path, suffix: str) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    report_path = tmp_path / f"diagnostics.{suffix}"
    monkeypatch.setattr(
        cli,
        "write_artifacts",
        lambda *args: (_ for _ in ()).throw(AssertionError("report must not write TTS")),
    )

    result = runner.invoke(
        cli.app,
        ["report", str(source), "-o", str(report_path), "--no-spokenform", "--no-titles"],
    )

    assert result.exit_code == 0, result.output
    if suffix == "md":
        assert report_path.read_text(encoding="utf-8").startswith("# ttsready report\n")
    else:
        assert json.loads(report_path.read_text(encoding="utf-8"))["schema"] == (
            "ttsready.report.v2"
        )
    assert {path.name for path in tmp_path.iterdir()} == {"book.md", report_path.name}


def test_report_explicit_format_allows_suffixless_path(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    report_path = tmp_path / "diagnostics"

    result = runner.invoke(
        cli.app,
        [
            "report",
            str(source),
            "-o",
            str(report_path),
            "--format",
            "json",
            "--no-spokenform",
            "--no-titles",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(report_path.read_text(encoding="utf-8"))["schema"] == ("ttsready.report.v2")


@pytest.mark.parametrize(
    "args",
    [
        ["-o", "report.txt"],
        ["-o", "report.md", "--format", "json"],
        ["-o", "report.json", "--format", "md"],
        ["-o", "extensionless"],
    ],
)
def test_report_rejects_bad_or_conflicting_output_formats(
    monkeypatch, tmp_path: Path, args: list[str]
) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    result = runner.invoke(
        cli.app,
        ["report", str(source), *args, "--no-spokenform", "--no-titles"],
    )

    assert result.exit_code == 2


def test_report_rejects_source_path_as_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    result = runner.invoke(
        cli.app,
        ["report", str(source), "-o", str(source), "--no-spokenform", "--no-titles"],
    )

    assert result.exit_code == 2
    assert "must not match the source path" in result.output
    assert source.read_text(encoding="utf-8") == "source"


def test_invalid_chapter_selector_is_usage_error(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    prepare_source(monkeypatch, source)
    result = runner.invoke(cli.app, ["chapters", str(source)])
    assert result.exit_code == 0

    invalid = runner.invoke(cli.app, ["convert", str(source), "--chapters", "3-1"])
    assert invalid.exit_code == 2
    assert "reversed" in invalid.output


def test_runtime_processing_failure_exits_one_without_traceback(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(
        cli, "load", lambda _: (_ for _ in ()).throw(RuntimeError("source parse failed"))
    )

    result = runner.invoke(cli.app, ["chapters", str(source)])

    assert result.exit_code == 1
    assert "Error: source parse failed" in result.output
    assert "Traceback" not in result.output


def test_invalid_tts_options_are_usage_errors(tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("source", encoding="utf-8")

    bad_format = runner.invoke(cli.app, ["convert", str(source), "--format", "wav"])
    bad_layout = runner.invoke(cli.app, ["convert", str(source), "--layout", "many"])
    bad_breaks = runner.invoke(cli.app, ["convert", str(source), "--paragraph-breaks", "9"])

    assert bad_format.exit_code == 2
    assert bad_layout.exit_code == 2
    assert bad_breaks.exit_code == 2
