from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import ssmd
from ssmdconvert import Book, BookChapter, SourceInfo, load_book_bundle, write_book_bundle
from typer.testing import CliRunner

from ttsready.cli import app
from ttsready.input import load
from ttsready.materialization import MaterializationError, materialize_substitution
from ttsready.pipeline import prepare
from ttsready.reporting import render_report

runner = CliRunner()


def _ssmd(text: str, *, title: str = "Book") -> str:
    return chr(10).join(["---", 'ssmd_version: "0.9"', f'title: "{title}"', "---", text, ""])


def _standalone(tmp_path: Path, text: str) -> Path:
    source = tmp_path / "book.ssmd.md"
    source.write_text(_ssmd(text), encoding="utf-8")
    return source


def _cached_change(source: Path, *, occurrence: int = 0) -> dict:
    result = runner.invoke(
        app,
        ["report", str(source), "--format", "json", "--no-titles", "--refresh"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    changes = [item for item in payload["changes"] if item["source"] == "Dr."]
    return changes[occurrence]


def test_materialization_maps_exact_occurrence_and_is_idempotent(tmp_path: Path) -> None:
    source = _ssmd("He met Dr. Smith. Later, Dr. returned.")
    section = load(_standalone(tmp_path, "He met Dr. Smith. Later, Dr. returned.")).sections[0]
    start = section.text.rindex("Dr.")

    updated = materialize_substitution(
        source,
        expected_clean_text=section.text,
        start=start,
        end=start + len("Dr."),
        surface="Dr.",
        spoken="Doctor",
    )
    repeated = materialize_substitution(
        updated,
        expected_clean_text=section.text,
        start=start,
        end=start + len("Dr."),
        surface="Dr.",
        spoken="Doctor",
    )
    structure = ssmd.parse_structure(updated, dialect="0.9", normalize=False)
    substitutions = [
        item
        for item in structure.annotations
        if (
            item.char_start == start
            and item.char_end == start + 3
            and item.attrs.get("sub") == "Doctor"
        )
    ]

    assert updated == repeated
    assert structure.clean_text == section.text
    assert len(substitutions) == 1
    assert updated.count('[Dr.]{sub="Doctor"}') == 1
    assert updated.count("Dr.") == 2


def test_materialization_rejects_stale_spans_and_updates_existing_sub() -> None:
    source = _ssmd('He met [Dr.]{sub="Doctor"} Smith.')
    clean_text = ssmd.parse_structure(source, dialect="0.9", normalize=False).clean_text
    start = clean_text.index("Dr.")

    assert (
        materialize_substitution(
            source,
            expected_clean_text=clean_text,
            start=start,
            end=start + 3,
            surface="Dr.",
            spoken="Doctor",
        )
        == source
    )
    updated = materialize_substitution(
        source,
        expected_clean_text=clean_text,
        start=start,
        end=start + 3,
        surface="Dr.",
        spoken="Doc",
    )

    assert 'sub="Doc"' in updated
    assert ssmd.parse_structure(updated, dialect="0.9", normalize=False).clean_text == clean_text
    with pytest.raises(MaterializationError, match="no longer contains"):
        materialize_substitution(
            source,
            expected_clean_text=clean_text,
            start=start + 1,
            end=start + 4,
            surface="Dr.",
            spoken="Doctor",
        )


def test_override_cli_materializes_report_change_and_suppresses_overlap(
    tmp_path: Path, monkeypatch
) -> None:
    source = _standalone(tmp_path, "He met Dr. Smith. Later, Dr. returned.")
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(tmp_path / "cache"))
    change = _cached_change(source, occurrence=1)

    result = runner.invoke(app, ["override", str(source), change["id"], "--spoken", "Doctor"])

    assert result.exit_code == 0, result.output
    output = tmp_path / "book.reviewed.ssmd.md"
    assert output.exists()
    document = load(output)
    report = prepare(document).report
    assert report is not None
    selected = [
        item
        for item in report.changes
        if item.source == "Dr." and item.source_start == change["source_start"]
    ]
    assert len(selected) == 1
    assert selected[0].stages == ("ssmd.sub",)
    assert selected[0].provenance == {"origin": "ssmd.sub", "status": "authoritative"}
    assert '"origin": "ssmd.sub"' in render_report(report, "md")
    assert document.sections[0].ssmd is not None
    assert document.sections[0].ssmd.count('[Dr.]{sub="Doctor"}') == 1


def test_override_cli_rejects_a_stale_cached_span(tmp_path: Path, monkeypatch) -> None:
    source = _standalone(tmp_path, "He met Dr. Smith.")
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(tmp_path / "cache"))
    change = _cached_change(source)
    source.write_text(_ssmd("He met Prof. Smith."), encoding="utf-8")

    result = runner.invoke(app, ["override", str(source), change["id"], "--spoken", "Doctor"])

    assert result.exit_code == 1
    assert "chapter has changed" in result.output or "stale" in result.output.casefold()
    assert not (tmp_path / "book.reviewed.ssmd.md").exists()


def test_override_cli_rewrites_book_atomically_and_preserves_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.ssmdbook"
    first = BookChapter(
        id="chapter-0001",
        source_number=1,
        title="First",
        ssmd=_ssmd("He met Dr. Smith.", title="First"),
        source_id="source-chapter-one",
        href="text/one.xhtml",
        level=1,
    )
    second = BookChapter(
        id="chapter-0002",
        source_number=2,
        title="Second",
        ssmd=_ssmd("A plain second chapter.", title="Second"),
        source_id="source-chapter-two",
        href="text/two.xhtml",
        level=1,
    )
    original = Book(
        source=SourceInfo(format="epub", media_type="application/epub+zip", name="source.epub"),
        metadata={"title": "Preserved book", "language": "en"},
        chapters=(first, second),
        source_sha256="a" * 64,
        source_chapter_count=2,
    )
    write_book_bundle(original, source, format="directory")
    original_book = load_book_bundle(source)
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(tmp_path / "cache"))
    change = _cached_change(source)

    result = runner.invoke(
        app,
        ["override", str(source), change["id"], "--spoken", "Doctor", "--write"],
    )

    assert result.exit_code == 0, result.output
    updated = load_book_bundle(source)
    assert updated.source == original_book.source
    assert updated.metadata == original_book.metadata
    assert updated.source_sha256 == original_book.source_sha256
    assert len(updated.chapters) == 2
    assert updated.chapters[0].ssmd != original_book.chapters[0].ssmd
    assert updated.chapters[1].ssmd == original_book.chapters[1].ssmd
    assert (
        hashlib.sha256(updated.chapters[0].ssmd.encode()).hexdigest()
        != hashlib.sha256(original_book.chapters[0].ssmd.encode()).hexdigest()
    )
    assert (
        hashlib.sha256(updated.chapters[1].ssmd.encode()).hexdigest()
        == hashlib.sha256(original_book.chapters[1].ssmd.encode()).hexdigest()
    )
    assert updated.chapters[0].source_id == original_book.chapters[0].source_id
    assert updated.chapters[0].href == original_book.chapters[0].href

    report = prepare(load(source)).report
    assert report is not None
    authoritative = [item for item in report.changes if item.stages == ("ssmd.sub",)]
    assert len(authoritative) == 1
