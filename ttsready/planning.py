"""Render a prepared TTS plan without performing analysis or normalization."""

from __future__ import annotations

from .models import RenderOptions, TTSPlan
from .writers import render_txt


def render_preview(plan: TTSPlan, *, options: RenderOptions | None = None) -> str:
    """Render clean speech text from an already prepared plan."""
    return render_txt(plan.segments, options=options)
