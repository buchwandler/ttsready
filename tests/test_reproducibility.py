from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import spokenform
from ssmdconvert import Book, BookChapter, load_book_bundle, write_book_bundle
from ssmdconvert import SourceInfo as BookSourceInfo
from typer.testing import CliRunner

import ttsready.pipeline as pipeline
from ttsready.cli import app
from ttsready.input import load
from ttsready.pipeline import prepare
from ttsready.reproducibility import normalization_fingerprints
from ttsready.sidecar import (
    Sidecar,
    SpeechOverride,
    canonical_source_identity,
    save_sidecar,
)

runner = CliRunner()


def _source(tmp_path: Path, body: str = "He met Dr. Smith and found 3 items.") -> Path:
    source = tmp_path / "book.ssmd.md"
    source.write_text(
        f'---\nssmd_version: "0.9"\ntitle: "Book"\nlanguage: en-US\n---\n{body}\n',
        encoding="utf-8",
    )
    return source


def _create_lock(source: Path, lock_path: Path, *options: str):
    return runner.invoke(app, ["lock", str(source), "-o", str(lock_path), *options])


def _sidecar(source: Path, spoken: str = "Doctor") -> Sidecar:
    return Sidecar(
        source=canonical_source_identity(load(source)),
        lexicon=(
            SpeechOverride(
                id="reviewed-dr",
                surface="Dr.",
                spoken=spoken,
                match="literal",
                case_sensitive=True,
                kind="pronunciation",
                scope={"type": "document"},
                provenance={"reviewer": "human"},
            ),
        ),
        characters=(),
        speaker_annotations=(),
    )


def test_lock_creation_is_deterministic_and_verification_is_strict(tmp_path: Path) -> None:
    source = _source(tmp_path)
    first = tmp_path / "first.lock.json"
    second = tmp_path / "second.lock.json"

    created = _create_lock(source, first)
    repeated = _create_lock(source, second)

    assert created.exit_code == 0, created.output
    assert repeated.exit_code == 0, repeated.output
    first_record = json.loads(first.read_text(encoding="utf-8"))
    assert first_record == json.loads(second.read_text(encoding="utf-8"))
    assert first_record["schema"] == "ttsready.lock.v1"
    assert next(iter(first_record["chapters"].values())).keys() == {"sha256"}
    assert first_record["normalization_profile"]["language"] == "en-US"
    assert len(first_record["normalization_profile"]["pronunciation_profile_sha256"]) == 64

    profile_options = asdict(pipeline.normalization_profile("en-US"))
    assert profile_options["sequence_fallback_mode"] == "preserve"
    lock_profile = first_record["normalization_profile"]
    assert (
        lock_profile["options_sha256"]
        == normalization_fingerprints("en-US", profile_options, None)["options_sha256"]
    )
    spell_options = {**profile_options, "sequence_fallback_mode": "spell"}
    assert (
        lock_profile["options_sha256"]
        != normalization_fingerprints("en-US", spell_options, None)["options_sha256"]
    )
    verified = runner.invoke(app, ["verify", str(source), "--lock", str(first)])
    assert verified.exit_code == 0, verified.output

    language_drift = runner.invoke(
        app,
        ["verify", str(source), "--lock", str(first), "--language", "en-GB"],
    )
    assert language_drift.exit_code == 1
    assert "normalization_profile.language" in language_drift.output


def test_lock_verification_reports_runtime_version_drift(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path)
    lock_path = tmp_path / "book.lock.json"
    created = _create_lock(source, lock_path)
    assert created.exit_code == 0, created.output

    changed_versions = dict(pipeline._tool_versions())
    changed_versions["spokenform"] = "999.0"
    monkeypatch.setattr(pipeline, "_tool_versions", lambda: changed_versions)

    verified = runner.invoke(app, ["verify", str(source), "--lock", str(lock_path)])

    assert verified.exit_code == 1
    assert "runtime.spokenform" in verified.output
    assert "runtime_fingerprint" in verified.output


