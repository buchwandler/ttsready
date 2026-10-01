"""Stable source-anchored identifiers for review records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import Section


def stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    """Return a deterministic, versioned ID for a JSON-compatible payload."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:20]
    return f"{prefix}:v1:{digest}"


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str | None:
    try:
        with open(path, "rb") as source:
            digest = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def section_locator(section: Section) -> str:
    if section.source_ref:
        return f"ref:{section.source_ref}"
    return f"id:{section.id}"


def context_id(
    section: Section,
    *,
    kind: str,
    source_text: str,
    duplicate_ordinal: int,
) -> str:
    return stable_id(
        "ctx",
        {
            "section": section_locator(section),
            "kind": kind,
            "text_sha256": text_sha256(source_text),
            "duplicate_ordinal": duplicate_ordinal,
        },
    )


def change_id(
    context_id: str,
    *,
    source_start: int,
    source_end: int,
    source: str,
) -> str:
    return stable_id(
        "chg",
        {
            "context_id": context_id,
            "source_start": source_start,
            "source_end": source_end,
            "source": source,
        },
    )



def utterance_id(
    context_id: str,
    *,
    source_start: int,
    source_end: int,
    source: str,
) -> str:
    """Return a stable ID for one source utterance span."""
    return stable_id(
        "utt",
        {
            "context_id": context_id,
            "source_start": source_start,
            "source_end": source_end,
            "source": source,
        },
    )


def speaker_decision_id(
    utterance_id_value: str,
    *,
    speaker_id: str | None,
    provider: str,
    provider_model: str | None,
) -> str:
    """Return a stable speaker decision ID independent of output voice names or status."""
    return stable_id(
        "spk",
        {
            "utterance_id": utterance_id_value,
            "speaker_id": speaker_id,
            "provider": provider,
            "provider_model": provider_model,
        },
    )
