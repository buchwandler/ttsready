# Installation

`ttsready` requires Python 3.10 or newer. Install the package from PyPI:

```bash
python -m pip install ttsready
```

Optional extras provide lexical evidence and speaker suggestions:

```bash
python -m pip install 'ttsready[lexical]'
python -m pip install 'ttsready[speakers]'
```

The core package uses `ssmd` to parse canonical SSMD and `ssmdconvert` to load and write `.ssmdbook` bundles. It does not install EPUB or PDF readers. Convert source formats to SSMD with `ssmdconvert` before using `ttsready`.

See the [quickstart](quickstart.md) to check an example document, or the [CLI reference](cli.md) for command summaries.
