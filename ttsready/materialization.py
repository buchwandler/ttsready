"""Materialize reviewed spoken changes as canonical SSMD annotations."""

from __future__ import annotations

import errno
import os
import re
import stat
import tempfile
from dataclasses import replace
from pathlib import Path

import ssmd
from ssmd.utils import format_ssmd_attr
from ssmdconvert import BookBundleError, load_book_bundle, load_book_workspace, write_book_bundle

from .analysis import load_cached_report
from .errors import TTSReadyError
from .input import _parse_ssmd, load
from .models import ConversionReport, Document, Section, SpokenChange
from .pipeline import _authoritative_annotation, _paragraph_ranges, prepare
from .sidecar import Sidecar, canonical_source_identity, save_sidecar
from .speakers.review import extract_utterances


class MaterializationError(ValueError):
    """Raised when a reviewed source span cannot be safely materialized."""


def _validate_updated_ssmd(source: str, *, expected_clean_text: str) -> None:
    try:
        structure = _parse_ssmd(source, label="materialized SSMD")
    except TTSReadyError as exc:
        raise MaterializationError(str(exc)) from exc
    if structure.clean_text != expected_clean_text:
        raise MaterializationError(
            "Materializing the substitution would change the SSMD clean text"
        )


def _replace_existing_attribute(
    source: str,
    *,
    source_start: int,
    source_end: int,
    attribute_name: str,
    spoken: str,
) -> str:
    raw_annotation = source[source_start:source_end]
    attr_pattern = re.compile(
        rf"(?<![A-Za-z0-9_-]){re.escape(attribute_name)}\s*=\s*(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')",
        re.DOTALL,
    )
    matches = list(attr_pattern.finditer(raw_annotation))
    if len(matches) != 1:
        raise MaterializationError(
            f"Could not safely update the existing SSMD {attribute_name} annotation"
        )
    updated_annotation = attr_pattern.sub(
        lambda _: format_ssmd_attr(attribute_name, spoken), raw_annotation, count=1
    )
    return source[:source_start] + updated_annotation + source[source_end:]


def _map_clean_span(
    source: str,
    *,
    expected_clean_text: str,
    start: int,
    end: int,
    surface: str,
) -> int:
    marker = "TTSREADYMATERIALIZATIONSENTINEL"
    while marker in source:
        marker += "X"
    expected_marked_text = expected_clean_text[:start] + marker + expected_clean_text[end:]
    raw_matches: list[int] = []
    position = source.find(surface)
    while position >= 0:
        marked_source = source[:position] + marker + source[position + len(surface) :]
        try:
            marked_structure = _parse_ssmd(marked_source, label="SSMD source-span probe")
        except TTSReadyError:
            position = source.find(surface, position + 1)
            continue
        if marked_structure.clean_text == expected_marked_text:
            raw_matches.append(position)
        position = source.find(surface, position + 1)
    if len(raw_matches) != 1:
        if not raw_matches:
            raise MaterializationError(
                "Could not map the reviewed clean-text span to an exact raw SSMD source span"
            )
        raise MaterializationError("The reviewed clean-text span maps to multiple raw SSMD spans")
    return raw_matches[0]


