# Quickstart

From the repository root, install the package and run the commands against the included valid SSMD fixture:

```bash
python -m pip install -e .
ttsready preflight examples/basic.ssmd.md
ttsready report examples/basic.ssmd.md
ttsready preview examples/basic.ssmd.md
ttsready export examples/basic.ssmd.md --format txt -o /tmp/basic.txt
```

`preflight` validates and prepares without writing output. `report` stores a review report. `preview` prints the prepared speech, while `export` writes plain text. These commands do not generate audio.

The same input can be loaded through the Python API:

```python
from pathlib import Path

from ttsready import load, prepare_tts_plan, render_preview

document = load(Path("examples/basic.ssmd.md"))
plan = prepare_tts_plan(document, language="en")
print(render_preview(plan))
```

For input conversion, first create canonical SSMD or an `.ssmdbook` with `ssmdconvert`. See [supported CLI commands](cli.md) and the [review workflow](review-workflow.md) for what to do with report findings.
