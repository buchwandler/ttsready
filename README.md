# ttsready

`ttsready` analyzes canonical SSMD 0.9 documents and `.ssmdbook` bundles, reviews speech decisions, and can materialize approved changes back into SSMD. It does not ingest EPUB, PDF, Markdown, HTML, or plain-text source files directly, and it does not generate audio.

The interchange boundary is the SSMD artifact:

```text
source formats -> ssmdconvert -> canonical SSMD -> ttsready review/materialization
                                                    |
                                                    v
                                         reviewed SSMD for downstream TTS
```

`ssmdconvert` owns source extraction, conversion, chapter identity, and book-bundle integrity. `ttsready` owns SSMD speech analysis, review, reproducibility, and reviewed SSMD changes. Downstream renderers consume the resulting SSMD document or book. There is no runtime API coupling between `ttsready` and a renderer.

## Supported inputs

`ttsready` accepts:

- standalone `.ssmd` and `.ssmd.md` documents;
- `.ssmdbook` directory bundles;
- `.ssmdbook.zip` bundles.

Inputs must contain valid SSMD 0.9. Convert EPUB, PDF, Markdown, HTML, text, or other supported sources with `ssmdconvert` first:

```bash
ssmdconvert book convert novel.epub -o novel.ssmdbook
ssmdconvert convert manuscript.md -o manuscript.ssmd
```

## Install

```bash
python -m pip install ttsready
```

The package depends on `ssmd` and `ssmdconvert` for canonical parsing and book loading. It does not install independent EPUB or PDF readers. Optional extras provide lexical evidence and speaker suggestions:

```bash
python -m pip install 'ttsready[lexical]'
python -m pip install 'ttsready[speakers]'
```

## Review workflow

Create a report to inspect Spokenform candidates and their SSMD source spans:

```bash
ttsready report novel.ssmdbook -c 5-17
ttsready report novel.ssmdbook --format json -o novel.report.json
```

Reports persist analysis snapshots. `context` looks up an existing cached finding and does not rerun conversion or Spokenform. Use `--refresh` on `report` to request fresh analysis:

```bash
ttsready context novel.ssmdbook chg:v1:8d1b2d540c6d995a51ac
ttsready report novel.ssmdbook -c 5 --refresh
```

An exact reviewed pronunciation can be materialized as an SSMD `sub` annotation. By default, the command writes a separate `.reviewed` artifact. Use `--write` only to explicitly replace the source:

```bash
ttsready override novel.ssmdbook chg:v1:8d1b2d540c6d995a51ac \
  --spoken 'habitat, commercial, industrial'
```

Speaker review uses logical IDs from the sidecar registry. Accepted or manual decisions can be materialized as SSMD `voice` annotations. Provider voice names remain a downstream rendering concern:

```bash
ttsready speakers novel.ssmdbook --config novel.ttsready.yaml --jev
ttsready speaker-set novel.ssmdbook --config novel.ttsready.yaml \
  --utterance utt:v1:0123456789abcdef0123 --speaker alice
ttsready speaker-materialize novel.ssmdbook --config novel.ttsready.yaml \
  --utterance utt:v1:0123456789abcdef0123
```

## Reproducibility and output

Create and verify a strict lock for canonical content, runtime, normalization profile, and prepared output. `freeze` writes a separate SSMD artifact with the selected automatic transformations materialized:

```bash
ttsready lock novel.ssmdbook
ttsready verify novel.ssmdbook novel.ssmdbook.ttsready.lock.json
ttsready freeze novel.ssmdbook -o novel.frozen.ssmdbook
```

`preview` prints prepared speech. `export` writes plain TXT from the same structured TTS plan. TXT applies speech substitutions but cannot preserve SSMD-only structure such as logical voice annotations:

```bash
ttsready preview novel.ssmdbook -c 5
ttsready export novel.ssmdbook --format txt --layout chapters -o novel-txt/
```

Use `ttsready --help` and command-specific `--help` for the complete CLI options.

## Python API

```python
from ttsready import load, prepare_tts_plan, render_preview

canonical = load("novel.ssmdbook")
plan = prepare_tts_plan(canonical, language="en")
preview = render_preview(plan)
```

For SSMD text already held in memory, use `load_ssmd()`:

```python
from ttsready import load_ssmd

document = load_ssmd(ssmd_text, section_id="chapter-0001")
```

`prepare_tts_plan()` returns structured segments and a report without rendering audio. `render_preview()` renders that plan as plain text. The report, preview, and TXT export share the same preparation result.

## Ownership boundary

- `ssmdconvert` converts supported source formats to canonical SSMD and owns `.ssmdbook` loading, validation, and writes.
- `ttsready` reviews canonical SSMD and writes explicit reviewed semantics such as `sub` and logical `voice` annotations into SSMD.
- Downstream tools consume canonical or reviewed SSMD. Tools exchange content through SSMD documents, not through a `ttsready` runtime integration API.
- The existing `ssmdconvert.speech` API remains available for compatibility. It is separate from the `ttsready` review and materialization workflow.
