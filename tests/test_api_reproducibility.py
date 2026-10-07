from ttsready import (
    PreparationProfile,
    ProtectedSpan,
    SpeechOverride,
    TextUnit,
    override_fingerprint,
    prepare_units,
    prepared_fingerprint,
    profile_fingerprint,
    runtime_fingerprint,
    runtime_versions,
    unit_fingerprint,
)


def test_profile_and_override_fingerprints_are_deterministic():
    profile = PreparationProfile()
    override = SpeechOverride("ART", "A R T")

    assert profile_fingerprint(profile) == profile_fingerprint(profile)
    assert override_fingerprint((override,)) == override_fingerprint((override,))
    assert override_fingerprint((override,)) != override_fingerprint(
        (SpeechOverride("ART", "art"),)
    )


def test_unit_fingerprint_tracks_content_language_spans_and_policies():
    profile_hash = profile_fingerprint(PreparationProfile())
    override_hash = override_fingerprint(())
    runtime_hash = runtime_fingerprint()
    unit = TextUnit("u", "1 kg", "en-US")

    base = unit_fingerprint(
        unit,
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    )
    assert base == unit_fingerprint(
        unit,
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    )
    assert base != unit_fingerprint(
        TextUnit("u", "1 kg", "fr-FR"),
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    )
    assert base != unit_fingerprint(
        TextUnit("u", "1 kg", "en-US", protected_spans=(ProtectedSpan(0, 1),)),
        profile_fingerprint=profile_hash,
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    )
    assert base != unit_fingerprint(
        unit,
        profile_fingerprint=profile_fingerprint(PreparationProfile(expand_numbers=False)),
        override_fingerprint=override_hash,
        runtime_fingerprint=runtime_hash,
    )


def test_runtime_fingerprint_uses_semantic_runtime_and_prepared_digest_is_ordered():
    versions = runtime_versions()
    assert set(versions) == {"ttsready", "spokenform", "phrasplit"}
    assert runtime_fingerprint(versions) == runtime_fingerprint(versions)

    first = prepare_units((TextUnit("a", "2 kg", "en-US"), TextUnit("b", "3 kg", "en-US")))
    assert prepared_fingerprint(first.units) != prepared_fingerprint(tuple(reversed(first.units)))
    changed = prepare_units((TextUnit("a", "3 kg", "en-US"), TextUnit("b", "2 kg", "en-US")))
    assert prepared_fingerprint(first.units) != prepared_fingerprint(changed.units)
