import pytest

from ttsready.preparation import split_prepared_text


def test_sentence_aware_chunks_are_exact_source_slices():
    text = "First sentence. This is a rather long sentence that needs splitting. Final."
    chunks = split_prepared_text(text, language="en", max_chars=24)

    assert len(chunks) > 3
    assert "".join(chunk.text for chunk in chunks) == text
    assert [chunk.part for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text
        assert chunk.end - chunk.start <= 24


def test_chunker_handles_empty_text_and_rejects_invalid_size():
    assert split_prepared_text("", language="en", max_chars=10) == ()
    with pytest.raises(ValueError, match="at least 1"):
        split_prepared_text("text", language="en", max_chars=0)
