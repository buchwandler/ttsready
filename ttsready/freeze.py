"""Freeze automatic speech decisions into a distinct reviewed SSMD artifact."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ssmdconvert import BookBundleError, load_book_bundle, load_book_workspace, write_book_bundle

from .errors import TTSReadyError
from .input import load
from .materialization import (
    MaterializationError,
    _find_change_context,
    _output_bundle_format,
    _write_standalone_atomic,
    materialize_substitution,
)
from .pipeline import prepare
from .sidecar import Sidecar


class FreezeError(ValueError):
    """Raised when speech decisions cannot be frozen safely."""


def _selected_freeze_changes(changes):
    ordered = sorted(
        (change for change in changes if "ssmd.sub" not in change.stages),
        key=lambda change: (
            change.context_id,
            change.source_start,
            change.source_end,
            0 if "custom" in change.stages else 1,
        ),
    )
    selected = []
    for change in ordered:
        overlapping = [
            item
            for item in selected
            if item.context_id == change.context_id
            and item.source_start < change.source_end
            and change.source_start < item.source_end
        ]
        if not overlapping:
            selected.append(change)
        elif "custom" in change.stages and all("custom" not in item.stages for item in overlapping):
            selected = [item for item in selected if item not in overlapping]
            selected.append(change)
    return selected


def freeze_ssmd(
    source_path: str | Path,
    output_path: str | Path,
    *,
    sidecar: Sidecar | None = None,
    language: str | None = None,
) -> Path:
    """Write all current automatic and explicit sidecar speech changes as SSMD sub tags."""
    source = Path(source_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if target == source:
        raise FreezeError("Freeze output must not overwrite the source SSMD input")
    document = load(source)
    result = prepare(document, language=language, sidecar=sidecar)
    if result.report is None:
        raise FreezeError("Freeze preparation did not produce a report")

    updated_by_section: dict[str, str] = {}
    sections = {section.id: section for section in document.sections}
    for change in _selected_freeze_changes(result.report.changes):
        try:
            section, start, end = _find_change_context(document, result.report, change)
            if section.ssmd is None:
                raise FreezeError(f"SSMD section {section.id!r} has no source markup")
            current_ssmd = updated_by_section.get(section.id, section.ssmd)
            updated_by_section[section.id] = materialize_substitution(
                current_ssmd,
                expected_clean_text=section.text,
                start=start,
                end=end,
                surface=change.source,
                spoken=change.replacement,
            )
        except MaterializationError as exc:
            raise FreezeError(f"Could not freeze change {change.id}: {exc}") from exc
        except TTSReadyError as exc:
            raise FreezeError(f"Could not freeze change {change.id}: {exc}") from exc

    if source.name.casefold().endswith((".ssmdbook", ".ssmdbook.zip")):
        try:
            book = load_book_workspace(source).book if source.is_dir() else load_book_bundle(source)
            chapters = tuple(
                replace(chapter, ssmd=updated_by_section[chapter.id])
                if chapter.id in updated_by_section
                else chapter
                for chapter in book.chapters
            )
            for chapter in book.chapters:
                section = sections.get(chapter.id)
                if section is None or chapter.ssmd != section.ssmd:
                    raise FreezeError("The SSMD book changed while freeze was being prepared")
            return write_book_bundle(
                replace(book, chapters=chapters),
                target,
                format=_output_bundle_format(target),
                overwrite=False,
            )
        except BookBundleError as exc:
            raise FreezeError(str(exc)) from exc

    section = document.sections[0]
    if not target.name.casefold().endswith((".ssmd.md", ".ssmd")):
        raise FreezeError("Standalone SSMD output must end in .ssmd or .ssmd.md")
    raw = source.read_bytes()
    if raw.decode("utf-8-sig") != section.ssmd:
        raise FreezeError("The SSMD source changed while freeze was being prepared")
    bom = bytes.fromhex("efbbbf") if raw.startswith(bytes.fromhex("efbbbf")) else b""
    output = updated_by_section.get(section.id, section.ssmd)
    _write_standalone_atomic(target, bom + output.encode("utf-8"), overwrite=False)
    return target