def materialize_substitution(
    source: str,
    *,
    expected_clean_text: str,
    start: int,
    end: int,
    surface: str,
    spoken: str,
) -> str:
    """Add or update one exact source-span SSMD sub annotation."""
    if not surface or not spoken:
        raise MaterializationError("Source surface and spoken replacement must be non-empty")
    structure = _parse_ssmd(source, label="source SSMD")
    if structure.clean_text != expected_clean_text:
        raise MaterializationError("The source SSMD no longer matches the reviewed analysis")
    if start < 0 or end > len(expected_clean_text) or start >= end:
        raise MaterializationError("The reviewed source span is outside the current SSMD text")
    if expected_clean_text[start:end] != surface:
        raise MaterializationError("The reviewed source span no longer contains the expected text")

    overlapping = [
        annotation
        for annotation in structure.annotations
        if annotation.char_start < end and start < annotation.char_end
    ]
    exact_subs = [
        annotation
        for annotation in overlapping
        if annotation.char_start == start
        and annotation.char_end == end
        and annotation.attrs.get("sub") is not None
    ]
    if len(exact_subs) > 1:
        raise MaterializationError("The exact source span has multiple SSMD sub annotations")
    if exact_subs:
        annotation = exact_subs[0]
        if annotation.attrs["sub"] == spoken:
            return source
        if annotation.source_start is None or annotation.source_end is None:
            raise MaterializationError("The existing SSMD sub annotation has no source location")
        updated = _replace_existing_attribute(
            source,
            source_start=annotation.source_start,
            source_end=annotation.source_end,
            attribute_name="sub",
            spoken=spoken,
        )
        _validate_updated_ssmd(updated, expected_clean_text=expected_clean_text)
        updated_structure = _parse_ssmd(updated, label="materialized SSMD")
        if not any(
            item.char_start == start and item.char_end == end and item.attrs.get("sub") == spoken
            for item in updated_structure.annotations
        ):
            raise MaterializationError(
                "The updated SSMD does not contain the requested sub annotation"
            )
        return updated

    if any(_authoritative_annotation(annotation) for annotation in overlapping):
        raise MaterializationError(
            "The reviewed source span overlaps an existing authoritative SSMD annotation"
        )

    raw_start = _map_clean_span(
        source,
        expected_clean_text=expected_clean_text,
        start=start,
        end=end,
        surface=surface,
    )
    escaped_surface = ssmd.escape_ssmd_syntax(surface)
    annotation = f"[{escaped_surface}]{{{format_ssmd_attr('sub', spoken)}}}"
    updated = source[:raw_start] + annotation + source[raw_start + len(surface) :]
    _validate_updated_ssmd(updated, expected_clean_text=expected_clean_text)
    updated_structure = _parse_ssmd(updated, label="materialized SSMD")
    if not any(
        item.char_start == start and item.char_end == end and item.attrs.get("sub") == spoken
        for item in updated_structure.annotations
    ):
        raise MaterializationError(
            "The materialized SSMD does not contain the requested sub annotation"
        )
    return updated


def materialize_voice_annotation(
    source: str,
    *,
    expected_clean_text: str,
    start: int,
    end: int,
    surface: str,
    speaker_id: str,
) -> str:
    """Add or update one exact source-span logical SSMD voice annotation."""
    if not surface or not speaker_id:
        raise MaterializationError("Utterance text and logical speaker ID must be non-empty")
    structure = _parse_ssmd(source, label="source SSMD")
    if structure.clean_text != expected_clean_text:
        raise MaterializationError("The source SSMD no longer matches the reviewed utterance")
    if start < 0 or end > len(expected_clean_text) or start >= end:
        raise MaterializationError("The reviewed utterance span is outside the current SSMD text")
    if expected_clean_text[start:end] != surface:
        raise MaterializationError(
            "The reviewed utterance span no longer contains the expected text"
        )

    overlapping_voices = [
        annotation
        for annotation in structure.annotations
        if "voice" in annotation.attrs
        and annotation.char_start < end
        and start < annotation.char_end
    ]
    if len(overlapping_voices) > 1:
        raise MaterializationError("The utterance overlaps multiple SSMD voice annotations")
    if overlapping_voices:
        annotation = overlapping_voices[0]
        contains_span = annotation.char_start <= start and annotation.char_end >= end
        if not contains_span:
            raise MaterializationError("The utterance partially overlaps an SSMD voice annotation")
        if annotation.attrs["voice"] == speaker_id:
            return source
        if annotation.char_start != start or annotation.char_end != end:
            raise MaterializationError(
                "A broader SSMD voice annotation conflicts with this decision"
            )
        if annotation.source_start is None or annotation.source_end is None:
            raise MaterializationError("The existing SSMD voice annotation has no source location")
        updated = _replace_existing_attribute(
            source,
            source_start=annotation.source_start,
            source_end=annotation.source_end,
            attribute_name="voice",
            spoken=speaker_id,
        )
        _validate_updated_ssmd(updated, expected_clean_text=expected_clean_text)
        updated_structure = _parse_ssmd(updated, label="materialized SSMD")
        if not any(
            item.char_start == start
            and item.char_end == end
            and item.attrs.get("voice") == speaker_id
            for item in updated_structure.annotations
        ):
            raise MaterializationError(
                "The updated SSMD does not contain the requested voice annotation"
            )
        return updated

    raw_start = _map_clean_span(
        source,
        expected_clean_text=expected_clean_text,
        start=start,
        end=end,
        surface=surface,
    )
    escaped_surface = ssmd.escape_ssmd_syntax(surface)
    annotation = f"[{escaped_surface}]{{{format_ssmd_attr('voice', speaker_id)}}}"
    updated = source[:raw_start] + annotation + source[raw_start + len(surface) :]
    _validate_updated_ssmd(updated, expected_clean_text=expected_clean_text)
    updated_structure = _parse_ssmd(updated, label="materialized SSMD")
    if not any(
        item.char_start == start and item.char_end == end and item.attrs.get("voice") == speaker_id
        for item in updated_structure.annotations
    ):
        raise MaterializationError(
            "The materialized SSMD does not contain the requested voice annotation"
        )
    return updated


