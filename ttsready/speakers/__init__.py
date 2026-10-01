"""Provider-neutral source speaker review."""

from .jev import JevSpeakerProvider
from .models import (
    SpeakerCandidate,
    SpeakerDecision,
    SpeakerDecisionStatus,
    SpeakerReview,
    Utterance,
)
from .protocol import SpeakerAttributionProvider
from .review import (
    accept_speaker_suggestion,
    attribute_utterances,
    extract_utterances,
    manual_speaker_decision,
    persist_speaker_decisions,
    render_speaker_review,
    review_speakers,
    speakers_from_sidecar,
    write_speaker_decisions,
)

__all__ = [
    "SpeakerAttributionProvider",
    "JevSpeakerProvider",
    "SpeakerCandidate",
    "SpeakerDecision",
    "SpeakerDecisionStatus",
    "SpeakerReview",
    "Utterance",
    "accept_speaker_suggestion",
    "attribute_utterances",
    "extract_utterances",
    "manual_speaker_decision",
    "persist_speaker_decisions",
    "render_speaker_review",
    "review_speakers",
    "speakers_from_sidecar",
    "write_speaker_decisions",
]
