"""Provider contract for bounded speaker attribution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..models import ContextRecord
from .models import SpeakerCandidate, SpeakerDecision, Utterance


class SpeakerAttributionProvider(Protocol):
    """Choose a speaker from the supplied logical candidates or return unknown."""

    name: str

    def attribute(
        self,
        utterance: Utterance,
        *,
        candidates: Sequence[SpeakerCandidate],
        context: Sequence[ContextRecord],
    ) -> SpeakerDecision: ...