def _find_change_context(
    document: Document,
    report: ConversionReport,
    change: SpokenChange,
) -> tuple[Section, int, int]:
    context = next((item for item in report.contexts if item.id == change.context_id), None)
    if context is None:
        raise MaterializationError(f"Cached change {change.id!r} has no source context")
    if context.is_title:
        raise MaterializationError(
            "Title changes cannot be materialized as inline SSMD substitutions"
        )
    section = next((item for item in document.sections if item.id == change.section_id), None)
    if section is None or section.ssmd is None:
        raise MaterializationError(f"SSMD section {change.section_id!r} is no longer available")
    report_section = next(
        (item for item in report.sections if item.section_id == change.section_id),
        None,
    )
    if report_section is None or report_section.chapter_sha256 != section.chapter_sha256:
        raise MaterializationError("The SSMD chapter has changed since this change was reviewed")
    ranges = _paragraph_ranges(section.text)
    if change.source_paragraph < 0 or change.source_paragraph >= len(ranges):
        raise MaterializationError("The reviewed source paragraph is no longer available")
    paragraph_start, paragraph_end = ranges[change.source_paragraph]
    paragraph_text = section.text[paragraph_start:paragraph_end]
    if paragraph_text != context.source_text:
        raise MaterializationError("The reviewed source paragraph no longer matches the SSMD text")
    start = paragraph_start + change.source_start
    end = paragraph_start + change.source_end
    if (
        end - start != len(change.source)
        or paragraph_text[change.source_start : change.source_end] != change.source
    ):
        raise MaterializationError("The reviewed source span no longer contains the expected text")
    return section, start, end


def _default_output_path(source: Path) -> Path:
    name = source.name
    for suffix in (".ssmdbook.zip", ".ssmdbook", ".ssmd.md", ".ssmd"):
        if name.casefold().endswith(suffix):
            stem = name[: -len(suffix)]
            return source.with_name(f"{stem}.reviewed{suffix}")
    raise MaterializationError(f"Unsupported SSMD input path: {source}")


def _output_bundle_format(path: Path) -> str:
    if path.name.casefold().endswith(".ssmdbook.zip"):
        return "zip"
    if path.name.casefold().endswith(".ssmdbook"):
        return "directory"
    raise MaterializationError("SSMD book output must end in .ssmdbook or .ssmdbook.zip")


