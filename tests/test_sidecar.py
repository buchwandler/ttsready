from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ttsready.cli import app
from ttsready.identifiers import file_sha256
from ttsready.overrides import OverrideConflictError, find_overrides
from ttsready.pipeline import prepare
from ttsready.readers import load
from ttsready.sidecar import (
    SCHEMA,
    SidecarError,
    SpeechOverride,
    load_sidecar,
    save_sidecar,
)

runner = CliRunner()


def _sidecar_data(source: Path, *, lexicon: list[dict] | None = None) -> dict:
    return {
        "schema": SCHEMA,
        "source": {"format": "text", "file_sha256": file_sha256(source)},
        "lexicon": lexicon or [],
    }


def _write_sidecar(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _override(
    override_id: str,
    surface: str,
    spoken: str,
    *,
    scope: dict | None = None,
) -> SpeechOverride:
    return SpeechOverride(
        id=override_id,
        surface=surface,
        spoken=spoken,
        match="literal",
        case_sensitive=True,
        kind="pronunciation",
        scope=scope or {"type": "document"},
        provenance={},
    )


def test_load_sidecar_validates_source_and_generates_stable_ids(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("H2O", encoding="utf-8")
    path = tmp_path / "book.ttsready.yaml"
    data = _sidecar_data(
        source,
        lexicon=[{"surface": "H2O", "spoken": "water", "provenance": {"note": "reviewed"}}],
    )
    _write_sidecar(path, data)

    sidecar = load_sidecar(path, source_path=source, source_format="text")
    reloaded = load_sidecar(path, source_path=source, source_format="text")

    assert sidecar.lexicon[0].id.startswith("ovr:v1:")
    assert sidecar.lexicon[0].id == reloaded.lexicon[0].id
    assert sidecar.lexicon[0].provenance == {"note": "reviewed"}
    saved = tmp_path / "saved.yaml"
    save_sidecar(saved, sidecar)
    assert load_sidecar(saved, source_path=source, source_format="text") == sidecar


def test_load_sidecar_rejects_schema_format_and_stale_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("original", encoding="utf-8")
    path = tmp_path / "sidecar.yaml"
    data = _sidecar_data(source)

    data["schema"] = "ttsready.sidecar.v2"
    _write_sidecar(path, data)
    with pytest.raises(SidecarError, match="Unsupported sidecar schema"):
        load_sidecar(path, source_path=source, source_format="text")

    data = _sidecar_data(source)
    data["source"]["format"] = "epub"
    _write_sidecar(path, data)
    with pytest.raises(SidecarError, match="source format"):
        load_sidecar(path, source_path=source, source_format="text")

    data = _sidecar_data(source)
    _write_sidecar(path, data)
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(SidecarError, match="SHA-256"):
        load_sidecar(path, source_path=source, source_format="text")


def test_load_sidecar_rejects_invalid_override_scope(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("Hello", encoding="utf-8")
    path = tmp_path / "sidecar.yaml"
    data = _sidecar_data(
        source,
        lexicon=[{"surface": "Hello", "spoken": "Hi", "scope": {"type": "section"}}],
    )
    _write_sidecar(path, data)

    with pytest.raises(SidecarError, match="requires section_id or section_locator"):
        load_sidecar(path, source_path=source, source_format="text")

def test_sidecar_preserves_logical_characters_and_reviewed_speakers(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("Hello", encoding="utf-8")
    path = tmp_path / "sidecar.yaml"
    data = _sidecar_data(source)
    data["characters"] = [{"id": "alice", "display_name": "Alice", "aliases": ["Al"]}]
    data["speaker_annotations"] = [
        {
            "utterance_id": "utt:v1:example",
            "speaker": "alice",
            "status": "manual",
            "provenance": {"provider": "human"},
        }
    ]
    _write_sidecar(path, data)

    sidecar = load_sidecar(path, source_path=source, source_format="text")

    assert sidecar.characters[0]["aliases"] == ["Al"]
    assert sidecar.speaker_annotations[0]["status"] == "manual"
    assert sidecar.speaker_annotations[0]["provenance"] == {"provider": "human"}
    data["speaker_annotations"][0]["speaker"] = "ghost"
    _write_sidecar(path, data)
    with pytest.raises(SidecarError, match="unknown logical character"):
        load_sidecar(path, source_path=source, source_format="text")
    data["speaker_annotations"][0]["speaker"] = "alice"
    data["speaker_annotations"][0]["status"] = "suggested"
    _write_sidecar(path, data)
    with pytest.raises(SidecarError, match="status must be accepted or manual"):
        load_sidecar(path, source_path=source, source_format="text")


def test_override_precedence_longer_match_and_conflict_detection() -> None:
    document = _override("document", "New", "old")
    section = _override(
        "section", "New", "section", scope={"type": "section", "section_id": "s1"}
    )
    occurrence = _override(
        "occurrence",
        "New",
        "local",
        scope={"type": "occurrence", "context_id": "ctx"},
    )
    longer = _override("longer", "New York", "NY")
    matches = find_overrides(
        "New York",
        (document, section, occurrence, longer),
        context_id="ctx",
        section_id="s1",
        section_locator="epub:item-1",
    )

    assert [(match.start, match.end, match.override.id) for match in matches] == [
        (0, 3, "occurrence")
    ]
    section_matches = find_overrides(
        "New",
        (document, section),
        context_id="ctx",
        section_id="s1",
        section_locator="epub:item-1",
    )
    assert [match.override.id for match in section_matches] == ["section"]
    longer_matches = find_overrides(
        "New York",
        (document, longer),
        context_id="",
        section_id="",
        section_locator="",
    )
    assert [match.override.id for match in longer_matches] == ["longer"]
    exact = _override(
        "exact",
        "New",
        "one occurrence",
        scope={"type": "occurrence", "context_id": "ctx", "source_start": 4, "source_end": 7},
    )
    exact_matches = find_overrides(
        "New New",
        (exact,),
        context_id="ctx",
        section_id="",
        section_locator="",
    )
    assert [(match.start, match.end) for match in exact_matches] == [(4, 7)]

    conflicting = _override("conflicting", "New", "different")
    with pytest.raises(OverrideConflictError, match="Conflicting sidecar overrides"):
        find_overrides(
            "New",
            (document, conflicting),
            context_id="ctx",
            section_id="s1",
            section_locator="",
        )


def test_custom_override_protects_structured_text_and_composes_offsets(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("H2O and 3.", encoding="utf-8")
    sidecar_path = tmp_path / "sidecar.yaml"
    _write_sidecar(
        sidecar_path,
        _sidecar_data(source, lexicon=[{"surface": "H2O", "spoken": "water"}]),
    )
    sidecar = load_sidecar(sidecar_path, source_path=source, source_format="text")

    result = prepare(load(source), sidecar=sidecar)

    assert result.paragraphs[0].text == "water and three."
    unchanged = prepare(load(source), apply_spokenform=False, sidecar=sidecar)
    assert unchanged.paragraphs[0].text == "water and 3."
    custom = next(change for change in result.report.changes if "custom" in change.stages)
    number = next(change for change in result.report.changes if change.source == "3")
    assert (custom.source_start, custom.source_end) == (0, 3)
    assert (custom.output_start, custom.output_end) == (0, 5)
    assert number.output_start == 10
    assert result.report.spokenform.stage_edits["custom"] == 1


def test_all_preparation_commands_accept_and_apply_config(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("H2O and 3.", encoding="utf-8")
    config = tmp_path / "sidecar.yaml"
    lexicon = [
        {
            "surface": "H2O",
            "spoken": "water",
            "provenance": {"finding_id": "lex:v1:reviewed"},
        }
    ]
    _write_sidecar(config, _sidecar_data(source, lexicon=lexicon))

    output = tmp_path / "output.txt"
    converted = runner.invoke(
        app,
        ["convert", str(source), "--config", str(config), "-o", str(output)],
    )
    assert converted.exit_code == 0, converted.output
    assert output.read_text(encoding="utf-8").strip() == "water and three."

    preflight = runner.invoke(app, ["preflight", str(source), "--config", str(config)])
    assert preflight.exit_code == 0, preflight.output
    assert "custom overrides: 1" in preflight.output

    reported = runner.invoke(
        app,
        ["report", str(source), "--config", str(config), "--format", "json"],
    )
    assert reported.exit_code == 0, reported.output
    payload = json.loads(reported.output)
    custom = next(change for change in payload["changes"] if "custom" in change["stages"])
    assert custom["provenance"]["finding_id"] == "lex:v1:reviewed"

    context = runner.invoke(
        app,
        ["context", str(source), custom["id"], "--config", str(config)],
    )
    assert context.exit_code == 0, context.output
    assert "H2O" in context.output
    assert "-> water" in context.output
    assert "lex:v1:reviewed" in context.output
