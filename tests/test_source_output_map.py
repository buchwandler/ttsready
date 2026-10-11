import pytest

from ttsready.models import SourceOutputMap


def number_map() -> SourceOutputMap:
    return SourceOutputMap(
        source_length=1,
        output_length=3,
        source_left=(0, 3),
        source_right=(3, 3),
        output_left=(0, 0, 0, 1),
        output_right=(1, 1, 1, 1),
    )


def test_identity_and_zero_length_identity_map_every_boundary_to_itself():
    source_map = SourceOutputMap.identity(5)
    assert source_map.source_length == source_map.output_length == 5
    for position in range(6):
        assert source_map.source_to_output(position) == position
        assert source_map.source_to_output(position, bias="right") == position
        assert source_map.output_to_source(position) == position
        assert source_map.output_to_source(position, bias="right") == position
    assert SourceOutputMap.identity(0).source_left == (0,)
    assert SourceOutputMap.concatenate(()) == SourceOutputMap.identity(0)


def test_map_spans_use_left_start_and_right_end_bias():
    source_map = number_map()
    assert source_map.map_source_span(0, 1) == (0, 3)
    assert source_map.map_output_span(0, 3) == (0, 1)
    assert source_map.to_dict() == {
        "source_length": 1,
        "output_length": 3,
        "source_left": [0, 3],
        "source_right": [3, 3],
        "output_left": [0, 0, 0, 1],
        "output_right": [1, 1, 1, 1],
    }


