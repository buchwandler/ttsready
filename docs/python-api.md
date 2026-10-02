# Python API

The supported API is the surface exported by `ttsready.__all__`. The main preparation flow loads canonical input, builds a structured TTS plan, and renders a plain-text preview:

```python
from ttsready import load, prepare_tts_plan, render_preview

document = load("novel.ssmdbook")
plan = prepare_tts_plan(document, language="en")
preview = render_preview(plan)
```

For SSMD content already in memory, use `load_ssmd(text, section_id=...)`. `prepare_tts_plan()` returns structured segments and a report; it does not render audio. `render_preview()` returns text prepared from that plan.

Other exported operations include `convert`, `prepare`, `source_paragraphs`, and `parse_section_range`. Exported data types include `Document`, `Section`, `TTSPlan`, `PreparedSegment`, `RenderOptions`, `ConversionResult`, `ConversionReport`, and related context/statistics types. See the package's `__all__` for the complete exported-name list. Internal modules are not a promise of public API stability.
