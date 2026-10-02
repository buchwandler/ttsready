from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ssmdconvert import Book, BookChapter, write_book_bundle
from ssmdconvert import SourceInfo as BookSourceInfo
from typer.testing import CliRunner

from ttsready.cli import app
from ttsready.input import load
from ttsready.pipeline import prepare, prepare_tts_plan
from ttsready.planning import render_preview

runner = CliRunner()


def _standalone(path: Path) -> Path:
    path.write_text(
        '---\nssmd_version: "0.9"\ntitle: "Book"\nlanguage: en-US\n---\n'
        'The [Dr.]{sub="Doctor"} spoke to [Alice]{voice="logical-alice"}.\n',
        encoding="utf-8",
    )
    return path


def _chapter(title: str, body: str) -> str:
    return chr(10).join(
        [
            "---",
            'ssmd_version: "0.9"',
            f'title: "{title}"',
            "language: en-US",
            "---",
            body,
            "",
        ]
    )


def test_plan_exposes_logical_voice_segments_and_shared_rendering(tmp_path: Path) -> None:
    source = _standalone(tmp_path / "book.ssmd.md")
    document = load(source)

    plan = prepare_tts_plan(document, apply_spokenform=False, include_titles=False)
    preview = render_preview(plan)
    result = prepare(document, apply_spokenform=False, include_titles=False)

    assert result.plan is not None
    assert result.plan.segments == tuple(result.paragraphs)
    assert preview == result.text == "The Doctor spoke to Alice.\n"
    assert plan.report.output_chars == 0
    assert plan.report.prepared_output_sha256 is None
    assert result.report is not None
    assert (
        result.report.prepared_output_sha256
        == hashlib.sha256(result.text.encode("utf-8")).hexdigest()
    )
    voice_segments = [segment for segment in plan.segments if segment.voice]
    assert [(segment.text, segment.voice) for segment in voice_segments] == [
        ("Alice", "logical-alice")
    ]
    assert all(segment.chapter_id == "document-0001" for segment in plan.segments)
    assert all(segment.source_context_id for segment in plan.segments)


def test_report_preview_and_txt_export_share_prepared_output(tmp_path: Path, monkeypatch) -> None:
    source = _standalone(tmp_path / "book.ssmd.md")
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(tmp_path / "cache"))

    report = runner.invoke(
        app,
        ["report", str(source), "--format", "json", "--no-titles", "--refresh"],
    )
    assert report.exit_code == 0, report.output
    report_data = json.loads(report.output)

    output_path = tmp_path / "prepared.txt"
    exported = runner.invoke(
        app,
        [
            "export",
            str(source),
            "--format",
            "txt",
            "--no-titles",
            "-o",
            str(output_path),
        ],
    )
    assert exported.exit_code == 0, exported.output
    exported_text = output_path.read_text(encoding="utf-8")

    preview = runner.invoke(app, ["preview", str(source), "--no-titles"])

    assert preview.exit_code == 0, preview.output
    assert preview.output == exported_text == "The Doctor spoke to Alice.\n"
    assert "logical-alice" not in exported_text
    assert (
        report_data["prepared_output_sha256"]
        == hashlib.sha256(exported_text.encode("utf-8")).hexdigest()
    )


def test_chapter_txt_export_uses_the_same_plan_and_keeps_layout_explicit(tmp_path: Path) -> None:
    source = tmp_path / "book.ssmdbook"
    book = Book(
        source=BookSourceInfo(format="epub", media_type="application/epub+zip", name="source.epub"),
        metadata={"title": "Book", "language": "en-US"},
        chapters=(
            BookChapter(
                "chapter-0001",
                1,
                "One",
                _chapter("One", 'The [Dr.]{sub="Doctor"} greeted [Alice]{voice="speaker-one"}.'),
            ),
            BookChapter(
                "chapter-0002",
                2,
                "Two",
                _chapter("Two", 'The [3]{sub="three"} guests left.'),
            ),
        ),
        source_sha256="a" * 64,
        source_chapter_count=2,
    )
    write_book_bundle(book, source, format="directory")
    output_dir = tmp_path / "chapters"

    exported = runner.invoke(
        app,
        [
            "export",
            str(source),
            "--format",
            "txt",
            "--layout",
            "chapters",
            "--no-titles",
            "-o",
            str(output_dir),
        ],
    )

    assert exported.exit_code == 0, exported.output
    first = output_dir / "001-One.txt"
    second = output_dir / "002-Two.txt"
    assert first.read_text(encoding="utf-8") == "The Doctor greeted Alice.\n"
    assert second.read_text(encoding="utf-8") == "The three guests left.\n"
    assert "speaker-one" not in first.read_text(encoding="utf-8")