def test_map_dict_round_trip_and_boundary_arrays_are_copied():
    data = number_map().to_dict()
    source_map = SourceOutputMap.from_dict(data)
    data["source_left"][0] = 99
    assert source_map == number_map()
    assert isinstance(source_map.source_left, tuple)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_left": (0,)},
        {"source_left": (0, 4)},
        {"source_left": (1, 0)},
        {"source_left": (2, 3), "source_right": (1, 3)},
    ],
)
def test_map_rejects_malformed_boundary_arrays(overrides):
    values = {
        "source_length": 1,
        "output_length": 3,
        "source_left": (0, 3),
        "source_right": (3, 3),
        "output_left": (0, 0, 0, 1),
        "output_right": (1, 1, 1, 1),
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        SourceOutputMap(**values)


def test_map_rejects_invalid_positions_spans_and_bias():
    source_map = SourceOutputMap.identity(2)
    with pytest.raises(ValueError):
        source_map.source_to_output(3)
    with pytest.raises(ValueError):
        source_map.output_to_source(-1)
    with pytest.raises(ValueError):
        source_map.source_to_output(1, bias="middle")
    with pytest.raises(ValueError):
        source_map.map_source_span(2, 1)
    with pytest.raises(ValueError):
        source_map.map_output_span(0, 3)


def test_concatenate_preserves_exact_mapping_at_run_joins_and_all_boundaries():
    first = number_map()
    second = SourceOutputMap.identity(2)
    combined = SourceOutputMap.concatenate((first, second))

    assert combined.source_length == 3
    assert combined.output_length == 5
    assert combined.source_to_output(1, bias="left") == 3
    assert combined.source_to_output(1, bias="right") == 3
    assert combined.output_to_source(3, bias="left") == 1
    assert combined.output_to_source(3, bias="right") == 1
    for position in range(combined.source_length + 1):
        assert combined.source_to_output(position, bias="left") <= combined.source_to_output(
            position, bias="right"
        )
    for position in range(combined.output_length + 1):
        assert combined.output_to_source(position, bias="left") <= combined.output_to_source(
            position, bias="right"
        )


def test_concatenate_supports_identity_edges_empty_maps_and_three_runs():
    changed = number_map()
    identity = SourceOutputMap.identity(2)
    zero = SourceOutputMap.identity(0)
    assert SourceOutputMap.concatenate((zero, changed)) == changed
    assert SourceOutputMap.concatenate((identity, changed)).source_length == 3
    assert SourceOutputMap.concatenate((changed, identity)).output_length == 5
    three = SourceOutputMap.concatenate((identity, changed, identity))
    assert three.source_length == 5
    assert three.output_length == 7


def test_concatenate_rejects_non_map_values():
    with pytest.raises(TypeError, match="SourceOutputMap"):
        SourceOutputMap.concatenate((SourceOutputMap.identity(1), object()))


@pytest.mark.parametrize(
    "text",
    [
        "unchanged text",
        "2 kg",
        "Dr. Smith",
        "(ART)",
        "  leading and trailing  ",
        "line one\nline two\n",
        "Café 🐈",
        "Dr. Smith and 2 kg",
        "2 kg at start",
        "Text ends with 2 kg",
    ],
)
def test_prepare_run_map_matches_spokenform_at_every_forward_and_reverse_boundary(text):
    import spokenform

    from ttsready import prepare_run

    options = {
        "use_spacy": False,
        "symbol_mode": "none",
        "normalize_unicode": False,
        "normalize_whitespace": False,
        "strip_outer_whitespace": False,
        "collapse_horizontal_whitespace": False,
        "normalize_line_whitespace": False,
        "collapse_blank_lines": False,
        "generic_acronym_mode": "known_only",
        "sequence_fallback_mode": "preserve",
        "expand_abbreviations": True,
        "expand_structured": True,
        "expand_numbers": True,
        "strict": False,
        "annotations": None,
        "protected_spans": (),
        "preserve_run_boundaries": False,
    }
    raw = spokenform.prepare_language(text, language="en-US", **options)
    prepared = prepare_run(text, language="en-US")
    assert prepared.spoken_text == raw.spoken_text

    for position in range(len(text) + 1):
        for bias in ("left", "right"):
            assert prepared.source_map.source_to_output(position, bias=bias) == (
                raw.offset_map.source_to_output(position, bias=bias)
            )
    for position in range(len(prepared.spoken_text) + 1):
        for bias in ("left", "right"):
            assert prepared.source_map.output_to_source(position, bias=bias) == (
                raw.offset_map.output_to_source(position, bias=bias)
            )


@pytest.mark.parametrize(
    "offset_map",
    [
        {"source_left": (0,)},
        {"source_left": (0, 2)},
        {"source_left": (1, 0)},
        {"source_left": (1, 1), "source_right": (0, 1)},
    ],
)
def test_prepare_run_fails_closed_on_malformed_backend_maps(monkeypatch, offset_map):
    from types import SimpleNamespace

    from ttsready import prepare_run
    from ttsready.errors import MappingError

    values = {
        "source_length": 1,
        "output_length": 1,
        "source_left": (0, 1),
        "source_right": (0, 1),
        "output_left": (0, 1),
        "output_right": (0, 1),
    }
    values.update(offset_map)
    result = SimpleNamespace(
        spoken_text="x",
        source_replacements=(),
        warnings=(),
        offset_map=SimpleNamespace(**values),
    )
    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", lambda *a, **k: result)
    with pytest.raises(MappingError, match="offset_map"):
        prepare_run("x", language="en-US")


def test_concatenate_maps_replacement_at_a_run_end_and_run_start():
    from ttsready import prepare_run

    ending_run = prepare_run("2 kg", language="en-US")
    following_identity = prepare_run(" next", language="en-US")
    ending_join = SourceOutputMap.concatenate(
        (ending_run.source_map, following_identity.source_map)
    )
    source_join = len(ending_run.source_text)
    output_join = len(ending_run.spoken_text)
    assert ending_join.source_to_output(source_join, bias="left") == output_join
    assert ending_join.source_to_output(source_join, bias="right") == output_join
    assert ending_join.output_to_source(output_join, bias="right") == source_join
    assert ending_join.output_to_source(output_join, bias="left") == source_join

    preceding_identity = prepare_run("prefix ", language="en-US")
    starting_run = prepare_run("2 kg", language="en-US")
    starting_join = SourceOutputMap.concatenate(
        (preceding_identity.source_map, starting_run.source_map)
    )
    source_join = len(preceding_identity.source_text)
    output_join = len(preceding_identity.spoken_text)
    assert starting_join.source_to_output(source_join, bias="right") == output_join
    assert starting_join.source_to_output(source_join, bias="left") == output_join
    assert starting_join.output_to_source(output_join, bias="right") == source_join
    assert starting_join.output_to_source(output_join, bias="left") == source_join
