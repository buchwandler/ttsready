"""Source-neutral deterministic identifiers and text digests."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from .models import JsonValue, SpeechOverride


def _json_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("identifier payload contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("identifier payload mapping keys must be strings")
            result[key] = _json_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise ValueError(f"identifier payload contains non-JSON value {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Encode JSON values with stable key order and compact separators."""
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_id(prefix: str, payload: Mapping[str, JsonValue]) -> str:
    """Return a deterministic, compact v1 identifier for a JSON payload."""
    if not isinstance(prefix, str) or not prefix or ":" in prefix:
        raise ValueError("ID prefix must be a non-empty string without ':'")
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:v1:{digest}"


def text_sha256(text: str) -> str:
    """Return a SHA-256 digest of UTF-8 text."""
    if not isinstance(text, str):
        raise TypeError("text_sha256 expects a string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_change_id(
    unit_id: str,
    *,
    source_start: int,
    source_end: int,
    source: str,
) -> str:
    """Identify a source occurrence independently of replacement or backend."""
    return stable_id(
        "chg",
        {
            "unit_id": unit_id,
            "source_start": source_start,
            "source_end": source_end,
            "source": source,
        },
    )


def override_id(override: SpeechOverride) -> str:
    """Return the deterministic identity for source-neutral override policy."""
    scope = override.scope
    return stable_id(
        "ovr",
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
        },
    )


__all__ = ["canonical_json", "override_id", "source_change_id", "stable_id", "text_sha256"]