def test_lock_verification_detects_pronunciation_profile_drift(tmp_path: Path) -> None:
    source = _source(tmp_path)
    sidecar_path = tmp_path / "book.ttsready.yaml"
    lock_path = tmp_path / "book.lock.json"
    save_sidecar(sidecar_path, _sidecar(source, "Doctor"))

    created = _create_lock(source, lock_path, "--config", str(sidecar_path))
    assert created.exit_code == 0, created.output
    save_sidecar(sidecar_path, _sidecar(source, "Physician"))

    verified = runner.invoke(
        app,
        ["verify", str(source), "--lock", str(lock_path), "--config", str(sidecar_path)],
    )

    assert verified.exit_code == 1
    assert "normalization_profile.pronunciation_profile_sha256" in verified.output


def test_lock_verification_detects_canonical_content_drift(tmp_path: Path) -> None:
    source = _source(tmp_path)
    lock_path = tmp_path / "book.lock.json"
    created = _create_lock(source, lock_path)
    assert created.exit_code == 0, created.output

    updated_source = source.read_text(encoding="utf-8").replace("3 items", "4 items")
    source.write_text(updated_source, encoding="utf-8")
    verified = runner.invoke(app, ["verify", str(source), "--lock", str(lock_path)])

    assert verified.exit_code == 1
    assert "ssmd_content_fingerprint" in verified.output


def test_lock_and_freeze_support_ssmdbook_artifacts(tmp_path: Path) -> None:

    source = tmp_path / "book.ssmdbook"
    chapter_ssmd = chr(10).join(
        [
            "---",
            'ssmd_version: "0.9"',
            'title: "Chapter"',
            "language: en-US",
            "---",
            "Dr. found 3 items.",
            "",
        ]
    )
    book = Book(
        source=BookSourceInfo(format="epub", media_type="application/epub+zip", name="source.epub"),
        metadata={"title": "Book", "language": "en-US"},
        chapters=(BookChapter("chapter-0001", 1, "Chapter", chapter_ssmd),),
        source_sha256="a" * 64,
        source_chapter_count=1,
    )
    write_book_bundle(book, source, format="directory")
    lock_path = tmp_path / "book.lock.json"

    created = _create_lock(source, lock_path)
    assert created.exit_code == 0, created.output
    verified = runner.invoke(app, ["verify", str(source), "--lock", str(lock_path)])
    assert verified.exit_code == 0, verified.output

    frozen_path = tmp_path / "book.frozen.ssmdbook"
    frozen = runner.invoke(app, ["freeze", str(source), "-o", str(frozen_path)])

    assert frozen.exit_code == 0, frozen.output
    frozen_book = load_book_bundle(frozen_path)
    assert '[Dr.]{sub="Doctor"}' in frozen_book.chapters[0].ssmd
    assert '[3]{sub="three"}' in frozen_book.chapters[0].ssmd


def test_freeze_materializes_transformations_and_is_engine_independent(
    tmp_path: Path, monkeypatch
) -> None:
    source = _source(tmp_path)
    source_before = source.read_bytes()
    expected = prepare(load(source)).text
    frozen_path = tmp_path / "book.frozen.ssmd.md"

    frozen = runner.invoke(app, ["freeze", str(source), "-o", str(frozen_path)])

    assert frozen.exit_code == 0, frozen.output
    assert source.read_bytes() == source_before
    frozen_ssmd = frozen_path.read_text(encoding="utf-8")
    assert '[Dr.]{sub="Doctor"}' in frozen_ssmd
    assert '[3]{sub="three"}' in frozen_ssmd

    def unchanged_spokenform(text: str, **_kwargs):
        return SimpleNamespace(spoken_text=text, stages=(), source_replacements=(), warnings=())

    monkeypatch.setattr(spokenform, "prepare", unchanged_spokenform)
    prepared_frozen = prepare(load(frozen_path))

    assert prepared_frozen.text == expected
    assert prepared_frozen.report is not None
    assert {change.replacement for change in prepared_frozen.report.changes} >= {
        "Doctor",
        "three",
    }
    assert all(
        change.stages == ("ssmd.sub",)
        for change in prepared_frozen.report.changes
        if change.source in {"Dr.", "3"}
    )
