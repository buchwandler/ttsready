"""Pure canonical fingerprints for source-neutral preparation inputs and outputs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Any

from .identifiers import canonical_json, text_sha256
from .models import PreparationProfile, PreparedUnit, SpeechOverride, TextUnit


def _fingerprint(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def runtime_versions() -> dict[str, str]:
    """Return only ttsready's semantic runtime versions."""
    try:
        from ._version import version as ttsready_version
    except (ImportError, AttributeError):  # pragma: no cover - source-tree fallback
        ttsready_version = "0.2.0"
    versions = {"ttsready": str(ttsready_version)}
    for package in ("spokenform", "phrasplit"):
        try:
            versions[package] = distribution_version(package)
        except PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def profile_fingerprint(profile: PreparationProfile | Mapping[str, Any]) -> str:
    """Fingerprint transformation policy independently from unit language."""
    if is_dataclass(profile):
        payload = {item.name: getattr(profile, item.name) for item in fields(profile)}
    elif isinstance(profile, Mapping):
        payload = dict(profile)
    else:
        raise TypeError("profile must be a PreparationProfile or mapping")
    return _fingerprint(payload)


def override_fingerprint(overrides: Iterable[SpeechOverride]) -> str:
    """Fingerprint ordered override policy, including scope and match behavior."""
    payload = []
    for override in overrides:
        scope = override.scope
        payload.append(
            {
                "surface": override.surface,
                "spoken": override.spoken,
                "match": override.match,
                "case_sensitive": override.case_sensitive,
                "scope": {
                    "kind": scope.kind,
                    "unit_id": scope.unit_id,
                    "source_start": scope.source_start,
                    "source_end": scope.source_end,
                },
            }
        )
    return _fingerprint(payload)


def runtime_fingerprint(versions: Mapping[str, str] | None = None) -> str:
    """Hash ttsready, spokenform, and phrasplit versions only."""
    selected = (
        runtime_versions()
        if versions is None
        else {
            name: str(versions.get(name, "unknown"))
            for name in ("ttsready", "spokenform", "phrasplit")
        }
    )
    return _fingerprint(selected)


def unit_fingerprint(
    unit: TextUnit,
    *,
    profile_fingerprint: str,
    override_fingerprint: str,
    runtime_fingerprint: str,
) -> str:
    """Fingerprint one caller unit and the policies/runtime used to process it."""
    return _fingerprint(
        {
            "id": unit.id,
            "text_sha256": text_sha256(unit.text),
            "language": unit.language,
            "role": unit.role,
            "protected_spans": [
                {"start": span.start, "end": span.end, "reason": span.reason}
                for span in unit.protected_spans
            ],
            "profile_fingerprint": profile_fingerprint,
            "override_fingerprint": override_fingerprint,
            "runtime_fingerprint": runtime_fingerprint,
        }
    )


def prepared_fingerprint(units: Iterable[PreparedUnit]) -> str:
    """Digest ordered caller unit IDs and their prepared spoken text."""
    return _fingerprint(
        [{"unit_id": unit.unit_id, "spoken_text": unit.spoken_text} for unit in units]
    )


__all__ = [
    "override_fingerprint",
    "prepared_fingerprint",
    "profile_fingerprint",
    "runtime_fingerprint",
    "runtime_versions",
    "unit_fingerprint",
]
