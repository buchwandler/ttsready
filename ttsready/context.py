"""Pure sentence-level context lookup for source-neutral preparation results."""

from __future__ import annotations

from .models import ChangeContext, PreparationResult, SentenceSpan, UnitContext


def _select_sentences(
    sentences: tuple[SentenceSpan, ...],
    start: int,
    end: int,
) -> tuple[SentenceSpan, ...]:
    selected = tuple(
        sentence for sentence in sentences if sentence.start < end and start < sentence.end
    )
    if selected or start != end:
        return selected
    return tuple(sentence for sentence in sentences if sentence.start <= start <= sentence.end)[:1]


def context_for_change(result: PreparationResult, change_id: str) -> ChangeContext:
    """Return context for an exact change ID; never consult a cache or filesystem."""
    change = next((item for item in result.changes if item.id == change_id), None)
    if change is None:
        raise KeyError(change_id)
    unit = next((item for item in result.units if item.unit_id == change.unit_id), None)
    if unit is None:
        raise KeyError(f"Unit {change.unit_id!r} for change {change_id!r} is missing")
    context: UnitContext = unit.context
    return ChangeContext(
        change=change,
        unit=context,
        source_sentences=_select_sentences(
            context.source_sentences, change.source_start, change.source_end
        ),
        spoken_sentences=_select_sentences(
            context.spoken_sentences, change.output_start, change.output_end
        ),
    )


__all__ = ["context_for_change"]
