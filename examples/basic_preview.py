from pathlib import Path

from ttsready import load, prepare_tts_plan, render_preview

document = load(Path(__file__).with_name("basic.ssmd.md"))
plan = prepare_tts_plan(document, language="en")
print(render_preview(plan), end="")
