from __future__ import annotations

from ttsready.identifiers import change_id, context_id, section_locator, stable_id
from ttsready.models import Section


def test_stable_id_is_deterministic_for_unicode_payloads() -> None:
    payload = {"source": "café 🗣️", "span": [4, 9]}

    assert stable_id("chg", payload) == stable_id("chg", payload)
    assert stable_id("chg", payload).startswith("chg:v1:")


def test_change_id_uses_only_context_and_source_span() -> None:
    same_occurrence = {
        "context_id": "ctx:v1:0123456789abcdefabcd",
        "source_start": 4,
        "source_end": 8,
        "source": "H2O",
    }
    original = change_id(**same_occurrence)
    later_interpretation = change_id(**same_occurrence)

    assert original == later_interpretation
    assert change_id(**{**same_occurrence, "source_start": 5}) != original
    assert change_id(**{**same_occurrence, "source": "H₂O"}) != original


def test_context_id_uses_source_reference_and_duplicate_ordinal() -> None:
    section = Section("nav:7:volatile", "", source_ref="chapter.xhtml#body")

    first = context_id(
        section,
        kind="paragraph",
        source_text="Repeated passage.",
        duplicate_ordinal=0,
    )
    duplicate = context_id(
        section,
        kind="paragraph",
        source_text="Repeated passage.",
        duplicate_ordinal=1,
    )

    assert section_locator(section) == "ref:chapter.xhtml#body"
    assert first != duplicate
    assert first.startswith("ctx:v1:")


def test_section_locator_falls_back_to_section_id() -> None:
    assert section_locator(Section("section-1", "text")) == "id:section-1"
