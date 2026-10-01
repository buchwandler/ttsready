"""Optional pyjev-backed bounded speaker choice provider."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from ..identifiers import speaker_decision_id
from ..models import ContextRecord
from .models import SpeakerCandidate, SpeakerDecision, Utterance

_UNKNOWN_LABEL = "__ttsready_unknown__"
_QUESTION = "Which known speaker, if any, said this quoted utterance?"


class _JevLike(Protocol):
    def choice(
        self,
        question: str,
        *,
        state: Mapping[str, Any],
        choices: Mapping[str, Any],
        model: str | None = None,
    ) -> Any: ...


class JevSpeakerProvider:
    """Use Jev to choose only among the supplied logical speaker candidates."""

    name = "jev"

    def __init__(self, *, model: str | None = None, jev: _JevLike | None = None) -> None:
        self.model = model
        self._jev = jev
        self._owns_jev = False

    @property
    def jev(self) -> _JevLike:
        if self._jev is None:
            try:
                from pyjev import Jev
            except ImportError as exc:
                raise RuntimeError(
                    "Jev speaker attribution requires the ttsready[speakers] extra"
                ) from exc
            self._jev = Jev(model=self.model)
            self._owns_jev = True
        return self._jev

    def close(self) -> None:
        if self._owns_jev and self._jev is not None:
            close = getattr(self._jev, "close", None)
            if callable(close):
                close()
            self._jev = None
            self._owns_jev = False

    def __enter__(self) -> JevSpeakerProvider:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def attribute(
        self,
        utterance: Utterance,
        *,
        candidates: Sequence[SpeakerCandidate],
        context: Sequence[ContextRecord],
    ) -> SpeakerDecision:
        labels: dict[str, str | None] = {}
        choices: dict[str, str] = {}
        for candidate in candidates:
            label = f"speaker:{candidate.id}"
            labels[label] = candidate.id
            aliases = ", ".join(candidate.aliases) or "none"
            choices[label] = (
                f"{candidate.display_name} (logical ID {candidate.id}; aliases: {aliases})"
            )
        labels[_UNKNOWN_LABEL] = None
        choices[_UNKNOWN_LABEL] = "Unknown or not one of the listed logical speakers."

        context_items = list(context)
        context_index = next(
            (index for index, item in enumerate(context_items) if item.id == utterance.context_id),
            None,
        )
        nearby = []
        if context_index is not None:
            start = max(0, context_index - 1)
            end = min(len(context_items), context_index + 2)
            nearby = [
                {
                    "section": item.section_locator,
                    "source": item.source_text,
                }
                for item in context_items[start:end]
            ]
        state = {
            "utterance": utterance.text,
            "source_span": [utterance.start, utterance.end],
            "nearby_source_context": nearby,
            "candidate_ids": [candidate.id for candidate in candidates],
            "instruction": "Choose only a listed speaker or unknown. Do not invent speaker IDs.",
        }
        result = self.jev.choice(
            _QUESTION,
            state=state,
            choices=choices,
            model=self.model,
        )
        selected = str(result.value)
        if selected not in labels:
            raise ValueError(f"Jev returned a choice outside the supplied candidates: {selected!r}")
        speaker_id = labels[selected]
        confidence_value = getattr(result, "confidence", None)
        confidence = None if confidence_value is None else float(confidence_value)
        return SpeakerDecision(
            id=speaker_decision_id(
                utterance.id,
                speaker_id=speaker_id,
                provider=self.name,
                provider_model=self.model,
            ),
            utterance_id=utterance.id,
            speaker_id=speaker_id,
            confidence=confidence,
            provider=self.name,
            provider_model=self.model,
            status="suggested",
        )
