from dataclasses import replace

from ttsready import (
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
    base = {"ttsready": "0.2.0", "spokenform": "0.4.6", "phrasplit": "0.3.9"}
    assert runtime_fingerprint(base) == runtime_fingerprint({**base, "unrelated": "9"})
    assert runtime_fingerprint(base) != runtime_fingerprint({**base, "spokenform": "0.4.7"})


def test_unit_and_prepared_fingerprints_are_content_sensitive():
    unit = TextUnit("u1", "2 kg", "en-US")
    result = prepare_units((unit,))
    profile_hash = profile_fingerprint(PreparationProfile())
    override_hash = override_fingerprint(())
    runtime_hash = runtime_fingerprint(
        {"ttsready": "0.2.0", "spokenform": "0.4.6", "phrasplit": "0.3.9"}
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
