# ttsready

`ttsready` prepares documents for text-to-speech as plain UTF-8 text.

It accepts common document formats, converts written forms to spoken forms with
[`spokenform`](https://pypi.org/project/spokenform/), and limits paragraph length with
[`phrasplit`](https://pypi.org/project/phrasplit/):

```text
document -> section selection -> paragraphs -> spokenform -> semantic chunking -> txt
```

## Supported inputs

- EPUB (`.epub`) via `epub2text`
- PDF (`.pdf`) via `pypdf`
- Plain text (`.txt`, `.text`)
- Markdown (`.md`, `.markdown`, `.mdown`, `.mkd`)
- HTML/XHTML (`.html`, `.htm`, `.xhtml`)

## Output

Conversion writes plain UTF-8 text (`.txt`). SSMD is not an input or output format for
`ttsready`; downstream conversion tools own SSMD rendering.

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

Run `ttsready --help` to discover the commands. The global `--version` option prints the
installed version.

### Convert

`convert` is the only command that writes TTS-ready text files:

```bash
ttsready convert "Platform Decay - Martha Wells.epub"
ttsready convert book.epub -c 5-17 --layout chapters -o murderbot_txt/
ttsready convert book.epub --language de --max-paragraph-chars 800 --stats
```

Use `-c, --chapters` to select 1-based chapters or sections. `--sections` is an alias. Selectors
support indexes, inclusive ranges, comma-separated combinations, and `all`. Requested order is
preserved, duplicate indexes are removed, and reversed or out-of-range selections are errors.

`--layout` accepts `single` or `chapters`. In single layout, output defaults to the source filename
with a `.txt` suffix. Chapter output uses a `-ttsready/` directory by default. Chapter filenames are
sanitized and prefixed by output order.

If `--language` is omitted, document metadata is used when available, otherwise English is used.
`spokenform` and section titles are enabled by default. Use `--no-spokenform` and `--no-titles` to
disable them. `--max-paragraph-chars` controls semantic chunking; `--line-width` controls rendered
line wrapping; `--paragraph-breaks` accepts `0`, `1`, or `2`. `--stats` prints detailed conversion
statistics. Conversion warnings direct users to `ttsready report SOURCE` for details.

### Chapters

List the chapter/section hierarchy without normalization, output planning, or file writes:

```bash
ttsready chapters book.epub
```

### Preflight

`preflight` accepts the result- and destination-affecting options from `convert`. It runs the same
preparation and in-memory TXT rendering, validates the planned destinations, and does not create
output files or directories:

```bash
ttsready preflight book.epub -c 5-17 --layout chapters -o murderbot_txt/
ttsready preflight book.epub --fail-on-warning
```

Warnings are shown without failing by default. `--fail-on-warning` completes preflight and then
exits non-zero if warnings were reported.

### Report

`report` prepares an in-memory TXT preview and reports spokenform changes, exact source spans,
splitting, section metrics, and source contexts. Markdown is printed to stdout by default; use
`--format json` for JSON stdout:

```bash
ttsready report book.epub -c 5-17
ttsready report book.epub -c 5-17 --format json
ttsready report book.epub -o book.report.json
```

Write reports explicitly with `-o`. `.md` and `.json` suffixes select the matching report format.
An explicit `--format md|json` may be used with a suffixless path; conflicting or unsupported
suffixes are usage errors. The report command never writes TTS output.

### Context

Every change row has a stable ID. Use it to retrieve the source and spoken sentence without
searching the document manually:

```bash
ttsready context book.epub chg:v1:8d1b2d540c6d995a51ac
ttsready context book.epub chg:v1:8d1b2d540c6d995a51ac --bug-report
```

`--json` emits machine-readable context, and `--paragraph` includes the full source paragraph.

## Python API

```python
from ttsready import RenderOptions, convert

result = convert(
    "book.epub",
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
result = prepare(document, language="de", max_paragraph_chars=800)
```

`prepare` and `convert` return a `ConversionResult` with a structured report using schema
`ttsready.report.v2`, including section metrics, source contexts, and exact spokenform changes.
`parse_section_range` is also available for callers that need the same 1-based selector syntax.

## Paragraph sizing

`max_paragraph_chars` is applied after spoken-form normalization. Existing paragraphs that fit remain
intact. Oversized paragraphs are passed to `phrasplit.split_long_lines`, which prefers
sentence/clause boundaries and falls back to word boundaries. `--line-width` is a separate
presentation option and does not change semantic paragraph boundaries.

## Dynamic versioning

The package version is generated by `setuptools-scm`; there is no manually maintained version
constant in `pyproject.toml`. Builds from tagged Git checkouts receive the tag-derived version.

## Design boundaries

`ttsready` owns document preparation and human review. It does not generate audio, select TTS voices,
automatically detect languages, rewrite EPUB files, or render SSMD. Downstream tools own SSMD
syntax and rendering.


## Review identities

Reports use schema `ttsready.report.v2`. Each source context has a deterministic `ctx:v1:` ID, and each Spokenform change has a `chg:v1:` ID derived from its source context and exact source span. Markdown change rows start with the change ID. Lexical findings and quoted utterances also have stable, versioned IDs. Use `ttsready context SOURCE ID` for change and lexical finding IDs; `--json`, `--paragraph`, and `--bug-report` select focused output modes.


JSON reports include reusable source contexts, exact-offset source/spoken sentences, a source fingerprint, and best-effort tool version metadata. `context` returns the sentence spans overlapping a change or finding; when none overlap, it falls back to the full source context. `--paragraph` adds the complete source paragraph.

IDs identify extracted source content, not a document forever. They are repeatable while the source item, section locator, and span remain the same. Editing text, changing extraction or section boundaries, or moving a span can change its ID. IDs are not intended to survive arbitrary edits or to identify equivalent text across books.

## Lexical review

`ttsready review SOURCE` ranks uncommon-word and name candidates using provider-neutral evidence. Findings retain their source occurrences and can be opened with `ttsready context SOURCE LEX_ID`. The core command does not download dictionaries or models. Lexhint is optional and only loaded when explicitly requested:

```bash
python -m pip install -e ".[lexical]"
ttsready review book.epub --lexhint
```

## Customization sidecars

A sidecar is a human-edited YAML file using schema `ttsready.sidecar.v1`. Pass it with `--config` to `report`, `context`, `preflight`, `convert`, `speakers`, or `speaker-set`. A configured source format must match the input. `source.file_sha256` is optional, but when present it is checked before use and a stale fingerprint is rejected.

```yaml
schema: ttsready.sidecar.v1
source:
  format: text
  # Add file_sha256 with the input file's SHA-256 to detect stale configurations.
lexicon:
  - surface: Siobhan
    spoken: Shivawn
    match: word
    case_sensitive: false
    kind: pronunciation
    scope:
      type: document
    provenance:
      note: Reviewed pronunciation
  - surface: "2nd"
    spoken: second
    kind: normalization_override
    scope:
      type: section
      section_locator: "ref:chapter-2"
characters:
  - id: alice
    display_name: Alice
    aliases: [Al, Miss Smith]
speaker_annotations:
  - utterance_id: utt:v1:0123456789abcdef0123
    speaker: alice
    status: manual
    provenance:
      provider: human
```

`lexicon` items match literal source text. `match` is `literal` or whole-token `word`; `case_sensitive` defaults to `true`, and `kind` is `pronunciation` or `normalization_override`. Scope defaults to the document. A section scope needs `section_id` or `section_locator`. An occurrence scope needs `context_id` and may additionally specify both `source_start` and `source_end`. `provenance` is an arbitrary YAML mapping. IDs may be omitted and are then generated deterministically. Conflicting overlapping overrides at the same priority fail instead of silently choosing one. Normalization overrides protect their matched source spans while leaving unrelated Spokenform transformations active.

The `characters` list is a registry of logical speaker candidates. IDs must be unique; aliases are candidate names, not TTS-provider voice bindings. Keep voice selection outside this file. Speaker annotations identify one utterance and one registered logical character. Only `accepted` and `manual` annotations are valid, and a sidecar can contain at most one annotation per utterance. Automated suggestions are never written as annotations.

## Speaker review

`ttsready speakers` extracts quoted source spans and prints their stable utterance IDs. Without a provider, it is a manual review list. Provider suggestions require the explicit `--jev` option and the optional extra:

```bash
python -m pip install -e ".[speakers]"
ttsready speakers book.epub --config book.ttsready.yaml

ttsready speakers book.epub --config book.ttsready.yaml --jev
```

The Jev adapter can choose only from logical IDs in `characters` or return unknown. The optional pyjev dependency is imported only when Jev is explicitly invoked, and suggestions remain unaccepted. Use `--format json` for machine-readable review output. To make an explicit manual assignment, copy the utterance ID from the review and choose a registered speaker:

```bash
ttsready speaker-set book.epub --config book.ttsready.yaml \
  --utterance utt:v1:0123456789abcdef0123 --speaker alice
```

This command verifies the source fingerprint, checks the utterance and speaker IDs, and writes a `manual` annotation to the sidecar. Python callers can instead pass a provider suggestion through `accept_speaker_suggestion()` and persist the returned `accepted` decision with `write_speaker_decisions()`. Persistence accepts only accepted or manual decisions.

## Downstream mapping contract

`ttsready` does not emit SSMD. A downstream converter may map a pronunciation `lexicon` item from `surface` and `spoken` to an SSMD substitution such as `[Siobhan]{sub="Shivawn"}`. Character-registry aliases are not automatically pronunciation substitutions; represent a spoken form in `lexicon` when that mapping is wanted.

For speaker markup, a downstream converter should consume only `speaker_annotations` with `accepted` or `manual` status. The annotation's `utterance_id` anchors the source quote, and its `speaker` value is the logical ID from `characters`. A converter may map that logical ID to a voice block such as `:::{voice="alice"}`. Concrete AWS, Google, Azure, or other voice names belong in downstream configuration, not in ttsready's sidecar. This describes the consumer contract only; it does not implement or verify a consumer.

## Non-goals

`ttsready` does not render SSMD, generate audio, select TTS-provider voices, infer a speaker without review, accept provider suggestions automatically, mutate EPUB files, or download optional provider resources automatically. SSMD parsing and rendering belong downstream.
