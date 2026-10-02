"""Deterministic profile fingerprints and strict ttsready lock files."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import ConversionReport, Document
from .sidecar import Sidecar

LOCK_SCHEMA = "ttsready.lock.v1"
_LOCK_FIELDS = {
    "schema",
    "ssmd_content_fingerprint",
    "chapters",
    "runtime",
    "runtime_fingerprint",
    "normalization_profile",
    "prepared_output_sha256",
}


class ReproducibilityError(ValueError):
    """Raised for malformed or incompatible reproducibility locks."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _fingerprint(value: Any) -> str:
    return _sha256(_canonical_json(value).encode("utf-8"))


def normalization_fingerprints(
    language: str,
    options: dict[str, Any],
    sidecar: Sidecar | None,
) -> dict[str, str]:
    """Fingerprint Spokenform options and pronunciation overrides independently."""
    pronunciation_profile = (
        [
            {
                "surface": item.surface,
                "spoken": item.spoken,
                "match": item.match,
                "case_sensitive": item.case_sensitive,
                "kind": item.kind,
                "scope": item.scope,
            }
            for item in sidecar.lexicon
        ]
        if sidecar
        else []
    )
    options_sha256 = _fingerprint(options)
    pronunciation_sha256 = _fingerprint(pronunciation_profile)
    profile_sha256 = _fingerprint(
        {
            "language": language,
            "options_sha256": options_sha256,
            "pronunciation_profile_sha256": pronunciation_sha256,
        }
    )
    return {
        "options_sha256": options_sha256,
        "pronunciation_profile_sha256": pronunciation_sha256,
        "profile_sha256": profile_sha256,
    }


def runtime_fingerprint(tool_versions: dict[str, str]) -> str:
    return _fingerprint(tool_versions)


def create_lock_record(
    document: Document,
    report: ConversionReport,
    prepared_output: str,
    *,
    sidecar: Sidecar | None = None,
) -> dict[str, Any]:
    if document.content_fingerprint is None:
        raise ReproducibilityError("Canonical SSMD input has no content fingerprint")
    profile_hashes = normalization_fingerprints(
        report.effective_language,
        report.normalization_profile,
        sidecar,
    )
    return {
        "schema": LOCK_SCHEMA,
        "ssmd_content_fingerprint": document.content_fingerprint,
        "chapters": {
            section.id: {"sha256": section.chapter_sha256} for section in document.sections
        },
        "runtime": dict(report.tool_versions),
        "runtime_fingerprint": runtime_fingerprint(report.tool_versions),
        "normalization_profile": {
            "language": report.effective_language,
            **profile_hashes,
        },
        "prepared_output_sha256": _sha256(prepared_output.encode("utf-8")),
    }


def write_lock(path: str | Path, lock: dict[str, Any]) -> Path:
    _validate_lock(lock)
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(lock, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _validate_lock(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReproducibilityError("Lock root must be a JSON object")
    if value.get("schema") != LOCK_SCHEMA:
        raise ReproducibilityError(f"Unsupported lock schema: {value.get('schema')!r}")
    fields = set(value)
    if fields != _LOCK_FIELDS:
        missing = sorted(_LOCK_FIELDS - fields)
        unknown = sorted(fields - _LOCK_FIELDS)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown fields: {', '.join(unknown)}")
        raise ReproducibilityError("Invalid lock fields (" + "; ".join(details) + ")")
    for field in ("ssmd_content_fingerprint", "runtime_fingerprint", "prepared_output_sha256"):
        if not _is_sha256(value[field]):
            raise ReproducibilityError(f"Lock field {field} must be a SHA-256 digest")
    for field in ("chapters", "runtime", "normalization_profile"):
        if not isinstance(value[field], dict):
            raise ReproducibilityError(f"Lock field {field} must be a JSON object")
    if any(
        not isinstance(chapter_id, str)
        or not isinstance(chapter, dict)
        or set(chapter) != {"sha256"}
        or not _is_sha256(chapter["sha256"])
        for chapter_id, chapter in value["chapters"].items()
    ):
        raise ReproducibilityError("Lock chapters must map IDs to {sha256: digest} objects")
    if any(
        not isinstance(name, str) or not isinstance(version, str)
        for name, version in value["runtime"].items()
    ):
        raise ReproducibilityError("Lock runtime must map package names to version strings")
    profile = value["normalization_profile"]
    profile_fields = {
        "language",
        "options_sha256",
        "pronunciation_profile_sha256",
        "profile_sha256",
    }
    if set(profile) != profile_fields:
        raise ReproducibilityError("Lock normalization_profile has invalid fields")
    if not isinstance(profile["language"], str) or not profile["language"]:
        raise ReproducibilityError("Lock normalization_profile.language must be a non-empty string")
    for field in ("options_sha256", "pronunciation_profile_sha256", "profile_sha256"):
        if not _is_sha256(profile[field]):
            raise ReproducibilityError(
                f"Lock normalization_profile.{field} must be a SHA-256 digest"
            )
    expected_runtime = runtime_fingerprint(value["runtime"])
    if value["runtime_fingerprint"] != expected_runtime:
        raise ReproducibilityError("Lock runtime_fingerprint does not match its runtime versions")
    expected_profile = _fingerprint(
        {
            "language": profile["language"],
            "options_sha256": profile["options_sha256"],
            "pronunciation_profile_sha256": profile["pronunciation_profile_sha256"],
        }
    )
    if profile["profile_sha256"] != expected_profile:
        raise ReproducibilityError("Lock normalization profile fingerprint is inconsistent")
    return value


def read_lock(path: str | Path) -> dict[str, Any]:
    lock_path = Path(path).expanduser()
    try:
        value = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReproducibilityError(f"Could not read ttsready lock {lock_path}: {exc}") from exc
    return _validate_lock(value)


def _differences(path: str, recorded: Any, current: Any) -> list[str]:
    if isinstance(recorded, dict) and isinstance(current, dict):
        differences = []
        for key in sorted(set(recorded) | set(current)):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in recorded:
                differences.append(f"{child_path}: missing from lock")
            elif key not in current:
                differences.append(f"{child_path}: no longer present")
            else:
                differences.extend(_differences(child_path, recorded[key], current[key]))
        return differences
    if recorded != current:
        return [f"{path}: locked {recorded!r}, current {current!r}"]
    return []


def verify_lock(path: str | Path, current: dict[str, Any]) -> None:
    recorded = read_lock(path)
    _validate_lock(current)
    differences = _differences("", recorded, current)
    if differences:
        details = "\n".join(f"- {difference}" for difference in differences)
        raise ReproducibilityError(f"Lock verification failed:\n{details}")
