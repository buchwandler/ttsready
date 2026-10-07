# ttsready

`ttsready` is a source-neutral Python library for preparing caller-owned text for speech. It accepts text units with explicit language and returns spoken text, exact source-relative changes, issues, context, statistics, and reproducibility fingerprints.

The library does **not** read or write files, parse SSMD or other formats, expose a CLI, generate audio, or own a document workflow. Callers adapt their source format to `TextUnit` values and decide what to do with the returned data.

## Install

Python 3.10 or newer is required.

```bash
python -m pip install ttsready
```

The runtime dependencies are `spokenform>=0.4.6,<1` and `phrasplit>=0.3.9,<1`. Install the optional lexical extra when you need its lexical-evidence integrations:

```bash
python -m pip install 'ttsready[lexical]'
```

## Quickstart

```python
from ttsready import prepare_text

prepared = prepare_text("A young reader opened a book.", language="en-US")
print(prepared.spoken_text)

for change in prepared.changes:
    print(change.source, "→", change.replacement, change.source_start, change.source_end)
```

`prepare_text()` prepares one unit and returns a `PreparedUnit`. Use `prepare_units()` when you have multiple caller-owned units, possibly with different languages, roles, protected spans, or metadata. See [docs/quickstart.md](docs/quickstart.md) and the runnable [API example](examples/basic_prepare.py).

## Core contract

- Inputs are immutable `TextUnit` records with caller-chosen IDs, text, explicit language, optional role, protected spans, and JSON-safe metadata.
- `SpeechOverride` values express global, unit-scoped, or exact-occurrence pronunciation policy.
- Results expose exact half-open source and output spans, stable IDs, warnings and residual QA issues, sentence context, and aggregate statistics.
- JSON serialization and fingerprints are pure; persistence and storage are caller responsibilities.

```python
from ttsready import TextUnit, prepare_units

result = prepare_units(
    (
        TextUnit("chapter-1", "2 kg", "en-US", role="body"),
        TextUnit("caption-1", "Bonjour.", "fr-FR", role="caption"),
    )
)

for unit in result.units:
    print(unit.unit_id, unit.spoken_text)
```

## Documentation

- [Installation](docs/installation.md)
- [Quickstart](docs/quickstart.md)
- [Python API](docs/python-api.md)
- [Overrides](docs/overrides.md)
- [Residual QA](docs/qa.md)
- [Reproducibility and serialization](docs/reproducibility.md)
- [Ownership boundary](docs/ownership-boundary.md)
- [Migration from 0.1.x](docs/migration.md)

## Migrating from 0.1.x

Version 0.2 is a breaking, API-only release. SSMD/document APIs, the CLI, file and cache I/O, writers, planning, speaker/JEV workflows, and their application-owned models were removed. Convert or read source data in your application, pass text units to `prepare_text()` or `prepare_units()`, then persist or render results in your application. See the [migration guide](docs/migration.md).

## License

`ttsready` is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for the full text.
