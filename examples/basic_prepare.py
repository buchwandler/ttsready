"""Minimal source-neutral ttsready example."""

from ttsready import prepare_text

prepared = prepare_text("A young reader opened a book.", language="en-US")
print(prepared.spoken_text)
