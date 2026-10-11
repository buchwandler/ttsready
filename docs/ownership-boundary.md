# Ownership boundary

`ttsready` owns speech-preparation policy and source-relative results. It is an API-only transformation library, not an application pipeline.

Two APIs serve different callers: `prepare_run()` is the low-level primitive for compilers that already own linguistic and sentence analysis; `prepare_text()` and `prepare_units()` provide review-oriented preparation with overrides, context, QA, and aggregate results. They share one TTSReady-owned Spokenform adapter.

```text
caller-owned source or speech pipeline
                │
       ┌────────┴────────┐
       ▼                 ▼
prepare_run(...)   prepare_text()/prepare_units()
compiler-facing    review-oriented
       │                 │
       ▼                 ▼
PreparedRun +      PreparedUnit / PreparationResult
SourceOutputMap
```

## The caller owns

- Reading and writing files, network or database access, and serialization storage.
- Parsing SSMD, Markdown, HTML, subtitles, books, or any other source format.
- Mapping source structure and identifiers to ordered `TextUnit` values or source-relative run slices.
- Loading NLP providers, selecting models, detecting language, and segmenting mixed-language runs or sentences.
- Choosing output formats, rendering, audio generation, and application/CLI behavior.
- Persisting overrides, reports, fingerprints, locks, or review decisions.

## ttsready owns

- Direct `spokenform` integration, provider-neutral annotation conversion, generic normalization policy forwarding, and replacement validation through one internal adapter.
- Source-neutral `TextUnit`, protected-span, profile, and override models.
- Exact run-level source/output maps, change provenance, generic issues, and the existing review-oriented context, aggregate statistics, QA, and fingerprints.
- JSON-ready result conversion without performing I/O.

The boundary is deliberate: the same preparation API can be used by a command-line application, service, editor, batch converter, or test without adding those behaviors to this package. See [migration from 0.1.x](migration.md) for the breaking API change.
