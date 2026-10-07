# Installation

`ttsready` 0.2 requires Python 3.10 or newer. Install it with pip:

```bash
python -m pip install ttsready
```

The library's runtime dependencies are `spokenform>=0.4.5,<1` and `phrasplit>=0.3.9,<1`. The package does not install format parsers, file readers, a CLI framework, or an audio renderer.

Install the optional `lexical` extra when using integrations that need the `lexhint` lexical-evidence package:

```bash
python -m pip install 'ttsready[lexical]'
```

For development, install the development tools and tests:

```bash
python -m pip install 'ttsready[dev]'
```

Continue with the [quickstart](quickstart.md) or the full [Python API reference](python-api.md).
