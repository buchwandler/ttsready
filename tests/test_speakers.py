from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from ttsready.identifiers import speaker_decision_id
from ttsready.models import ContextRecord
from ttsready.pipeline import prepare
from ttsready.readers import load
from ttsready.sidecar import Sidecar, SidecarError, load_sidecar, save_sidecar
from ttsready.speakers import (
    SpeakerCandidate,
    SpeakerDecision,
    accept_speaker_suggestion,
    attribute_utterances,
    extract_utterances,
    manual_speaker_decision,
    persist_speaker_decisions,
    review_speakers,
    write_speaker_decisions,
)
from ttsready.speakers.jev import JevSpeakerProvider


@dataclass
class FakeProvider:
    name: str = "fake"
    model: str = "fake-v1"
    speaker_id: str | None = "alice"
    confidence: float | None = 0.88

    def attribute(self, utterance, *, candidates, context):
        assert [candidate.id for candidate in candidates] == ["alice", "bob"]
        return SpeakerDecision(
            id="ignored-provider-id",
            utterance_id=utterance.id,
            speaker_id=self.speaker_id,
            confidence=self.confidence,
            provider="ignored-provider-name",
            provider_model=None,
            status="accepted",
        )


class FakeJev:
    def __init__(self, value: str = "speaker:alice") -> None:
        self.value = value
        self.choices = None
        self.state = None

    def choice(self, question, *, state, choices, model=None):
        self.choices = choices
        self.state = state
        return SimpleNamespace(value=self.value, confidence=0.91)


def _contexts(tmp_path: Path, text: str) -> tuple[ContextRecord, ...]:
    source = tmp_path / "book.txt"
    source.write_text(text, encoding="utf-8")
    report = prepare(load(source), apply_spokenform=False).report
    assert report is not None
    return tuple(report.contexts)


def _candidates() -> tuple[SpeakerCandidate, ...]:
    return (
        SpeakerCandidate("alice", "Alice", ("Al",)),
        SpeakerCandidate("bob", "Robert", ("Bob",)),
    )


def _sidecar() -> Sidecar:
    return Sidecar(
        source={"format": "text"},
        lexicon=(),
        characters=(
            {"id": "alice", "display_name": "Alice", "aliases": ["Al"]},
            {"id": "bob", "display_name": "Robert", "aliases": ["Bob"]},
        ),
        speaker_annotations=(),
    )


def test_utterances_have_exact_source_spans_and_deterministic_ids(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path, 'Narrator said “Wait, where are you?” Then "Go!"')

    utterances = extract_utterances(contexts)
    repeated = extract_utterances(contexts)

    assert [item.text for item in utterances] == ["Wait, where are you?", "Go!"]
    assert [item.id for item in utterances] == [item.id for item in repeated]
    assert all(item.id.startswith("utt:v1:") for item in utterances)
    for utterance in utterances:
        context = next(item for item in contexts if item.id == utterance.context_id)
        assert context.source_text[utterance.start : utterance.end] == utterance.text


def test_provider_decisions_are_bounded_and_remain_suggestions(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path, "“Where are you?” “Who are you?”")
    utterances = extract_utterances(contexts)
    provider = FakeProvider()

    decisions = attribute_utterances(
        utterances,
        provider=provider,
        candidates=_candidates(),
        context=contexts,
    )

    assert decisions[0].speaker_id == "alice"
    assert decisions[0].status == "suggested"
    assert decisions[0].provider == "fake"
    assert decisions[0].provider_model == "fake-v1"
    assert decisions[0].id.startswith("spk:v1:")
    assert decisions[0].confidence == 0.88

    with pytest.raises(ValueError, match="unknown candidate ID"):
        attribute_utterances(
            utterances,
            provider=FakeProvider(speaker_id="invented"),
            candidates=_candidates(),
            context=contexts,
        )


def test_jev_adapter_passes_only_logical_candidates_and_unknown(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path, "“Hello.”")
    utterance = extract_utterances(contexts)[0]
    jev = FakeJev()
    provider = JevSpeakerProvider(model="local-model", jev=jev)

    decision = provider.attribute(utterance, candidates=_candidates(), context=contexts)

    assert decision.speaker_id == "alice"
    assert decision.status == "suggested"
    assert set(jev.choices) == {"speaker:alice", "speaker:bob", "__ttsready_unknown__"}
    assert jev.state["candidate_ids"] == ["alice", "bob"]
    assert "voice" not in str(jev.state).casefold()


def test_manual_acceptance_and_suggestion_persistence_are_explicit(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path, "“Hello.” “Goodbye.”")
    utterances = extract_utterances(contexts)
    utterance = utterances[0]
    candidates = _candidates()
    suggestion = attribute_utterances(
        (utterance,),
        provider=FakeProvider(),
        candidates=candidates,
        context=contexts,
    )[0]
    sidecar = _sidecar()

    suggested = persist_speaker_decisions(sidecar, (suggestion,))
    assert suggested.speaker_annotations == ()
    path = tmp_path / "reviewed.yaml"
    assert write_speaker_decisions(path, sidecar, (suggestion,)) == sidecar
    assert not path.exists()

    accepted = accept_speaker_suggestion(
        suggestion,
        candidates=candidates,
        speaker_id="bob",
    )
    assert accepted.status == "accepted"
    assert accepted.speaker_id == "bob"
    assert accepted.id == speaker_decision_id(
        utterance.id,
        speaker_id="bob",
        provider="fake",
        provider_model="fake-v1",
    )

    manual = manual_speaker_decision(utterances[1], speaker_id="alice", candidates=candidates)
    updated = write_speaker_decisions(path, sidecar, (accepted, manual))
    loaded = load_sidecar(path, source_path=tmp_path / "book.txt", source_format="text")

    assert [item["status"] for item in loaded.speaker_annotations] == ["accepted", "manual"]
    assert [item["speaker"] for item in loaded.speaker_annotations] == ["bob", "alice"]
    assert all("voice" not in item for item in loaded.speaker_annotations)
    assert updated.speaker_annotations == loaded.speaker_annotations


def test_review_without_provider_only_extracts_utterances(tmp_path: Path) -> None:
    contexts = _contexts(tmp_path, "“Hello.”")
    review = review_speakers(contexts, candidates=_candidates())

    assert len(review.utterances) == 1
    assert review.decisions == ()


def test_candidates_can_be_loaded_from_sidecar() -> None:
    from ttsready.speakers import speakers_from_sidecar

    assert speakers_from_sidecar(_sidecar()) == _candidates()



def test_sidecar_writer_rejects_suggestions_and_tts_voice_bindings(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    sidecar = _sidecar()
    voice_bound = Sidecar(
        source=sidecar.source,
        lexicon=sidecar.lexicon,
        characters=(
            {"id": "alice", "display_name": "Alice", "aliases": [], "tts_voice": "voice-a"},
        ),
        speaker_annotations=(),
    )
    with pytest.raises(SidecarError, match="TTS voice bindings"):
        save_sidecar(path, voice_bound)

    suggested = Sidecar(
        source=sidecar.source,
        lexicon=sidecar.lexicon,
        characters=sidecar.characters,
        speaker_annotations=(
            {
                "utterance_id": "utt:v1:example",
                "speaker": "alice",
                "status": "suggested",
            },
        ),
    )
    with pytest.raises(SidecarError, match="status must be accepted or manual"):
        save_sidecar(path, suggested)
