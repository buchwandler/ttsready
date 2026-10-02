"""Persist reusable SSMD analysis and resolve context from cached reports."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import asdict, fields, replace
from pathlib import Path, PurePosixPath
from typing import Any

from .identifiers import stable_id, text_sha256
from .input import _content_fingerprint
from .models import (
    ContextRecord,
    ConversionReport,
    Document,
    PreparedParagraph,
    SectionStats,
    SentenceContext,
    SpokenChange,
    SpokenformStats,
)
from .sidecar import Sidecar

ANALYSIS_SCHEMA = "ttsready.analysis.v1"
_CHAPTER_SCHEMA = "ttsready.chapter-analysis.v1"
_INDEX_SCHEMA = "ttsready.analysis-index.v1"


class AnalysisCacheError(RuntimeError):
    """Raised when a cached analysis is missing or no longer matches its source."""


def _cache_root() -> Path:
    override = os.environ.get("TTSREADY_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif os.sys.platform == "darwin":
        base = Path.home() / "Library/Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ttsready"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(prefix: str, value: Any) -> str:
    return stable_id(prefix, {"value": value})


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _report_from_dict(value: dict[str, Any]) -> ConversionReport:
    data = dict(value)
    data["sections"] = [SectionStats(**item) for item in data.get("sections", [])]
    data["spokenform"] = SpokenformStats(**data.get("spokenform", {}))
    contexts = []
    for item in data.get("contexts", []):
        context = dict(item)
        context["source_sentences"] = tuple(
            SentenceContext(**sentence) for sentence in context.get("source_sentences", [])
        )
        context["spoken_sentences"] = tuple(
            SentenceContext(**sentence) for sentence in context.get("spoken_sentences", [])
        )
        contexts.append(ContextRecord(**context))
    data["contexts"] = contexts
    changes = []
    for item in data.get("changes", []):
        change = dict(item)
        change["stages"] = tuple(change.get("stages", ()))
        changes.append(SpokenChange(**change))
    data["changes"] = changes
    return ConversionReport(**data)


def _section_digest(section: Any) -> str:
    return section.chapter_sha256 or text_sha256(section.ssmd or section.text)


def _sidecar_lexicon(sidecar: Sidecar | None) -> list[dict[str, Any]]:
    if sidecar is None:
        return []
    return [asdict(item) for item in sidecar.lexicon]


def _section_options(
    document: Document,
    section: Any,
    *,
    section_index: int,
    language: str | None,
    effective_language: str,
    max_paragraph_chars: int | None,
    apply_spokenform: bool,
    include_titles: bool,
    profile: dict[str, Any],
    runtime: dict[str, str],
    sidecar: Sidecar | None,
) -> tuple[str, str, str]:
    profile_fingerprint = _fingerprint("profile", profile)
    runtime_fingerprint = _fingerprint("runtime", runtime)
    options = {
        "input_format": document.source.format,
        "requested_language": language,
        "effective_language": effective_language,
        "max_paragraph_chars": max_paragraph_chars,
        "apply_spokenform": apply_spokenform,
        "include_titles": include_titles,
        "lexicon": _sidecar_lexicon(sidecar),
    }
    options_fingerprint = _fingerprint("options", options)
    key = {
        "chapter_id": section.id,
        "chapter_sha256": _section_digest(section),
        "title": section.title,
        "source_ref": section.source_ref,
        "source_index": section.source_index or section_index,
        "level": section.level,
        "profile_fingerprint": profile_fingerprint,
        "options_fingerprint": options_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
    }
    cache_key = hashlib.sha256(_canonical_json(key)).hexdigest()
    return cache_key, profile_fingerprint, options_fingerprint


def _chapter_path(cache_key: str) -> Path:
    return _cache_root() / "chapters" / f"{cache_key}.json"


def _load_chapter(cache_key: str) -> tuple[ConversionReport, list[PreparedParagraph]] | None:
    path = _chapter_path(cache_key)
    value = _read_json(path)
    if value is None or value.get("schema") != _CHAPTER_SCHEMA:
        return None
    if value.get("cache_key") != cache_key or not isinstance(value.get("report"), dict):
        return None
    try:
        report = _report_from_dict(value["report"])
        paragraphs = [PreparedParagraph(**item) for item in value.get("paragraphs", [])]
    except (KeyError, TypeError, ValueError):
        return None
    return report, paragraphs


def _save_chapter(
    cache_key: str,
    report: ConversionReport,
    paragraphs: list[PreparedParagraph],
) -> None:
    _write_json(
        _chapter_path(cache_key),
        {
            "schema": _CHAPTER_SCHEMA,
            "cache_key": cache_key,
            "report": asdict(report),
            "paragraphs": [asdict(item) for item in paragraphs],
        },
    )


def _refresh_cached_report(
    report: ConversionReport,
    document: Document,
    section: Any,
    *,
    requested_language: str | None,
    effective_language: str,
    profile: dict[str, Any],
    runtime: dict[str, str],
) -> ConversionReport:
    report.source_path = str(document.source.path)
    report.input_format = document.source.format
    report.document_title = (
        str(document.metadata["title"]) if document.metadata.get("title") is not None else None
    )
    metadata_language = document.metadata.get("language")
    report.metadata_language = str(metadata_language) if metadata_language is not None else None
    report.requested_language = requested_language
    report.effective_language = effective_language
    report.total_sections = document.original_section_count or len(document.sections)
    report.selected_sections = 1
    report.source_sha256 = document.source_sha256 or report.source_sha256
    report.content_fingerprint = document.content_fingerprint
    report.normalization_profile = profile
    report.tool_versions = runtime
    if report.sections:
        report.sections[0].section_id = section.id
        report.sections[0].index = section.source_index or 1
        report.sections[0].title = section.title
        report.sections[0].level = section.level
        report.sections[0].chapter_sha256 = _section_digest(section)
    return report


def _merge_reports(
    reports: list[ConversionReport],
    paragraph_groups: list[list[PreparedParagraph]],
    document: Document,
) -> ConversionReport:
    from .models import RenderOptions
    from .writers import render_txt

    paragraphs = [paragraph for group in paragraph_groups for paragraph in group]
    if reports:
        merged = _report_from_dict(asdict(reports[0]))
        merged.sections = [item for report in reports for item in report.sections]
        merged.contexts = [item for report in reports for item in report.contexts]
        merged.changes = [item for report in reports for item in report.changes]
        merged.warnings = [item for report in reports for item in report.warnings]
        merged.spokenform = SpokenformStats()
        for report in reports:
            for field in fields(SpokenformStats):
                value = getattr(report.spokenform, field.name)
                target = getattr(merged.spokenform, field.name)
                if isinstance(value, dict):
                    for key, count in value.items():
                        target[key] = target.get(key, 0) + count
                else:
                    setattr(merged.spokenform, field.name, target + value)
        for name in (
            "input_chars",
            "source_paragraphs",
            "source_prepared_items",
            "split_source_items",
            "prepared_paragraphs",
            "added_split_parts",
        ):
            setattr(merged, name, sum(getattr(report, name) for report in reports))
        merged.max_prepared_paragraph_chars = max(
            (report.max_prepared_paragraph_chars for report in reports), default=0
        )
    else:
        from .pipeline import prepare

        result = prepare(document, render_options=RenderOptions())
        if result.report is None:
            raise ValueError("Conversion did not produce a report")
        merged = result.report
        paragraphs = result.paragraphs

    rendered = render_txt(paragraphs, options=RenderOptions())
    merged.total_sections = document.original_section_count or len(document.sections)
    merged.selected_sections = len(document.sections)
    merged.input_chars = sum(len(section.text) for section in document.sections)
    merged.source_paragraphs = sum(item.source_paragraphs for item in merged.sections)
    merged.output_chars = len(rendered)
    merged.output_lines = len(rendered.splitlines())
    merged.prepared_output_sha256 = text_sha256(rendered)
    merged.output_files = 0
    merged.destinations = []
    return merged


def _analysis_id(
    document: Document,
    report: ConversionReport,
    selected_chapters: list[dict[str, str]],
    profile_fingerprint: str,
    options_fingerprint: str,
    runtime_fingerprint: str,
) -> str:
    content_fingerprint = document.content_fingerprint or _content_fingerprint(
        document.source.format,
        [(item["id"], item["sha256"]) for item in selected_chapters],
    )
    return stable_id(
        "ana",
        {
            "kind": document.source.format,
            "content_fingerprint": content_fingerprint,
            "selected_chapters": selected_chapters,
            "profile_fingerprint": profile_fingerprint,
            "options_fingerprint": options_fingerprint,
            "runtime_fingerprint": runtime_fingerprint,
        },
    )


def _source_key(source: Path) -> str:
    return hashlib.sha256(str(source.expanduser().resolve()).encode("utf-8")).hexdigest()


def _save_snapshot(
    document: Document,
    report: ConversionReport,
    selected_chapters: list[dict[str, str]],
    profile_fingerprint: str,
    options_fingerprint: str,
    runtime_fingerprint: str,
) -> None:
    content_fingerprint = document.content_fingerprint or _content_fingerprint(
        document.source.format,
        [(item["id"], item["sha256"]) for item in selected_chapters],
    )
    analysis_id = _analysis_id(
        document,
        report,
        selected_chapters,
        profile_fingerprint,
        options_fingerprint,
        runtime_fingerprint,
    )
    report.analysis_id = analysis_id
    snapshot_path = _cache_root() / content_fingerprint / f"{analysis_id.rsplit(':', 1)[-1]}.json"
    snapshot = {
        "schema": ANALYSIS_SCHEMA,
        "analysis_id": analysis_id,
        "source": {
            "path": str(document.source.path),
            "kind": document.source.format,
            "book_source_sha256": document.source_sha256 or report.source_sha256,
            "content_fingerprint": content_fingerprint,
            "selected_chapters": selected_chapters,
        },
        "runtime": report.tool_versions,
        "normalization": {
            "language": report.effective_language,
            "profile_fingerprint": profile_fingerprint,
            "options_fingerprint": options_fingerprint,
        },
        "contexts": [asdict(item) for item in report.contexts],
        "changes": [asdict(item) for item in report.changes],
        "warnings": report.warnings,
        "report": asdict(report),
    }
    _write_json(snapshot_path, snapshot)

    source_index_path = _cache_root() / "sources" / f"{_source_key(document.source.path)}.json"
    index = _read_json(source_index_path) or {
        "schema": _INDEX_SCHEMA,
        "source_path": str(document.source.path.expanduser().resolve()),
        "snapshots": [],
    }
    entries = [
        item
        for item in index.get("snapshots", [])
        if isinstance(item, dict) and item.get("analysis_id") != analysis_id
    ]
    entries.insert(
        0,
        {
            "analysis_id": analysis_id,
            "path": str(snapshot_path.relative_to(_cache_root())),
        },
    )
    index.update(schema=_INDEX_SCHEMA, snapshots=entries)
    _write_json(source_index_path, index)


def prepare_cached_report(
    document: Document,
    *,
    language: str | None,
    max_paragraph_chars: int,
    apply_spokenform: bool,
    include_titles: bool,
    sidecar: Sidecar | None,
    force_refresh: bool = False,
) -> ConversionReport:
    """Analyze or reuse per-chapter results, then persist a versioned snapshot."""
    from .models import RenderOptions
    from .pipeline import _tool_versions, normalization_profile, prepare

    effective_language = str(language or document.metadata.get("language") or "en")
    profile = asdict(normalization_profile(effective_language))
    runtime = _tool_versions()
    profile_fingerprint = _fingerprint("profile", profile)
    runtime_fingerprint = _fingerprint("runtime", runtime)
    options = {
        "requested_language": language,
        "effective_language": effective_language,
        "max_paragraph_chars": max_paragraph_chars,
        "apply_spokenform": apply_spokenform,
        "include_titles": include_titles,
        "lexicon": _sidecar_lexicon(sidecar),
    }
    options_fingerprint = _fingerprint("options", options)

    reports: list[ConversionReport] = []
    paragraph_groups: list[list[PreparedParagraph]] = []
    selected_chapters: list[dict[str, str]] = []
    for index, original_section in enumerate(document.sections, start=1):
        section = replace(original_section, source_index=original_section.source_index or index)
        chapter_sha256 = _section_digest(section)
        selected_chapters.append({"id": section.id, "sha256": chapter_sha256})
        cache_key, _, _ = _section_options(
            document,
            section,
            section_index=index,
            language=language,
            effective_language=effective_language,
            max_paragraph_chars=max_paragraph_chars,
            apply_spokenform=apply_spokenform,
            include_titles=include_titles,
            profile=profile,
            runtime=runtime,
            sidecar=sidecar,
        )
        cached = None if force_refresh else _load_chapter(cache_key)
        if cached is None:
            section_document = replace(document, sections=[section])
            result = prepare(
                section_document,
                language=language,
                max_paragraph_chars=max_paragraph_chars,
                apply_spokenform=apply_spokenform,
                include_titles=include_titles,
                render_options=RenderOptions(),
                sidecar=sidecar,
            )
            if result.report is None:
                raise ValueError("Conversion did not produce a report")
            chapter_report = result.report
            paragraphs = result.paragraphs
            _save_chapter(cache_key, chapter_report, paragraphs)
        else:
            chapter_report, paragraphs = cached
        chapter_report = _refresh_cached_report(
            chapter_report,
            document,
            section,
            requested_language=language,
            effective_language=effective_language,
            profile=profile,
            runtime=runtime,
        )
        reports.append(chapter_report)
        paragraph_groups.append(paragraphs)

    report = _merge_reports(reports, paragraph_groups, document)
    report.source_sha256 = document.source_sha256 or report.source_sha256
    report.content_fingerprint = document.content_fingerprint or _content_fingerprint(
        document.source.format,
        [(item["id"], item["sha256"]) for item in selected_chapters],
    )
    report.normalization_profile = profile
    report.tool_versions = runtime
    _save_snapshot(
        document,
        report,
        selected_chapters,
        profile_fingerprint,
        options_fingerprint,
        runtime_fingerprint,
    )
    return report


def _safe_bundle_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        return None
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {".", ".."} for part in path.parts):
        return None
    return value


def _bundle_chapter_hash(source: Path, chapter_id: str) -> str | None:
    if source.is_dir():
        manifest_path = source / "manifest.json"
        if manifest_path.stat().st_size > 2 * 1024 * 1024:
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest.get("chapters", [])
        entry = next(
            (item for item in entries if isinstance(item, dict) and item.get("id") == chapter_id),
            None,
        )
        if entry is None:
            return None
        relative = _safe_bundle_path(entry.get("path"))
        if relative is None:
            return None
        root = source.resolve()
        chapter_path = root.joinpath(*PurePosixPath(relative).parts)
        resolved = chapter_path.resolve(strict=True)
        resolved.relative_to(root)
        if resolved.stat().st_size > 64 * 1024 * 1024:
            return None
        data = resolved.read_bytes()
    else:
        with zipfile.ZipFile(source, "r") as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > 2 * 1024 * 1024:
                return None
            manifest = json.loads(archive.read(info).decode("utf-8"))
            entries = manifest.get("chapters", [])
            entry = next(
                (
                    item
                    for item in entries
                    if isinstance(item, dict) and item.get("id") == chapter_id
                ),
                None,
            )
            if entry is None:
                return None
            relative = _safe_bundle_path(entry.get("path"))
            if relative is None:
                return None
            info = archive.getinfo(relative)
            if info.file_size > 64 * 1024 * 1024:
                return None
            data = archive.read(info)
    digest = hashlib.sha256(data).hexdigest()
    return digest if entry.get("sha256") == digest else None


def _current_chapter_hash(source: Path, chapter_id: str, kind: str) -> str | None:
    path = source.expanduser().resolve()
    if kind == "ssmd" and path.is_file():
        if chapter_id != "document-0001":
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if kind == "ssmdbook" and (path.is_dir() or path.is_file()):
        return _bundle_chapter_hash(path, chapter_id)
    return None


def _report_chapter_for_id(report: ConversionReport, identifier: str) -> str | None:
    change = next((item for item in report.changes if item.id == identifier), None)
    if change is not None:
        return change.section_id
    from .lexical_review import lexical_context_payload

    try:
        payload = lexical_context_payload(report, identifier, paragraph=True)
    except KeyError:
        return None
    occurrences = payload.get("occurrences", [])
    return occurrences[0].get("section_id") if occurrences else None


def load_cached_report(source: str | Path, identifier: str) -> ConversionReport:
    """Find a cached report for an ID and verify only its current chapter bytes."""
    source_path = Path(source).expanduser().resolve()
    index_path = _cache_root() / "sources" / f"{_source_key(source_path)}.json"
    index = _read_json(index_path)
    if index is None or index.get("schema") != _INDEX_SCHEMA:
        raise AnalysisCacheError(
            f"No cached analysis is available for {source_path}. "
            f"Run `ttsready report {source_path}` first."
        )

    stale_chapter: str | None = None
    stale_detail: str | None = None
    found_id = False
    for entry in index.get("snapshots", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        snapshot_path = _cache_root() / entry["path"]
        snapshot = _read_json(snapshot_path)
        if snapshot is None or snapshot.get("schema") != ANALYSIS_SCHEMA:
            continue
        report_value = snapshot.get("report")
        if not isinstance(report_value, dict):
            continue
        try:
            report = _report_from_dict(report_value)
        except (KeyError, TypeError, ValueError):
            continue
        chapter_id = _report_chapter_for_id(report, identifier)
        if chapter_id is None:
            continue
        found_id = True
        chapter = next(
            (
                item
                for item in snapshot.get("source", {}).get("selected_chapters", [])
                if isinstance(item, dict) and item.get("id") == chapter_id
            ),
            None,
        )
        if chapter is None or not isinstance(chapter.get("sha256"), str):
            stale_chapter = chapter_id
            stale_detail = "the snapshot has no chapter fingerprint"
            continue
        try:
            current_sha256 = _current_chapter_hash(
                source_path,
                chapter_id,
                str(snapshot.get("source", {}).get("kind", "")),
            )
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            current_sha256 = None
            stale_detail = str(exc)
        if current_sha256 is None or current_sha256 != chapter["sha256"]:
            stale_chapter = chapter_id
            continue
        return report

    if found_id:
        detail = f" ({stale_detail})" if stale_detail else ""
        raise AnalysisCacheError(
            f"Analysis cache is stale for {stale_chapter or 'the requested chapter'}{detail}. "
            f"Run `ttsready report {source_path} --refresh`."
        )
    raise AnalysisCacheError(
        f"No cached analysis contains ID {identifier!r} for {source_path}. "
        f"Run `ttsready report {source_path}` first."
    )
