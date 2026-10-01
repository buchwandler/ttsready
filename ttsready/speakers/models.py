"""Provider-neutral source utterance and speaker review models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SpeakerDecisionStatus = Literal["suggested", "accepted", "rejected", "manual"]


@dataclass(frozen=True, slots=True)
class Utterance:
    id: str
    context_id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class SpeakerCandidate:
    id: str
    display_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpeakerDecision:
    id: str
    utterance_id: str
    speaker_id: str | None
    confidence: float | None
    provider: str
    provider_model: str | None
    status: SpeakerDecisionStatus


@dataclass(frozen=True, slots=True)
class SpeakerReview:
    utterances: tuple[Utterance, ...]
    decisions: tuple[SpeakerDecision, ...]
