# Migration from 0.1.x

Version 0.2 is a breaking release that narrows `ttsready` to a source-neutral preparation API. It does not preserve 0.1 application behavior behind compatibility wrappers.

## Removed ownership

The following 0.1 areas are no longer part of `ttsready`:

- SSMD and document/book parsing, source-specific models, file readers, and writers.
- CLI commands, reporting workflows, caches, sidecars, planning, selection, and freeze/materialization.
- Speaker/JEV scanning, registries, and speaker annotation workflows.
- File-based locks, exports, and document-owned reproducibility operations.

Callers now own source parsing and I/O, output formats, workflow state, and persistence. The library accepts only caller-owned text data and returns in-memory values.

## Replace the 0.1 preparation flow

A file- or document-oriented call such as `load(...)`, `load_ssmd(...)`, `prepare_tts_plan(...)`, or a CLI command must be moved to the caller's adapter. Pass the text and language directly to the library:

```python
from ttsready import TextUnit, prepare_text, prepare_units

# One text unit:
prepared = prepare_text(source_text, language="en-US", unit_id="chapter-1")
print(prepared.spoken_text)

# Or an ordered set with per-unit language:
result = prepare_units(
    (
        TextUnit("chapter-1", source_text, "en-US", role="body"),
        TextUnit("caption-1", caption_text, "fr-FR", role="caption"),
    )
)
```

`prepare_text()` returns a `PreparedUnit`; `prepare_units()` returns a `PreparationResult`. Both expose exact source-relative changes, issues, and contexts. `apply_changes()` verifies and applies a change set to the exact source string supplied by the caller.

If the application reads or writes a file, keep that code outside `ttsready`. If it parses a format, convert relevant regions into `TextUnit` values and retain the mapping back to the caller's source model.

## Policy and state

Replace document annotations with caller-owned `SpeechOverride` values. Use global, unit, or occurrence scopes as appropriate; see [overrides](overrides.md). Use `check_units()` and the issues attached to preparation results for residual QA. Use pure fingerprints and JSON serialization when building caller-owned records; `ttsready` no longer maintains caches, lock files, or persistent review state.

## Dependency and packaging changes

The 0.2 runtime dependencies are `spokenform>=0.4.6,<1` and `phrasplit>=0.3.9,<1`. SSMD/SSMDConvert, CLI, PyYAML, Utterplan, and PyJEV are no longer runtime dependencies. The CLI and speaker extras were removed; `ttsready[lexical]` remains optional.

Update imports to the source-neutral exports in `ttsready.__all__`, and pin the new major API boundary before upgrading. See [Python API](python-api.md), [ownership boundary](ownership-boundary.md), and [reproducibility](reproducibility.md).
