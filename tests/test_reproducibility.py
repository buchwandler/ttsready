from dataclasses import replace

from ttsready import (
    LinguisticToken,
    OverrideScope,
    PreparationProfile,
    SpeechOverride,
    TextUnit,
    override_fingerprint,
    prepare_units,
    prepared_fingerprint,
    profile_fingerprint,
    runtime_fingerprint,
    unit_fingerprint,
)


def test_profile_and_override_fingerprints_capture_policy():
    profile = PreparationProfile()
    assert profile_fingerprint(profile) == profile_fingerprint(replace(profile))
    assert profile_fingerprint(profile) != profile_fingerprint(
        replace(profile, expand_numbers=not profile.expand_numbers)
    )

    one = SpeechOverride("ACME", "A C M E")
    two = SpeechOverride("ACME", "A C M E", scope=OverrideScope("unit", "u1"))
    assert override_fingerprint((one,)) != override_fingerprint((two,))


def test_runtime_fingerprint_selects_only_semantic_runtime_versions():
    base = {"ttsready": "test-version", "spokenform": "0.4.6", "phrasplit": "0.3.9"}
    assert runtime_fingerprint(base) == runtime_fingerprint({**base, "unrelated": "9"})
    assert runtime_fingerprint(base) != runtime_fingerprint({**base, "spokenform": "0.4.7"})


def test_unit_and_prepared_fingerprints_are_content_sensitive():
    unit = TextUnit("u1", "2 kg", "en-US")
    result = prepare_units((unit,))
    profile_hash = profile_fingerprint(PreparationProfile())
    override_hash = override_fingerprint(())
    runtime_hash = runtime_fingerprint(
        {"ttsready": "test-version", "spokenform": "0.4.6", "phrasplit": "0.3.9"}
    )
    assert unit_fingerprint(
        unit,
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    ) == unit_fingerprint(
        unit,
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    )
    assert prepared_fingerprint(result.units) == prepared_fingerprint(result.units)

    changed = prepare_units(
        (unit,),
        overrides=(SpeechOverride("kg", "kilograms", scope=OverrideScope("unit", "u1")),),
    )
    assert prepared_fingerprint(result.units) != prepared_fingerprint(changed.units)


def test_linguistic_tokens_change_unit_fingerprint_but_empty_hints_preserve_legacy_hash():
    unit = TextUnit("u1", "2 kg", "en-US")
    kwargs = {
        "profile_fingerprint": "pf",
        "override_fingerprint": "of",
        "runtime_fingerprint": "rf",
    }

    assert unit_fingerprint(unit, **kwargs) == (
        "8237afcd63fd71127ab9ba4d9ed96a58e926fee10d63137d61413e8629a65be5"
    )

    first = TextUnit(
        "u1",
        "2 kg",
        "en-US",
        linguistic_tokens=(LinguisticToken(0, 1, text="2", pos="NUM"),),
    )
    second = TextUnit(
        "u1",
        "2 kg",
        "en-US",
        linguistic_tokens=(LinguisticToken(0, 1, text="2", pos="NOUN"),),
    )

    assert unit_fingerprint(first, **kwargs) != unit_fingerprint(unit, **kwargs)
    assert unit_fingerprint(first, **kwargs) != unit_fingerprint(second, **kwargs)
