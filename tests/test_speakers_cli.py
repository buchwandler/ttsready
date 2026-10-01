from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ttsready.cli import app
from ttsready.identifiers import file_sha256
from ttsready.pipeline import prepare
from ttsready.readers import load
from ttsready.sidecar import Sidecar, load_sidecar, save_sidecar
from ttsready.speakers import extract_utterances

runner = CliRunner()


def _source_and_config(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "book.txt"
    source.write_text("“Hello there.”", encoding="utf-8")
    config = tmp_path / "book.ttsready.yaml"
    save_sidecar(
        config,
        Sidecar(
            source={"format": "text", "file_sha256": file_sha256(source)},
            lexicon=(),
            characters=(
                {"id": "alice", "display_name": "Alice", "aliases": ["Al"]},
            ),
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
    loaded = load_sidecar(config, source_path=source, source_format="text")
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
    loaded = load_sidecar(config, source_path=source, source_format="text")
    assert loaded.speaker_annotations[0]["utterance_id"] == utterance.id
    assert loaded.speaker_annotations[0]["speaker"] == "alice"
    assert loaded.speaker_annotations[0]["status"] == "manual"


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
