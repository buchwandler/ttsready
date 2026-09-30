"""Input readers for the MVP."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from .errors import TTSReadyError, UnsupportedInputError
from .models import Document, Section, SourceInfo


class InputReader(Protocol):
    name: str

    def supports(self, source: Path) -> bool: ...

    def load(self, source: Path) -> Document: ...


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _plain_section(source: Path, fmt: str, media_type: str, text: str) -> Document:
    return Document(
        source=SourceInfo(source, fmt, media_type),
        sections=[Section("section-0001", _normalize_newlines(text).strip())],
        metadata={"title": source.stem},
    )


class TextReader:
    name = "text"
    suffixes = {".txt", ".text"}

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes

    def load(self, source: Path) -> Document:
        return _plain_section(source, "text", "text/plain", read_text_file(source))


_MARKDOWN_H1 = re.compile(r"^#\s+(.+?)\s*$")


def _markdown_inline_to_text(value: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"(?<!\\)[*_~]{1,3}", "", value)
    value = re.sub(r"\\([\\`*_{}\[\]()#+.!>-])", r"\1", value)
    return value.strip()


def _split_markdown(text: str) -> list[tuple[str | None, str]]:
    lines = _normalize_newlines(text).splitlines()
    sections: list[tuple[str | None, list[str]]] = []
    title: str | None = None
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal body
        rendered = "\n".join(body).strip()
        if rendered or title:
            sections.append((title, body))
        body = []

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _MARKDOWN_H1.match(raw)
        if match:
            flush()
            title = _markdown_inline_to_text(match.group(1))
            continue
        line = raw
        line = re.sub(r"^\s{0,3}#{2,6}\s+", "", line)
        line = re.sub(r"^\s*>\s?", "", line)
        line = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", line)
        line = _markdown_inline_to_text(line)
        body.append(line)
    flush()

    result: list[tuple[str | None, str]] = []
    for section_title, section_lines in sections:
        content = "\n".join(section_lines).strip()
        if content or section_title:
            result.append((section_title, content))
    return result or [(None, "")]


class MarkdownReader:
    name = "markdown"
    suffixes = {".md", ".markdown", ".mdown", ".mkd"}

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes

    def load(self, source: Path) -> Document:
        sections = [
            Section(f"section-{idx:04d}", body, title=title)
            for idx, (title, body) in enumerate(_split_markdown(read_text_file(source)), start=1)
        ]
        return Document(
            source=SourceInfo(source, "markdown", "text/markdown"),
            sections=sections,
            metadata={"title": source.stem},
        )


_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "nav",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
    "hr",
}


class _HTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.ignore_depth = 0
        self.in_title = False

    def _break(self) -> None:
        if self.parts and not "".join(self.parts).endswith("\n\n"):
            self.parts.append("\n\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"script", "style", "svg", "math"}:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag == "title":
            self.in_title = True
        elif tag in _BLOCK_TAGS:
            self._break()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg", "math"}:
            if self.ignore_depth:
                self.ignore_depth -= 1
            return
        if self.ignore_depth:
            return
        if tag == "title":
            self.in_title = False
        elif tag in _BLOCK_TAGS:
            self._break()

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        value = re.sub(r"\s+", " ", data)
        if not value.strip():
            return
        if self.parts and not self.parts[-1].endswith((" ", "\n")):
            self.parts.append(" ")
        self.parts.append(value.strip())

    def result(self) -> tuple[str, str | None]:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        title = re.sub(r"\s+", " ", "".join(self.title_parts)).strip() or None
        return text, title


class HtmlReader:
    name = "html"
    suffixes = {".html", ".htm", ".xhtml"}

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes

    def load(self, source: Path) -> Document:
        parser = _HTMLToText()
        parser.feed(read_text_file(source))
        parser.close()
        text, title = parser.result()
        return Document(
            source=SourceInfo(source, "html", "text/html"),
            sections=[Section("section-0001", text)],
            metadata={"title": title or source.stem},
        )


class EpubReader:
    name = "epub"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".epub"

    def load(self, source: Path) -> Document:
        from epub2text import EPUBParser

        try:
            parser = EPUBParser(str(source))
            chapters = parser.get_chapter_documents()
            epub_metadata = parser.get_metadata()
        except (OSError, ValueError) as exc:
            raise TTSReadyError(f"Could not read EPUB {source.name}: {exc}") from exc

        sections = [
            Section(
                id=chapter.id,
                text=chapter.text.strip(),
                title=chapter.title,
                source_ref=chapter.href,
                parent_id=chapter.parent_id,
                level=chapter.level,
            )
            for chapter in chapters
            if chapter.text.strip() or chapter.title.strip()
        ]
        if not sections:
            raise TTSReadyError(f"EPUB did not yield readable chapters: {source.name}")

        metadata: dict[str, object] = {"title": epub_metadata.title or source.stem}
        if epub_metadata.authors:
            metadata["author"] = epub_metadata.authors[0]
        if epub_metadata.language:
            metadata["language"] = epub_metadata.language
        if epub_metadata.publisher:
            metadata["publisher"] = epub_metadata.publisher
        if epub_metadata.identifier:
            metadata["identifier"] = epub_metadata.identifier

        return Document(
            source=SourceInfo(source, "epub", "application/epub+zip"),
            sections=sections,
            metadata=metadata,
        )


class PdfReader:
    name = "pdf"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".pdf"

    def load(self, source: Path) -> Document:
        from pypdf import PdfReader as _PdfReader

        reader = _PdfReader(str(source))
        pages: list[str] = []
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)

        metadata: dict[str, object] = {"title": source.stem}
        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = str(reader.metadata.title)
            if reader.metadata.author:
                metadata["author"] = str(reader.metadata.author)

        return Document(
            source=SourceInfo(source, "pdf", "application/pdf"),
            sections=[Section("section-0001", "\n\n".join(pages))],
            metadata=metadata,
        )


class SsmdReader:
    name = "ssmd"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".ssmd"

    def load(self, source: Path) -> Document:
        from ssmd import parse_front_matter

        raw = read_text_file(source)
        parsed = parse_front_matter(raw)
        metadata = dict(parsed.data) if parsed.present else {}
        metadata.pop("ssmd_version", None)
        metadata.setdefault("title", source.stem)
        body = parsed.body if parsed.present else raw
        return Document(
            source=SourceInfo(source, "ssmd", "text/markdown"),
            sections=[Section("section-0001", body.strip())],
            metadata=metadata,
        )


def default_readers() -> list[InputReader]:
    return [TextReader(), MarkdownReader(), HtmlReader(), EpubReader(), PdfReader(), SsmdReader()]


def reader_for(source: str | Path, readers: list[InputReader] | None = None) -> InputReader:
    path = Path(source).expanduser().resolve()
    candidates = readers or default_readers()
    for reader in candidates:
        if reader.supports(path):
            return reader
    names = ", ".join(reader.name for reader in candidates)
    raise UnsupportedInputError(
        f"Unsupported input: {path.suffix or '<no suffix>'}; readers: {names}"
    )


def load(source: str | Path, readers: list[InputReader] | None = None) -> Document:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return reader_for(path, readers).load(path)
