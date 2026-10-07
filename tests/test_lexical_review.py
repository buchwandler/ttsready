from dataclasses import dataclass

from ttsready.lexical_review import review_lexicon
from ttsready.models import TextUnit
from ttsready.preparation import prepare_units


@dataclass(frozen=True)
class Evidence:
    known: bool
    frequency_rank: int | None = None
    frequency_count: int | None = None


class FakeProvider:
    language = "en"
    capabilities = ("lexical",)

    def __init__(self, words=None):
        self.words = words or {}
        self.calls = []

    def word(self, word):
        self.calls.append(word)
        return self.words.get(word, Evidence(True))

    def segment(self, text, *, max_word_length=32):
        return ()

    def supports_domain(self, text, **kwargs):
        return None


def test_review_aggregates_terms_across_units_and_keeps_unit_relative_occurrences():
    provider = FakeProvider({"siobhan": Evidence(False)})
    result = review_lexicon(
        (
            TextUnit("unit-a", "We met Siobhan. Unknownword unknownword.", "en"),
            TextUnit("unit-b", "SIOBHAN returned.", "en"),
        ),
        provider=provider,
    )
    finding = next(item for item in result.findings if item.normalized == "siobhan")

    assert finding.count == 2
    assert finding.surface == "Siobhan"
    assert "unknown_to_lexicon" in finding.reasons
    assert {item.unit_id for item in finding.occurrences} == {"unit-a", "unit-b"}
    assert all(item.start >= 0 and item.end > item.start for item in finding.occurrences)
    assert provider.calls.count("siobhan") == 1


def test_review_finds_orthographic_signals_and_filters_urls_numbers_and_single_letters():
    unit = TextUnit(
        "u",
        "iPhone NASA cafe\u0301 123 user@example.com https://example.org I",
        "en",
    )
    findings = {item.normalized: item for item in review_lexicon((unit,)).findings}

    assert "iphone" in findings and "mixed_case" in findings["iphone"].reasons
    assert "nasa" in findings and "all_caps" in findings["nasa"].reasons
    assert "cafe\u0301" in findings
    assert "contains_unusual_graphemes" in findings["cafe\u0301"].reasons
    assert not {"123", "user", "example", "org", "https", "i"} & set(findings)


def test_review_accepts_preparation_results_and_honors_filters_and_order():
    provider = FakeProvider(
        {
            "geomorphology": Evidence(True, frequency_rank=48_231, frequency_count=3),
            "rareword": Evidence(True, frequency_rank=20_000, frequency_count=2),
        }
    )
    result = prepare_units((TextUnit("u", "geomorphology. rareword rareword.", "en"),))

    review = review_lexicon(result, provider=provider, max_frequency_rank=10_000)
    assert [item.normalized for item in review.findings] == ["rareword", "geomorphology"]
    assert all("rare_word" in item.reasons for item in review.findings)
    assert review.findings[1].frequency_count == 3
    assert review.units_reviewed == 1

    filtered = review_lexicon(result, provider=provider, min_count=2, max_items=1)
    assert [item.normalized for item in filtered.findings] == ["rareword"]


def test_unknown_only_requires_evidence_and_result_is_deterministic():
    unit = TextUnit("u", "We met Siobhan. Siobhan returned.", "en")
    provider = FakeProvider({"siobhan": Evidence(False)})
    first = review_lexicon((unit,), provider=provider)
    second = review_lexicon((unit,), provider=provider)

    assert first == second
    assert [item.normalized for item in review_lexicon((unit,), unknown_only=True).findings] == []
    assert [
        item.normalized
        for item in review_lexicon((unit,), provider=provider, unknown_only=True).findings
    ] == ["siobhan"]


def test_protected_terms_are_not_reviewed():
    unit = TextUnit("u", "Siobhan and Siobhan", "en", protected_spans=((0, 7), (12, 19)))
    result = review_lexicon((unit,), include_all_tokens=True)

    assert all(item.normalized != "siobhan" for item in result.findings)
