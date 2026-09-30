# ttsready

`ttsready` prepares documents for text-to-speech engines.

It accepts common document formats, converts written forms to spoken forms with
[`spokenform`](https://pypi.org/project/spokenform/), limits paragraph length with
[`phrasplit`](https://pypi.org/project/phrasplit/), and renders either plain UTF-8 text
or SSMD.

The command-oriented workflow separates inspection, validation, conversion, and reporting while
keeping file-writing behavior explicit:

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

Run `ttsready --help` to discover the four commands. The global `--version` option prints the
installed version.

### Convert

`convert` is the only command that writes TTS-ready TXT or SSMD files:

```bash
ttsready convert "Platform Decay - Martha Wells.epub"
ttsready convert book.epub -c 5-17 --layout chapters -o murderbot_txt/
ttsready convert book.epub --format ssmd -o book.ssmd
ttsready convert book.epub --language de --max-paragraph-chars 800 --stats
```

Use `-c, --chapters` to select 1-based chapters or sections. `--sections` is an alias. Selectors
support indexes, inclusive ranges, comma-separated combinations, and `all`. Requested order is
preserved, duplicate indexes are removed, and reversed or out-of-range selections are errors.

`--layout` accepts `single` or `chapters`. An explicit `--format txt|ssmd` wins. In single
layout, an `.ssmd` output suffix selects SSMD when format is omitted; chapter layout defaults to
TXT. Chapter filenames are sanitized and prefixed by output order. Without `-o`, single output is
derived from the source filename and chapter output uses a `-ttsready/` directory.

If `--language` is omitted, document metadata is used when available, otherwise English is used.
`spokenform` and section titles are enabled by default. Use `--no-spokenform` and `--no-titles` to
disable them. `--max-paragraph-chars` controls semantic chunking; `--line-width` controls rendered
line wrapping; `--paragraph-breaks` accepts `0`, `1`, or `2`. `--stats` prints detailed
conversion statistics. Conversion warnings direct users to `ttsready report SOURCE` for details.

### Chapters

List the source's chapter/section hierarchy without normalization, TTS rendering, output planning, or file writes:

```bash
ttsready chapters book.epub
```

### Preflight

`preflight` accepts the result- and destination-affecting options from `convert`. It runs the same
preparation and in-memory rendering, validates the planned destinations, and does not create TTS
files or directories:

```bash
ttsready preflight book.epub -c 5-17 --layout chapters -o murderbot_txt/
ttsready preflight book.epub --format ssmd -o book.ssmd --fail-on-warning
```

Warnings are shown without failing by default. `--fail-on-warning` completes the full preflight and
then exits non-zero if warnings were reported. `preflight` does not accept `--stats` or a
report-file option.

### Report

`report` prepares a canonical TXT preview and reports spokenform changes, exact source spans,
splitting, and section metrics. It never writes TTS output. Markdown is printed to stdout by default;
use `--format json` for JSON stdout:

```bash
ttsready report book.epub -c 5-17
ttsready report book.epub -c 5-17 --format json
```

Write a report explicitly with `-o`. `.md` and `.json` suffixes select the matching format. An
explicit `--format md|json` may be used with a suffixless path; conflicting or unsupported suffixes
are usage errors:

```bash
ttsready report book.epub -c 5-17 -o report.md
ttsready report book.epub -o report.json
ttsready report book.epub -o diagnostics --format json
```

Only the requested report file may be written. The no-file report describes an in-memory
prepared-text preview, not a created TTS file.

### Paragraph sizing and rendered lines

`--max-paragraph-chars` controls semantic TTS chunking after spoken-form normalization.
`--line-width` is a separate presentation option. It wraps at whitespace and does not split long
words or change the number of prepared paragraphs. `--paragraph-breaks` controls separation between
prepared paragraphs: `0` joins them with spaces, `1` uses one newline, and `2` uses a blank line. The
default is `2`, preserving the existing TXT layout.

```bash
ttsready convert book.epub --max-paragraph-chars 900 --line-width 100 --paragraph-breaks 1
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

`ttsready` remains a document preparation CLI with distinct inspection, conversion, preflight, and reporting commands. It does not generate audio, detect languages
automatically, or add DOCX support. Chapter discovery and selection apply to the sections supplied
by existing readers.
