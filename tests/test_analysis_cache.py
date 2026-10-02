from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import spokenform
from ssmdconvert import Book, BookChapter, load_book_bundle, write_book_bundle
from ssmdconvert import SourceInfo as BookSourceInfo
from typer.testing import CliRunner

import ttsready.input as input_loader
from ttsready.cli import app

runner = CliRunner()


def _ssmd(title: str, body: str) -> str:
    return chr(10).join(
        ["---", 'ssmd_version: "0.9"', f"title: {title}", "language: en-US", "---", body, ""]
    )


def _report(source: Path, *, format: str = "json"):
    result = runner.invoke(
        app,
        ["report", str(source), "--format", format, "--no-titles"],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_stale_context_does_not_recompute_spokenform(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.ssmd.md"
    source.write_text(_ssmd("Book", "He met Dr. Smith."), encoding="utf-8")
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(tmp_path / "cache"))
    report = _report(source)
    change_id = next(item["id"] for item in report["changes"] if item["source"] == "Dr.")
    source.write_text(_ssmd("Book", "He met Prof. Smith."), encoding="utf-8")

    def fail_prepare(*args, **kwargs):
        raise AssertionError("stale context must not rerun Spokenform")

    monkeypatch.setattr(spokenform, "prepare", fail_prepare)
    result = runner.invoke(app, ["context", str(source), change_id])

    assert result.exit_code == 1
    assert "Analysis cache is stale for document-0001" in result.output
    assert "ttsready report" in result.output and "--refresh" in result.output


def test_report_reuses_unaffected_chapter_analysis(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.ssmdbook"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(cache))
    book = Book(
        source=BookSourceInfo(format="epub", media_type="application/epub+zip", name="book.epub"),
        metadata={"title": "Book", "language": "en-US"},
        chapters=(
            BookChapter(
                id="chapter-0001",
                source_number=1,
                title="One",
                ssmd=_ssmd("One", "The first chapter has 3."),
            ),
            BookChapter(
                id="chapter-0002",
                source_number=2,
                title="Two",
                ssmd=_ssmd("Two", "The second chapter has 4."),
            ),
        ),
        source_sha256="a" * 64,
        source_chapter_count=2,
    )
    write_book_bundle(book, source, format="directory")
    original_prepare = spokenform.prepare
    calls = []

    def count_prepare(text: str, **kwargs):
        calls.append(text)
        return original_prepare(text, **kwargs)

    monkeypatch.setattr(spokenform, "prepare", count_prepare)
    first_report = _report(source)
    assert len(calls) == 2
    assert first_report["analysis_id"].startswith("ana:v1:")

    loaded = load_book_bundle(source)
    updated = replace(
        loaded,
        chapters=(
            loaded.chapters[0],
            replace(loaded.chapters[1], ssmd=_ssmd("Two", "The changed chapter has 5.")),
        ),
    )
    write_book_bundle(updated, source, format="directory", overwrite=True)
    calls.clear()

    second_report = _report(source)

    assert len(calls) == 1
    assert first_report["analysis_id"] != second_report["analysis_id"]
    assert len(list((cache / "chapters").glob("*.json"))) == 3
    snapshots = list(cache.glob("*/*.json"))
    assert any(
        json.loads(path.read_text(encoding="utf-8"))["schema"] == "ttsready.analysis.v1"
        for path in snapshots
    )
    change = next(item for item in second_report["changes"] if item["source"] == "3")

    def fail_load(*args, **kwargs):
        raise AssertionError("context must not reload the SSMD book")

    def fail_prepare(*args, **kwargs):
        raise AssertionError("context must not rerun Spokenform")

    monkeypatch.setattr(input_loader, "load_book_bundle", fail_load)
    monkeypatch.setattr(spokenform, "prepare", fail_prepare)
    context = runner.invoke(app, ["context", str(source), change["id"], "--json"])

    assert context.exit_code == 0, context.output
    assert json.loads(context.output)["spoken_sentence_text"] == "The first chapter has three."
