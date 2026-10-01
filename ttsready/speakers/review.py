"""Extract utterances, collect bounded suggestions, and persist reviewed decisions."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path

from ..identifiers import speaker_decision_id, utterance_id
from ..models import ContextRecord
from ..sidecar import Sidecar, save_sidecar
from .models import (
    SpeakerCandidate,
    SpeakerDecision,
    SpeakerDecisionStatus,
    SpeakerReview,
    Utterance,
)
from .protocol import SpeakerAttributionProvider

_QUOTE_PAIRS = {
    '"': '"',
    "“": "”",
    "‘": "’",
    "«": "»",
    "„": "“",
    "‹": "›",
}


def speakers_from_sidecar(sidecar: Sidecar) -> tuple[SpeakerCandidate, ...]:
    return tuple(
        SpeakerCandidate(
            id=character["id"],
            display_name=character["display_name"],
            aliases=tuple(character.get("aliases", ())),
        )
        for character in sidecar.characters
    )


def extract_utterances(contexts: Sequence[ContextRecord]) -> tuple[Utterance, ...]:
    """Extract paired quoted spans without replacing source offsets with sentence numbers."""
    utterances: list[tuple[int, Utterance]] = []
    for context_index, context in enumerate(contexts):
        stack: list[tuple[str, int]] = []
        for position, character in enumerate(context.source_text):
            if character == '"' and position > 0 and context.source_text[position - 1] == chr(92):
                continue
            if stack and character == stack[-1][0]:
                _, quote_start = stack.pop()
                start, end = quote_start + 1, position
                text = context.source_text[start:end]
                if text.strip():
                    utterances.append(
                        (
                            context_index,
                            Utterance(
                                id=utterance_id(
                                    context.id,
                                    source_start=start,
                                    source_end=end,
                                    source=text,
                                ),
                                context_id=context.id,
                                start=start,
                                end=end,
                                text=text,
                            ),
                        )
                    )
            elif character in _QUOTE_PAIRS:
                stack.append((_QUOTE_PAIRS[character], position))
    return tuple(
        item
        for _, item in sorted(
            utterances,
            key=lambda entry: (entry[0], entry[1].start, entry[1].end),
        )
    )


def _validate_candidates(candidates: Sequence[SpeakerCandidate]) -> set[str]:
    identifiers = [candidate.id for candidate in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Speaker candidate IDs must be unique")
    return set(identifiers)


def _decision(
    utterance_id_value: str,
    speaker_id: str | None,
    *,
    confidence: float | None,
    provider: str,
    provider_model: str | None,
    status: SpeakerDecisionStatus,
) -> SpeakerDecision:
    return SpeakerDecision(
        id=speaker_decision_id(
            utterance_id_value,
            speaker_id=speaker_id,
            provider=provider,
            provider_model=provider_model,
        ),
        utterance_id=utterance_id_value,
        speaker_id=speaker_id,
        confidence=confidence,
        provider=provider,
        provider_model=provider_model,
        status=status,
    )


def attribute_utterances(
    utterances: Sequence[Utterance],
    *,
    provider: SpeakerAttributionProvider,
    candidates: Sequence[SpeakerCandidate],
    context: Sequence[ContextRecord],
) -> tuple[SpeakerDecision, ...]:
    """Run a provider while enforcing candidate bounds and review-only status."""
    candidate_ids = _validate_candidates(candidates)
    if not provider.name:
        raise ValueError("Speaker attribution provider name must not be empty")
    decisions = []
    for utterance in utterances:
        proposed = provider.attribute(
            utterance,
            candidates=candidates,
            context=context,
        )
        if proposed.utterance_id != utterance.id:
            raise ValueError("Speaker provider returned a decision for a different utterance")
        if proposed.speaker_id is not None and proposed.speaker_id not in candidate_ids:
            raise ValueError(
                f"Speaker provider returned unknown candidate ID {proposed.speaker_id!r}"
            )
        if proposed.confidence is not None and (
            not math.isfinite(proposed.confidence) or not 0 <= proposed.confidence <= 1
        ):
            raise ValueError("Speaker provider confidence must be between 0 and 1")
        model = proposed.provider_model or getattr(provider, "model", None)
        decisions.append(
            _decision(
                utterance.id,
                proposed.speaker_id,
                confidence=proposed.confidence,
                provider=provider.name,
                provider_model=model,
                status="suggested",
            )
        )
    return tuple(decisions)


def review_speakers(
    contexts: Sequence[ContextRecord],
    *,
    candidates: Sequence[SpeakerCandidate],
    provider: SpeakerAttributionProvider | None = None,
) -> SpeakerReview:
    """Build source utterances and optional provider suggestions for human review."""
    utterances = extract_utterances(contexts)
    decisions = (
        attribute_utterances(
            utterances,
            provider=provider,
            candidates=candidates,
            context=contexts,
        )
        if provider is not None
        else ()
    )
    return SpeakerReview(utterances=utterances, decisions=decisions)



def render_speaker_review(review: SpeakerReview, *, format: str = "md") -> str:
    if format == "json":
        return json.dumps(asdict(review), ensure_ascii=False, indent=2)
    if format != "md":
        raise ValueError("Speaker review format must be 'json' or 'md'")

    decisions = {decision.utterance_id: decision for decision in review.decisions}
    lines = [
        "# Speaker review",
        "",
        "| Utterance ID | Source text | Suggested speaker | Confidence | Status |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for utterance in review.utterances:
        decision = decisions.get(utterance.id)
        if decision is None:
            speaker, confidence, status = "", "", "unreviewed"
        else:
            speaker = decision.speaker_id or "unknown"
            confidence = "" if decision.confidence is None else f"{decision.confidence:.3f}"
            status = decision.status
        text = " ".join(utterance.text.replace("|", "&#124;").splitlines())
        lines.append(
            f"| `{utterance.id}` | {text} | {speaker} | {confidence} | {status} |"
        )
    return "\n".join(lines)


def accept_speaker_suggestion(
    suggestion: SpeakerDecision,
    *,
    candidates: Sequence[SpeakerCandidate],
    speaker_id: str | None = None,
) -> SpeakerDecision:
    """Return an explicitly human-accepted suggestion, optionally corrected."""
    if suggestion.status != "suggested":
        raise ValueError("Only suggested speaker decisions can be accepted")
    selected_id = suggestion.speaker_id if speaker_id is None else speaker_id
    candidate_ids = _validate_candidates(candidates)
    if selected_id is None or selected_id not in candidate_ids:
        raise ValueError("Accepted speaker must be one of the known logical candidates")
    return _decision(
        suggestion.utterance_id,
        selected_id,
        confidence=suggestion.confidence,
        provider=suggestion.provider,
        provider_model=suggestion.provider_model,
        status="accepted",
    )


def manual_speaker_decision(
    utterance: Utterance,
    *,
    speaker_id: str,
    candidates: Sequence[SpeakerCandidate],
) -> SpeakerDecision:
    """Create an explicit manual assignment to a known logical speaker ID."""
    candidate_ids = _validate_candidates(candidates)
    if speaker_id not in candidate_ids:
        raise ValueError(f"Unknown logical speaker ID {speaker_id!r}")
    return _decision(
        utterance.id,
        speaker_id,
        confidence=None,
        provider="human",
        provider_model=None,
        status="manual",
    )


def persist_speaker_decisions(
    sidecar: Sidecar,
    decisions: Sequence[SpeakerDecision],
) -> Sidecar:
    """Add only accepted/manual logical speaker assignments to a sidecar."""
    candidate_ids = {character["id"] for character in sidecar.characters}
    annotations = {item["utterance_id"]: item for item in sidecar.speaker_annotations}
    for decision in decisions:
        if decision.status not in {"accepted", "manual"}:
            continue
        if decision.speaker_id is None or decision.speaker_id not in candidate_ids:
            raise ValueError("Persisted speaker decisions must name a registered logical speaker")
        expected_id = speaker_decision_id(
            decision.utterance_id,
            speaker_id=decision.speaker_id,
            provider=decision.provider,
            provider_model=decision.provider_model,
        )
        if decision.id != expected_id:
            raise ValueError("Speaker decision ID does not match its source decision")
        provenance = {"provider": decision.provider}
        if decision.provider_model is not None:
            provenance["model"] = decision.provider_model
        if decision.confidence is not None:
            provenance["confidence"] = decision.confidence
        annotations[decision.utterance_id] = {
            "id": decision.id,
            "utterance_id": decision.utterance_id,
            "speaker": decision.speaker_id,
            "status": decision.status,
            "provenance": provenance,
        }
    return replace(sidecar, speaker_annotations=tuple(annotations.values()))


def write_speaker_decisions(
    path: str | Path,
    sidecar: Sidecar,
    decisions: Sequence[SpeakerDecision],
) -> Sidecar:
    """Persist explicit human-reviewed decisions, leaving suggestion-only runs untouched."""
    updated = persist_speaker_decisions(sidecar, decisions)
    if updated != sidecar:
        save_sidecar(path, updated)
    return updated
