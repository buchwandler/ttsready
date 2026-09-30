# ttsready

`ttsready` prepares documents for text-to-speech engines.

It accepts common document formats, converts written forms to spoken forms with
[`spokenform`](https://pypi.org/project/spokenform/), limits paragraph length with
[`phrasplit`](https://pypi.org/project/phrasplit/), and renders either plain UTF-8 text
or SSMD.

The single-command workflow keeps the existing invocation and prepares selected source sections:

```text
document -> section selection -> paragraphs -> spokenform -> semantic chunking -> txt/ssmd
```

## Supported inputs

- EPUB (`.epub`) via `epub2text`
- PDF (`.pdf`) via `pypdf`
- plain text (`.txt`, `.text`)
- Markdown (`.md`, `.markdown`, `.mdown`, `.mkd`)
- HTML/XHTML (`.html`, `.htm`, `.xhtml`)
- SSMD (`.ssmd`)

## Outputs

- plain UTF-8 text (`txt`)
- SSMD 0.9 (`ssmd`)

## Install

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## CLI

The primary invocation remains `ttsready SOURCE`. Plain text is the default output:

```bash
ttsready "Platform Decay - Martha Wells.epub"
ttsready book.epub -o book.txt --language de --max-paragraph-chars 800
```

If `--language` is omitted, `ttsready` uses document metadata when available and falls
back to English. `spokenform` is enabled by default. Disable normalization with
`--no-spokenform`. Real section titles are included by default; use `--no-titles` to omit them.

### List and select sections

List available chapters or sections without preparing or writing output:

```bash
ttsready book.epub --list-chapters
```

`--list-sections` is an alias. Select sections with 1-based indexes and inclusive ranges:

```bash
ttsready book.epub --chapters 3-5,8 -o selected.txt
ttsready book.epub --sections 4,1-2 --preflight
```

Selections preserve the requested order and remove duplicate indexes. Invalid or out-of-range
selections are errors. The same options work for Markdown and other documents with sections.

### Output formats and layouts

An explicit `--format txt|ssmd` takes precedence over suffix inference. In single-file layout,
an `.ssmd` output suffix selects SSMD when `--format` is omitted. Chapter layout defaults to TXT:

```bash
ttsready book.epub --format ssmd -o book.ssmd
ttsready book.epub --chapters 3-5 --output-layout chapters -o selected/
```

Chapter layout writes one file per selected section. Filenames are sanitized and prefixed by
their output order. If `-o` is omitted, the output directory is derived as `book-ttsready/`.

### Statistics, reports, and preflight

`--stats` prints conversion, spokenform, splitting, and output statistics. `--report` writes a
detailed Markdown or JSON report containing exact changed source spans and their provenance:

```bash
ttsready book.epub --stats
ttsready book.epub --report report.md
ttsready book.epub --chapters 3-5 --output-layout chapters -o selected/ --report report.json
```

`--preflight` runs the full selected preparation and rendering path in memory, prints statistics
and the planned destination paths, and writes no TTS output files. An explicitly requested
`--report` file may still be written:

```bash
ttsready book.epub --chapters 4-9 --preflight
ttsready book.epub --preflight --report preflight.json
```

### Paragraph sizing and rendered lines

`--max-paragraph-chars` controls semantic TTS chunking after spoken-form normalization.
`--line-width` is a separate presentation option. It wraps at whitespace and does not split long
words or change the number of prepared paragraphs. `--paragraph-breaks` controls separation
between prepared paragraphs: `0` joins them with spaces, `1` uses one newline, and `2` uses a
blank line. The default is `2`, preserving the existing TXT layout.

```bash
ttsready book.epub --max-paragraph-chars 900 --line-width 100 --paragraph-breaks 1
```

## Python API

```python
from ttsready import RenderOptions, convert

result = convert(
    "book.epub",
    output_format="txt",
    language="de",
    max_paragraph_chars=800,
    render_options=RenderOptions(line_width=100, paragraph_breaks=1),
)

print(result.text)
print(result.language)
print(len(result.paragraphs))
print(result.report.spokenform.source_replacements if result.report else 0)
```

You can separate loading and preparation:

```python
from ttsready import load, prepare

document = load("book.epub")
result = prepare(
    document,
    output_format="txt",
    language="de",
    max_paragraph_chars=800,
)
```


`prepare` and `convert` return a `ConversionResult` with a structured `ConversionReport`, including
section metrics and exact `spokenform` source changes. `parse_section_range` is also available
from the package for callers that need the same 1-based selector syntax.

## Paragraph sizing

`max_paragraph_chars` is applied **after** spoken-form normalization. Existing paragraphs
that fit remain intact. Oversized paragraphs are passed to `phrasplit.split_long_lines`,
which prefers sentence/clause boundaries and falls back to word boundaries. This means a
very long source paragraph may become two or more output paragraphs as needed.

## Dynamic versioning

The package version is generated by `setuptools-scm`; there is no manually maintained
version constant in `pyproject.toml`.

Create Git tags such as:

```bash
git tag v0.1.0
```

Builds from a tagged Git checkout receive the tag-derived version. Untagged development
builds receive a development version. Source archives without `.git` metadata use the fallback
version `0.1.0.dev0` until placed in a Git repository.

The generated `ttsready/_version.py` is build output and should not be edited manually.

## Design boundaries

`ttsready` remains a single-command preparation CLI. It does not generate audio, detect languages
automatically, or add DOCX support. Chapter discovery and selection apply to the sections supplied
by existing readers.
