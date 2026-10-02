from __future__ import annotations

import hashlib
from pathlib import Path

import spokenform
from ssmdconvert import Book, BookChapter, write_book_bundle
from ssmdconvert import SourceInfo as BookSourceInfo
from ssmdconvert import convert as convert_ssmd

from ttsready.input import load
from ttsready.pipeline import prepare


def ssmd(title: str, body: str) -> str:
    return f'---\nssmd_version: "0.9"\ntitle: {title}\nlanguage: en-US\n---\n{body}\n'


def book() -> Book:
    return Book(
        source=BookSourceInfo(
            format="epub",
            media_type="application/epub+zip",
            name="source.epub",
        ),
        metadata={"title": "Sample book", "language": "en-US"},
        chapters=(
            BookChapter(
                id="chapter-0002",
                source_number=2,
                title="Second",
                ssmd=ssmd("Second", "Second chapter."),
                level=1,
            ),
            BookChapter(
                id="chapter-0001",
                source_number=1,
                title="First",
                ssmd=ssmd("First", 'The [Dr.]{sub="Doctor"} counted 3 items.'),
                level=1,
            ),
        ),
        source_sha256="a" * 64,
        source_chapter_count=2,
    )


def test_load_standalone_ssmd_retains_structure_and_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "sample.ssmd.md"
    source.write_text(ssmd("Sample", 'Hello [world]{ph="wɝːld"}.'), encoding="utf-8")

    document = load(source)

    assert document.source.format == "ssmd"
    assert document.metadata["title"] == "Sample"
    assert document.sections[0].text == "Hello world."
    assert document.sections[0].ssmd is not None
    assert document.sections[0].structure is not None
    assert document.sections[0].structure.annotations[0].attrs["ph"] == "wɝːld"
    assert document.source_sha256 is not None
    assert document.content_fingerprint is not None
    assert document.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert document.content_fingerprint == load(source).content_fingerprint


def test_load_normalizes_crlf_before_paragraph_processing(tmp_path: Path) -> None:
    source = tmp_path / "paragraphs.ssmd.md"
    source.write_bytes(
        ssmd("Sample", "First paragraph.\n\nSecond paragraph.")
        .replace("\n", "\r\n")
        .encode("utf-8")
    )

    document = load(source)
    result = prepare(document, apply_spokenform=False, include_titles=False)

    assert document.sections[0].text == "First paragraph.\n\nSecond paragraph."
    assert result.text == "First paragraph.\n\nSecond paragraph.\n"


def test_load_book_bundle_uses_manifest_chapter_order_and_hashes(tmp_path: Path) -> None:
    source = tmp_path / "sample.ssmdbook"
    write_book_bundle(book(), source, format="directory")

    document = load(source)

    assert document.source.format == "ssmdbook"
    assert [section.id for section in document.sections] == ["chapter-0002", "chapter-0001"]
    assert [section.source_index for section in document.sections] == [2, 1]
    assert all(section.chapter_sha256 for section in document.sections)
    assert [section.chapter_sha256 for section in document.sections] == [
        hashlib.sha256(chapter.ssmd.encode("utf-8")).hexdigest() for chapter in book().chapters
    ]
    assert document.source_sha256 == "a" * 64
    assert document.content_fingerprint is not None


def test_bundle_zip_loads_and_native_sub_is_applied_without_spokenform(tmp_path: Path) -> None:
    source = tmp_path / "sample.ssmdbook.zip"
    write_book_bundle(book(), source, format="zip")

    document = load(source)
    result = prepare(document, apply_spokenform=False, include_titles=False)

    assert "Doctor" in result.text
    assert "Dr." not in result.text
    assert result.report is not None
    substitution = next(change for change in result.report.changes if change.source == "Dr.")
    assert result.report.input_format == "ssmdbook"
    assert result.report.content_fingerprint == document.content_fingerprint
    assert result.report.normalization_profile["language"] == "en-US"
    assert substitution.replacement == "Doctor"
    assert substitution.stages == ("ssmd.sub",)
    assert substitution.provenance == {"origin": "ssmd.sub", "status": "authoritative"}


def test_say_as_and_phoneme_spans_are_protected_from_spokenform(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "protected.ssmd.md"
    source.write_text(
        ssmd("Protected", 'The [3]{as="cardinal"} [4]{ph="fɔːr"} items.'),
        encoding="utf-8",
    )
    protected_spans = []
    original_prepare = spokenform.prepare

    def recording_prepare(text: str, **kwargs):
        protected_spans.extend(kwargs["protected_spans"])
        return original_prepare(text, **kwargs)

    monkeypatch.setattr(spokenform, "prepare", recording_prepare)
    result = prepare(load(source), include_titles=False)

    assert result.text.strip() == "The 3 4 items."
    assert protected_spans == [(4, 5), (6, 7)]


def test_standalone_ssmd_requires_versioned_valid_input(tmp_path: Path) -> None:
    source = tmp_path / "invalid.ssmd"
    source.write_text("Unversioned text.", encoding="utf-8")

    try:
        load(source)
    except Exception as error:
        assert "ssmd_version" in str(error)
    else:  # pragma: no cover
        raise AssertionError("expected invalid SSMD to be rejected")


def test_raw_format_is_not_an_authoritative_ttsready_input(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.write_bytes(b"not an epub")

    try:
        load(source)
    except Exception as error:
        assert "accepts standalone" in str(error)
    else:  # pragma: no cover
        raise AssertionError("expected raw EPUB input to be rejected")


def test_ssmdconvert_output_is_ttsready_canonical_input(tmp_path: Path) -> None:
    source = tmp_path / "chapter.md"
    source.write_text("The starship arrived.\n", encoding="utf-8")

    conversion = convert_ssmd(source, title="Chapter", language="en-US")
    canonical_path = tmp_path / "chapter.ssmd.md"
    canonical_path.write_text(conversion.ssmd, encoding="utf-8", newline="")

    document = load(canonical_path)
    result = prepare(document, apply_spokenform=False, include_titles=False)

    assert document.sections[0].ssmd == conversion.ssmd
    assert result.text.strip() == "The starship arrived."
    assert result.report is not None
    assert result.report.input_format == "ssmd"
    assert result.report.source_sha256 == hashlib.sha256(canonical_path.read_bytes()).hexdigest()
