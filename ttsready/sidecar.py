"""Load and validate human-edited ttsready sidecar files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .identifiers import file_sha256, stable_id

SCHEMA = "ttsready.sidecar.v1"


class SidecarError(ValueError):
    """Raised when a sidecar is invalid or does not match its source."""


@dataclass(frozen=True, slots=True)
class SpeechOverride:
    id: str
    surface: str
    spoken: str
    match: str
    case_sensitive: bool
    kind: str
    scope: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Sidecar:
    source: dict[str, Any]
    lexicon: tuple[SpeechOverride, ...]
    characters: tuple[dict[str, Any], ...]
    speaker_annotations: tuple[dict[str, Any], ...]


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SidecarError(f"Sidecar {field} must be a mapping")
    return value


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SidecarError(f"Sidecar {field} must be a non-empty string")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SidecarError(f"Sidecar {field} must be a list")
    return value


def _parse_override(value: Any, index: int) -> SpeechOverride:
    field = f"lexicon[{index}]"
    item = _mapping(value, field)
    surface = _string(item.get("surface"), f"{field}.surface")
    spoken = _string(item.get("spoken"), f"{field}.spoken", allow_empty=True)
    match = item.get("match", "literal")
    if not isinstance(match, str) or match not in {"literal", "word"}:
        raise SidecarError(f"{field}.match must be 'literal' or 'word'")
    case_sensitive = item.get("case_sensitive", True)
    if not isinstance(case_sensitive, bool):
        raise SidecarError(f"{field}.case_sensitive must be a boolean")
    kind = item.get("kind", "pronunciation")
    if not isinstance(kind, str) or kind not in {"pronunciation", "normalization_override"}:
        raise SidecarError(
            f"{field}.kind must be 'pronunciation' or 'normalization_override'"
        )
    scope = _mapping(item.get("scope", {"type": "document"}), f"{field}.scope")
    scope_type = scope.get("type", "document")
    if not isinstance(scope_type, str) or scope_type not in {"document", "section", "occurrence"}:
        raise SidecarError(f"{field}.scope.type must be document, section, or occurrence")
    if scope_type == "section":
        section_id = scope.get("section_id")
        section_locator = scope.get("section_locator")
        if section_id is not None:
            _string(section_id, f"{field}.scope.section_id")
        if section_locator is not None:
            _string(section_locator, f"{field}.scope.section_locator")
        if section_id is None and section_locator is None:
            raise SidecarError(f"{field}.scope requires section_id or section_locator")
    if scope_type == "occurrence":
        _string(scope.get("context_id"), f"{field}.scope.context_id")
        start, end = scope.get("source_start"), scope.get("source_end")
        if (start is None) != (end is None):
            raise SidecarError(f"{field}.scope source_start and source_end must be given together")
        if start is not None and (
            type(start) is not int or type(end) is not int or start < 0 or end <= start
        ):
            raise SidecarError(f"{field}.scope source span must be a valid positive range")
    provenance = _mapping(item.get("provenance", {}), f"{field}.provenance")
    override_id = item.get("id")
    if override_id is None:
        override_id = stable_id(
            "ovr",
            {
                "surface": surface,
                "spoken": spoken,
                "match": match,
                "case_sensitive": case_sensitive,
                "kind": kind,
                "scope": scope,
                "provenance": provenance,
            },
        )
    else:
        override_id = _string(override_id, f"{field}.id")
    return SpeechOverride(
        id=override_id,
        surface=surface,
        spoken=spoken,
        match=match,
        case_sensitive=case_sensitive,
        kind=kind,
        scope=dict(scope),
        provenance=dict(provenance),
    )


def _parse_characters(value: Any) -> tuple[dict[str, Any], ...]:
    characters = []
    seen_ids = set()
    for index, entry in enumerate(_list(value, "characters")):
        field = f"characters[{index}]"
        item = _mapping(entry, field)
        character_id = _string(item.get("id"), f"{field}.id")
        if any(key in item for key in ("voice", "tts_voice", "provider_voice")):
            raise SidecarError(f"{field} may contain logical speaker data, not TTS voice bindings")
        if character_id in seen_ids:
            raise SidecarError(f"Duplicate logical character ID {character_id!r}")
        seen_ids.add(character_id)
        display_name = _string(item.get("display_name"), f"{field}.display_name")
        aliases = _list(item.get("aliases", []), f"{field}.aliases")
        if any(not isinstance(alias, str) for alias in aliases):
            raise SidecarError(f"{field}.aliases must contain only strings")
        characters.append(
            {**item, "id": character_id, "display_name": display_name, "aliases": aliases}
        )
    return tuple(characters)


def _parse_speaker_annotations(value: Any) -> tuple[dict[str, Any], ...]:
    annotations = []
    seen_utterances = set()
    for index, entry in enumerate(_list(value, "speaker_annotations")):
        field = f"speaker_annotations[{index}]"
        item = _mapping(entry, field)
        utterance_id = _string(item.get("utterance_id"), f"{field}.utterance_id")
        if any(key in item for key in ("voice", "tts_voice", "provider_voice")):
            raise SidecarError(f"{field} may store logical speaker IDs, not TTS voice bindings")
        if utterance_id in seen_utterances:
            raise SidecarError(f"Duplicate speaker annotation for {utterance_id!r}")
        seen_utterances.add(utterance_id)
        speaker = _string(item.get("speaker"), f"{field}.speaker")
        status = item.get("status", "accepted")
        if not isinstance(status, str) or status not in {"accepted", "manual"}:
            raise SidecarError(f"{field}.status must be accepted or manual")
        provenance = _mapping(item.get("provenance", {}), f"{field}.provenance")
        annotation_id = item.get("id") or stable_id(
            "spk",
            {"utterance_id": utterance_id, "speaker": speaker, "status": status},
        )
        annotations.append(
            {
                **item,
                "id": _string(annotation_id, f"{field}.id"),
                "utterance_id": utterance_id,
                "speaker": speaker,
                "status": status,
                "provenance": dict(provenance),
            }
        )
    return tuple(annotations)



def _validate_speaker_references(
    characters: tuple[dict[str, Any], ...],
    annotations: tuple[dict[str, Any], ...],
) -> None:
    character_ids = {character["id"] for character in characters}
    for annotation in annotations:
        if annotation["speaker"] not in character_ids:
            raise SidecarError(
                f"Speaker annotation references unknown logical character ID "
                f"{annotation['speaker']!r}"
            )


def load_sidecar(
    path: str | Path,
    *,
    source_path: str | Path,
    source_format: str,
) -> Sidecar:
    sidecar_path = Path(path)
    try:
        data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SidecarError(f"Could not read ttsready sidecar {sidecar_path}: {exc}") from exc
    data = _mapping(data, "root")
    if data.get("schema") != SCHEMA:
        raise SidecarError(f"Unsupported sidecar schema: {data.get('schema')!r}")
    unknown = set(data) - {"schema", "source", "lexicon", "characters", "speaker_annotations"}
    if unknown:
        raise SidecarError(f"Unknown sidecar fields: {', '.join(sorted(unknown))}")

    source = _mapping(data.get("source", {}), "source")
    expected_format = source.get("format")
    if expected_format is not None and expected_format != source_format:
        raise SidecarError(
            f"Sidecar source format {expected_format!r} does not match {source_format!r}"
        )
    expected_hash = source.get("file_sha256")
    if expected_hash is not None:
        expected_hash = _string(expected_hash, "source.file_sha256")
        actual_hash = file_sha256(Path(source_path))
        if actual_hash is None:
            raise SidecarError(f"Could not verify sidecar fingerprint for {source_path}")
        if actual_hash.casefold() != expected_hash.casefold():
            raise SidecarError("Sidecar source SHA-256 does not match the input file")

    lexicon_values = _list(data.get("lexicon"), "lexicon")
    lexicon = tuple(_parse_override(item, index) for index, item in enumerate(lexicon_values))
    characters = _parse_characters(data.get("characters"))
    speaker_annotations = _parse_speaker_annotations(data.get("speaker_annotations"))
    _validate_speaker_references(characters, speaker_annotations)
    return Sidecar(
        source=dict(source),
        lexicon=lexicon,
        characters=characters,
        speaker_annotations=speaker_annotations,
    )


def save_sidecar(path: str | Path, sidecar: Sidecar) -> None:
    characters = _parse_characters(list(sidecar.characters))
    speaker_annotations = _parse_speaker_annotations(list(sidecar.speaker_annotations))
    _validate_speaker_references(characters, speaker_annotations)
    data = {
        "schema": SCHEMA,
        "source": sidecar.source,
        "lexicon": [
            {
                "id": item.id,
                "surface": item.surface,
                "spoken": item.spoken,
                "match": item.match,
                "case_sensitive": item.case_sensitive,
                "kind": item.kind,
                "scope": item.scope,
                "provenance": item.provenance,
            }
            for item in sidecar.lexicon
        ],
        "characters": list(characters),
        "speaker_annotations": list(speaker_annotations),
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