def _write_standalone_atomic(path: Path, source: bytes, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {path}")
    if path.exists() and path.is_dir():
        raise IsADirectoryError(path)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            if path.exists():
                os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except (AttributeError, OSError) as exc:
                if (
                    isinstance(exc, OSError)
                    and exc.errno not in {errno.EOPNOTSUPP, errno.EXDEV, errno.ENOSYS}
                ):
                    raise
                with path.open("xb") as stream:
                    stream.write(temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)


def _resolve_output_target(
    source: Path,
    output: str | Path | None,
    *,
    overwrite: bool,
) -> Path:
    if overwrite:
        if output is not None:
            raise MaterializationError(
                "An explicit output path cannot be combined with in-place writing"
            )
        return source
    target = (
        Path(output).expanduser().resolve() if output is not None else _default_output_path(source)
    )
    if target == source:
        raise MaterializationError("Use --write to replace the source SSMD input")
    return target


def _write_updated_section(
    source: Path,
    target: Path,
    section: Section,
    updated_ssmd: str,
    *,
    overwrite: bool,
) -> Path:
    if source.name.casefold().endswith((".ssmdbook", ".ssmdbook.zip")):
        try:
            book = load_book_workspace(source).book if source.is_dir() else load_book_bundle(source)
            original_chapter = next(
                (chapter for chapter in book.chapters if chapter.id == section.id),
                None,
            )
            if original_chapter is None or original_chapter.ssmd != section.ssmd:
                raise MaterializationError(
                    "The SSMD chapter changed while the override was being prepared"
                )
            chapters = tuple(
                replace(chapter, ssmd=updated_ssmd) if chapter.id == section.id else chapter
                for chapter in book.chapters
            )
            return write_book_bundle(
                replace(book, chapters=chapters),
                target,
                format=_output_bundle_format(target),
                overwrite=overwrite,
            )
        except BookBundleError as exc:
            raise MaterializationError(str(exc)) from exc

    if not target.name.casefold().endswith((".ssmd.md", ".ssmd")):
        raise MaterializationError("Standalone SSMD output must end in .ssmd or .ssmd.md")
    raw = source.read_bytes()
    if raw.decode("utf-8-sig") != section.ssmd:
        raise MaterializationError("The SSMD source changed while the override was being prepared")
    bom = bytes.fromhex("efbbbf") if raw.startswith(bytes.fromhex("efbbbf")) else b""
    _write_standalone_atomic(target, bom + updated_ssmd.encode("utf-8"), overwrite=overwrite)
    return target


def materialize_change(
    source_path: str | Path,
    change_id: str,
    spoken: str,
    *,
    output: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write one reviewed change as an SSMD sub annotation."""
    source = Path(source_path).expanduser().resolve()
    report = load_cached_report(source, change_id)
    change = next((item for item in report.changes if item.id == change_id), None)
    if change is None:
        raise MaterializationError(f"No cached spoken change has ID {change_id!r}")
    document = load(source)
    section, start, end = _find_change_context(document, report, change)
    if section.ssmd is None:
        raise MaterializationError(f"SSMD section {section.id!r} has no source markup")
    updated_ssmd = materialize_substitution(
        section.ssmd,
        expected_clean_text=section.text,
        start=start,
        end=end,
        surface=change.source,
        spoken=spoken,
    )

    target = _resolve_output_target(source, output, overwrite=overwrite)
    return _write_updated_section(source, target, section, updated_ssmd, overwrite=overwrite)


def materialize_speaker_decision(
    source_path: str | Path,
    utterance_id_value: str,
    sidecar: Sidecar,
    sidecar_path: str | Path,
    *,
    output: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Materialize one accepted/manual speaker decision and re-anchor its sidecar."""
    source = Path(source_path).expanduser().resolve()
    document = load(source)
    if sidecar.source != canonical_source_identity(document):
        raise MaterializationError("The speaker sidecar does not match the canonical SSMD input")
    decision = next(
        (
            item
            for item in sidecar.speaker_annotations
            if item["utterance_id"] == utterance_id_value
        ),
        None,
    )
    if decision is None:
        raise KeyError(f"No accepted/manual speaker decision exists for {utterance_id_value!r}")
    if decision["status"] not in {"accepted", "manual"}:
        raise MaterializationError("Only accepted/manual speaker decisions can be materialized")
    candidate_ids = {item["id"] for item in sidecar.characters}
    if decision["speaker"] not in candidate_ids:
        raise MaterializationError(
            "Speaker decision does not reference a registered logical speaker"
        )

    result = prepare(document, apply_spokenform=False)
    if result.report is None:
        raise MaterializationError(
            "Could not build current source contexts for speaker materialization"
        )
    utterance = next(
        (
            item
            for item in extract_utterances(result.report.contexts)
            if item.id == utterance_id_value
        ),
        None,
    )
    if utterance is None:
        raise MaterializationError(
            f"Stale speaker decision: utterance {utterance_id_value!r} no longer exists in SSMD"
        )
    context = next(item for item in result.report.contexts if item.id == utterance.context_id)
    section = next((item for item in document.sections if item.id == context.section_id), None)
    if section is None or section.ssmd is None or context.is_title:
        raise MaterializationError(
            "The reviewed utterance no longer maps to an SSMD source section"
        )
    ranges = _paragraph_ranges(section.text)
    if context.source_paragraph < 0 or context.source_paragraph >= len(ranges):
        raise MaterializationError("The reviewed utterance source paragraph is no longer available")
    paragraph_start, paragraph_end = ranges[context.source_paragraph]
    paragraph_text = section.text[paragraph_start:paragraph_end]
    if paragraph_text != context.source_text:
        raise MaterializationError("The reviewed utterance paragraph no longer matches SSMD")
    if paragraph_text[utterance.start : utterance.end] != utterance.text:
        raise MaterializationError("The reviewed utterance source span no longer matches SSMD")
    start = paragraph_start + utterance.start
    end = paragraph_start + utterance.end
    updated_ssmd = materialize_voice_annotation(
        section.ssmd,
        expected_clean_text=section.text,
        start=start,
        end=end,
        surface=utterance.text,
        speaker_id=decision["speaker"],
    )

    target = _resolve_output_target(source, output, overwrite=overwrite)
    written = _write_updated_section(source, target, section, updated_ssmd, overwrite=overwrite)
    updated_sidecar = replace(sidecar, source=canonical_source_identity(load(written)))
    save_sidecar(sidecar_path, updated_sidecar)
    return written
