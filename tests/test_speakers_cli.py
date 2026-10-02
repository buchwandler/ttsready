from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner

from ttsready.cli import app
from ttsready.input import load
from ttsready.pipeline import prepare
from ttsready.sidecar import Sidecar, canonical_source_identity, load_sidecar, save_sidecar
from ttsready.speakers import extract_utterances

runner = CliRunner()


def _source_and_config(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "book.ssmd.md"
    source.write_text(
        chr(10).join(["---", 'ssmd_version: "0.9"', "---", "“Hello there.”", ""]),
        encoding="utf-8",
    )
    config = tmp_path / "book.ttsready.yaml"
    save_sidecar(
        config,
        Sidecar(
            source=canonical_source_identity(load(source)),
            lexicon=(),
            characters=({"id": "alice", "display_name": "Alice", "aliases": ["Al"]},),
            speaker_annotations=(),
        ),
    )
    return source, config


def test_speakers_cli_shows_unreviewed_source_utterances_without_provider(
    tmp_path: Path,
) -> None:
    source, config = _source_and_config(tmp_path)

    result = runner.invoke(app, ["speakers", str(source), "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "unreviewed" in result.output
    assert "Hello there." in result.output
    loaded = load_sidecar(config, document=load(source))
    assert loaded.speaker_annotations == ()


def test_speaker_set_cli_persists_an_explicit_manual_assignment(tmp_path: Path) -> None:
    source, config = _source_and_config(tmp_path)
    report = prepare(load(source), apply_spokenform=False).report
    assert report is not None
    utterance = extract_utterances(report.contexts)[0]

    result = runner.invoke(
        app,
        [
            "speaker-set",
            str(source),
            "--config",
            str(config),
            "--utterance",
            utterance.id,
            "--speaker",
            "alice",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Saved manual speaker assignment" in result.output
    loaded = load_sidecar(config, document=load(source))
    assert loaded.speaker_annotations[0]["utterance_id"] == utterance.id
    assert loaded.speaker_annotations[0]["speaker"] == "alice"
    assert loaded.speaker_annotations[0]["status"] == "manual"
    assert loaded.speaker_annotations[0]["provenance"] == {"provider": "human"}


def test_speaker_materialize_writes_logical_voice_and_is_idempotent(tmp_path: Path) -> None:
    source, config = _source_and_config(tmp_path)
    report = prepare(load(source), apply_spokenform=False).report
    assert report is not None
    utterance = extract_utterances(report.contexts)[0]
    assigned = runner.invoke(
        app,
        [
            "speaker-set",
            str(source),
            "--config",
            str(config),
            "--utterance",
            utterance.id,
            "--speaker",
            "alice",
        ],
    )
    assert assigned.exit_code == 0, assigned.output

    result = runner.invoke(
        app,
        [
            "speaker-materialize",
            str(source),
            "--config",
            str(config),
            "--utterance",
            utterance.id,
        ],
    )

    assert result.exit_code == 0, result.output
    output = tmp_path / "book.reviewed.ssmd.md"
    document = load(output)
    source_ssmd = document.sections[0].ssmd
    assert source_ssmd is not None
    voice_annotations = [
        item for item in document.sections[0].structure.annotations if item.attrs.get("voice")
    ]
    assert len(voice_annotations) == 1
    assert voice_annotations[0].attrs["voice"] == "alice"
    assert "voice-a" not in source_ssmd
    reanchored_sidecar = load_sidecar(config, document=document)
    assert reanchored_sidecar.characters[0]["id"] == "alice"
    assert reanchored_sidecar.speaker_annotations[0]["speaker"] == "alice"
    assert reanchored_sidecar.speaker_annotations[0]["provenance"] == {"provider": "human"}

    repeated = runner.invoke(
        app,
        [
            "speaker-materialize",
            str(output),
            "--config",
            str(config),
            "--utterance",
            utterance.id,
            "--write",
        ],
    )
    assert repeated.exit_code == 0, repeated.output
    reloaded = load(output)
    assert reloaded.sections[0].ssmd == source_ssmd
    assert sum("voice" in item.attrs for item in reloaded.sections[0].structure.annotations) == 1


def test_speaker_materialize_rejects_stale_utterance_id(tmp_path: Path) -> None:
    source, config = _source_and_config(tmp_path)
    original_document = load(source)
    report = prepare(original_document, apply_spokenform=False).report
    assert report is not None
    utterance = extract_utterances(report.contexts)[0]
    sidecar = load_sidecar(config, document=original_document)
    assigned = runner.invoke(
        app,
        [
            "speaker-set",
            str(source),
            "--config",
            str(config),
            "--utterance",
            utterance.id,
            "--speaker",
            "alice",
        ],
    )
    assert assigned.exit_code == 0, assigned.output
    sidecar = load_sidecar(config, document=original_document)
    source.write_text(
        chr(10).join(["---", 'ssmd_version: "0.9"', "---", "“Different words.”", ""]),
        encoding="utf-8",
    )
    changed_document = load(source)
    save_sidecar(config, replace(sidecar, source=canonical_source_identity(changed_document)))

    result = runner.invoke(
        app,
        [
            "speaker-materialize",
            str(source),
            "--config",
            str(config),
            "--utterance",
            utterance.id,
        ],
    )

    assert result.exit_code == 1
    assert "Stale speaker decision" in result.output
    assert not (tmp_path / "book.reviewed.ssmd.md").exists()


def test_speakers_cli_supports_json_review_output(tmp_path: Path) -> None:
    source, config = _source_and_config(tmp_path)

    result = runner.invoke(
        app,
        ["speakers", str(source), "--config", str(config), "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["utterances"][0]["text"] == "Hello there."
    assert payload["decisions"] == []
