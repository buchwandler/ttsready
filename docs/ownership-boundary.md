# Ownership boundary

`ttsready` owns speech-preparation policy and source-relative results. It is an API-only transformation library, not an application pipeline.

```text
caller-owned source or format adapter
                │
                ▼
       TextUnit / prepare_text
                │
                ▼
 PreparedUnit / PreparationResult
                │
                ▼
caller-owned review, persistence, and output
```

## The caller owns

- Reading and writing files, network or database access, and serialization storage.
- Parsing SSMD, Markdown, HTML, subtitles, books, or any other source format.
- Mapping source structure and identifiers to ordered `TextUnit` values.
- Choosing output formats, rendering, audio generation, and application/CLI behavior.
- Persisting overrides, reports, fingerprints, locks, or review decisions.

## ttsready owns

- Preparation of text with an explicit language through `spokenform`.
- Source-neutral `TextUnit`, protected-span, profile, and override models.
- Exact source/output mapping, issues, sentence context, aggregate statistics, QA, and fingerprints.
- JSON-ready result conversion without performing I/O.

The boundary is deliberate: the same preparation API can be used by a command-line application, service, editor, batch converter, or test without adding those behaviors to this package. See [migration from 0.1.x](migration.md) for the breaking API change.
