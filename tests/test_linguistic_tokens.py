import pytest

from ttsready.models import LinguisticToken


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": -1, "end": 1},
        {"start": 1, "end": 1},
        {"start": 2, "end": 1},
        {"start": True, "end": 2},
        {"start": 0, "end": 1.5},
    ],
)
def test_linguistic_token_rejects_invalid_ranges(kwargs):
    with pytest.raises(ValueError):
        LinguisticToken(**kwargs)


@pytest.mark.parametrize("field", ["text", "pos", "tag", "lemma", "language"])
def test_linguistic_token_rejects_non_string_optional_fields(field):
    with pytest.raises(TypeError, match=field):
        LinguisticToken(0, 2, **{field: 42})


def test_linguistic_token_is_immutable_and_provider_neutral():
    token = LinguisticToken(0, 2, text="Dr", pos="PROPN", tag="NNP", lemma="doctor", language="en")
    assert (
        token.start,
        token.end,
        token.text,
        token.pos,
        token.tag,
        token.lemma,
        token.language,
    ) == (
        0,
        2,
        "Dr",
        "PROPN",
        "NNP",
        "doctor",
        "en",
    )
    with pytest.raises((AttributeError, TypeError)):
        token.pos = "NOUN"
