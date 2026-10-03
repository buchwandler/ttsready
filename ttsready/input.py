"""Load canonical SSMD documents and validated SSMD book bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import ssmd as ssmd_library
from ssmdconvert import Book, BookChapter, load_book_bundle, load_book_workspace

from .errors import TTSReadyError, UnsupportedInputError
from .models import (
    Document,
    Section,
    SourceInfo,
    resolve_sequence_fallback_mode,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve_artifact_sequence_fallback_mode(metadata: dict, *, label: str) -> str:
    try:
        return resolve_sequence_fallback_mode(metadata["sequence_fallback_mode"])
    except KeyError:
        return resolve_sequence_fallback_mode()
    except TTSReadyError as exc:
        raise TTSReadyError(f"{label}: {exc}") from exc


def _parse_ssmd(source: str, *, label: str):
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    issues = ssmd_library.lint(source, profile="ssmd-core", dialect="0.9")
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        messages = "; ".join(issue.message for issue in errors[:5])
        raise TTSReadyError(f"{label} is not valid SSMD 0.9: {messages}")
    structure = ssmd_library.parse_structure(
        source,
        dialect="0.9",
        normalize=False,
        resolve_defaults=True,
    )
    if structure.header.get("ssmd_version") != "0.9":
        raise TTSReadyError(f"{label} must declare ssmd_version: '0.9'")
    return structure


def _content_fingerprint(kind: str, chapters: list[tuple[str, str]]) -> str:
    payload = {
        "schema": "ttsready.ssmd-content.v1",
        "kind": kind,
        "chapters": [{"id": chapter_id, "sha256": digest} for chapter_id, digest in chapters],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(canonical.encode("utf-8"))


def _section_from_ssmd(
    chapter_id: str,
    source: str,
    *,
    title: str | None,
    level: int = 1,
    source_ref: str | None = None,
    source_index: int | None = None,
    chapter_sha256: str | None = None,
) -> Section:
    structure = _parse_ssmd(source, label=f"SSMD section {chapter_id!r}")
    digest = chapter_sha256 or _sha256(source.encode("utf-8"))
    return Section(
        id=chapter_id,
        text=structure.clean_text,
        title=title or structure.header.get("title"),
        source_ref=source_ref,
        level=level,
        source_index=source_index,
        ssmd=source,
        structure=structure,
        chapter_sha256=digest,
    )


def load_ssmd(
    source: str,
    *,
    source_path: Path | None = None,
    section_id: str = "document-0001",
    source_sha256: str | None = None,
) -> Document:
    """Load canonical SSMD text without passing it through a source converter."""
    label = str(source_path) if source_path is not None else "<memory>"
    structure = _parse_ssmd(source, label=label)
    digest = source_sha256 or _sha256(source.encode("utf-8"))
    title = structure.header.get("title")
    document_title = title or (
        source_path.name.removesuffix(".ssmd.md").removesuffix(".ssmd")
        if source_path is not None
        else "SSMD document"
    )
    section = Section(
        id=section_id,
        text=structure.clean_text,
        title=str(title) if title is not None else None,
        source_index=1,
        ssmd=source,
        structure=structure,
        chapter_sha256=digest,
    )
    return Document(
        source=SourceInfo(source_path or Path("<memory>"), "ssmd", "text/markdown"),
        sections=[section],
        metadata={
            **structure.header,
            "title": document_title,
            "sequence_fallback_mode": _resolve_artifact_sequence_fallback_mode(
                structure.header,
                label=f"SSMD document {label}",
            ),
            "_sequence_fallback_mode_stored": "sequence_fallback_mode" in structure.header,
        },
        source_sha256=digest,
        content_fingerprint=_content_fingerprint("ssmd", [(section.id, digest)]),
    )


def _load_standalone(path: Path) -> Document:
    try:
        raw = path.read_bytes()
        source = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise TTSReadyError(f"Could not read SSMD {path}: {exc}") from exc
    return load_ssmd(source, source_path=path, source_sha256=_sha256(raw))


def _resolve_book_sequence_fallback_mode(metadata: dict, sections: list[Section]) -> str:
    key = "sequence_fallback_mode"
    manifest_has_mode = key in metadata
    manifest_mode = _resolve_artifact_sequence_fallback_mode(
        metadata,
        label="SSMD book manifest",
    )
    chapter_modes = []
    for section in sections:
        if section.structure is None or key not in section.structure.header:
            continue
        chapter_mode = _resolve_artifact_sequence_fallback_mode(
            section.structure.header,
            label=f"SSMD book chapter {section.id!r}",
        )
        chapter_modes.append((section.id, chapter_mode))

    if manifest_has_mode:
        for chapter_id, chapter_mode in chapter_modes:
            if chapter_mode != manifest_mode:
                raise TTSReadyError(
                    f"SSMD book chapter {chapter_id!r} sequence_fallback_mode "
                    f"{chapter_mode!r} conflicts with manifest value {manifest_mode!r}"
                )
        return manifest_mode

    if not chapter_modes:
        return resolve_sequence_fallback_mode()
    first_chapter_id, first_mode = chapter_modes[0]
    for chapter_id, chapter_mode in chapter_modes[1:]:
        if chapter_mode != first_mode:
            raise TTSReadyError(
                "Conflicting sequence_fallback_mode values in SSMD book chapters "
                f"{first_chapter_id!r} and {chapter_id!r}"
            )
    return first_mode


def _load_book(path: Path, *, workspace: bool = False) -> Document:
    try:
        loaded_workspace = load_book_workspace(path) if workspace else None
        book: Book = (
            loaded_workspace.book
            if loaded_workspace is not None
            else load_book_bundle(path)
        )
    except Exception as exc:
        raise TTSReadyError(f"Could not load SSMD book {path}: {exc}") from exc

    sections: list[Section] = []
    chapter_hashes: list[tuple[str, str]] = []
    for chapter in book.chapters:
        section = _section_from_ssmd(
            chapter.id,
            chapter.ssmd,
            title=chapter.title,
            level=chapter.level,
            source_ref=chapter.href,
            source_index=chapter.source_number,
        )
        sections.append(section)
        chapter_hashes.append((chapter.id, section.chapter_sha256 or ""))

    metadata = dict(book.metadata)
    book_sequence_mode = _resolve_book_sequence_fallback_mode(book.metadata, sections)
    metadata["sequence_fallback_mode"] = book_sequence_mode
    metadata["_sequence_fallback_mode_stored"] = "sequence_fallback_mode" in book.metadata or any(
        section.structure is not None and "sequence_fallback_mode" in section.structure.header
        for section in sections
    )
    if loaded_workspace is not None:
        dirty_chapters = [item.id for item in loaded_workspace.chapters if item.dirty]
        metadata["workspace"] = {
            "type": "directory",
            "status": "dirty" if loaded_workspace.dirty else "clean",
            "dirty": loaded_workspace.dirty,
            "dirty_chapters": dirty_chapters,
        }
    return Document(
        source=SourceInfo(path, "ssmdbook", "application/vnd.ssmd.book"),
        sections=sections,
        metadata=metadata,
        original_section_count=book.source_chapter_count or len(book.chapters),
        source_sha256=book.source_sha256,
        content_fingerprint=_content_fingerprint("ssmdbook", chapter_hashes),
    )


def load(source: str | Path) -> Document:
    """Load one standalone SSMD document or an ssmdconvert book bundle."""
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    if path.is_dir() and path.name.casefold().endswith(".ssmdbook"):
        return _load_book(path, workspace=True)
    if path.is_file() and path.name.casefold().endswith(".ssmdbook.zip"):
        return _load_book(path, workspace=False)
    if path.is_file() and (
        path.name.casefold().endswith(".ssmd.md") or path.suffix.casefold() == ".ssmd"
    ):
        return _load_standalone(path)

    raise UnsupportedInputError(
        "Convert the source with ssmdconvert first; ttsready accepts "
        "standalone .ssmd/.ssmd.md files and .ssmdbook/.ssmdbook.zip bundles"
    )


def section_from_book_chapter(chapter: BookChapter) -> Section:
    """Build an analysis section from a validated ssmdconvert chapter."""
    return _section_from_ssmd(
        chapter.id,
        chapter.ssmd,
        title=chapter.title,
        level=chapter.level,
        source_ref=chapter.href,
        source_index=chapter.source_number,
    )
