from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from typer.testing import CliRunner

from ttsready.cli import app
from ttsready.context import render_context_json
from ttsready.input import load
from ttsready.lexical_review import (
    format_lexical_context,
    lexical_context_payload,
    render_review,
    review_document,
)
from ttsready.pipeline import prepare

runner = CliRunner()


@dataclass(frozen=True)
class Evidence:
    known: bool
    frequency_rank: int | None = None
    frequency_count: int | None = None


class FakeProvider:
    language = "en"
    capabilities = ("lexical",)

    def __init__(self, words: dict[str, Evidence] | None = None) -> None:
        self.words = words or {}
        self.calls: list[str] = []

    def word(self, word: str) -> Evidence:
        self.calls.append(word)
        return self.words.get(word, Evidence(True))

    def segment(self, text: str, *, max_word_length: int = 32):
        return ()

    def supports_domain(self, text: str, **kwargs):
        return None


def _source(tmp_path: Path, text: str) -> Path:
    source = tmp_path / "book.ssmd.md"
    source.write_text(
        chr(10).join(["---", 'ssmd_version: "0.9"', "language: en", "---", text, ""]),
        encoding="utf-8",
    )
    return source


def test_review_aggregates_casefolded_terms_and_keeps_context_occurrences(tmp_path: Path) -> None:
    source = _source(tmp_path, "Siobhan met SIOBHAN.\n\nsiobhan returned.")
    provider = FakeProvider({"siobhan": Evidence(False)})

    review = review_document(load(source), provider=provider)
    finding = next(item for item in review.findings if item.normalized == "siobhan")

    assert finding.count == 3
    assert finding.surface == "Siobhan"
    assert "unknown_to_lexicon" in finding.reasons
    assert len({item.context_id for item in finding.occurrences}) == 2
    assert all(item.sentence_id for item in finding.occurrences)
    assert provider.calls.count("siobhan") == 1


def test_review_ranks_unknown_proper_names_and_repeated_unknown_terms(tmp_path: Path) -> None:
    source = _source(tmp_path, "We met Siobhan. Unknownword unknownword.")
    provider = FakeProvider(
        {
            "siobhan": Evidence(False),
            "unknownword": Evidence(False),
        }
    )

    review = review_document(load(source), provider=provider)

    assert [item.normalized for item in review.findings[:2]] == [
        "siobhan",
        "unknownword",
    ]
    assert "proper_name_candidate" in review.findings[0].reasons
    assert review.findings[1].count == 2


def test_common_sentence_initial_word_is_not_flagged_as_a_name(tmp_path: Path) -> None:
    source = _source(tmp_path, "The common word is here.")
    review = review_document(load(source), provider=FakeProvider())

    assert all(item.normalized != "the" for item in review.findings)


def test_review_filters_urls_numbers_and_single_letters_but_keeps_orthographic_signals(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path,
        "iPhone NASA cafe\u0301 123 user@example.com https://example.org I",
    )
    review = review_document(load(source), provider=FakeProvider())
    findings = {item.normalized: item for item in review.findings}

    assert "iphone" in findings and "mixed_case" in findings["iphone"].reasons
    assert "nasa" in findings and "all_caps" in findings["nasa"].reasons
    assert "cafe\u0301" in findings
    assert "contains_unusual_graphemes" in findings["cafe\u0301"].reasons
    assert not {"123", "user", "example", "org", "https", "i"} & set(findings)


def test_rare_words_use_frequency_cutoff_and_repeated_terms_rank_higher(tmp_path: Path) -> None:
    source = _source(tmp_path, "geomorphology. rareword rareword.")
    provider = FakeProvider(
        {
            "geomorphology": Evidence(True, frequency_rank=48_231, frequency_count=3),
            "rareword": Evidence(True, frequency_rank=20_000, frequency_count=2),
        }
    )

    review = review_document(load(source), provider=provider, max_frequency_rank=10_000)

    assert [item.normalized for item in review.findings] == ["rareword", "geomorphology"]
    assert all("rare_word" in item.reasons for item in review.findings)
    assert review.findings[1].frequency_count == 3


def test_review_filters_and_serialization_are_deterministic(tmp_path: Path) -> None:
    source = _source(tmp_path, "We met Siobhan. Siobhan returned. geomorphology.")
    provider = FakeProvider(
        {
            "siobhan": Evidence(False),
            "geomorphology": Evidence(True, frequency_rank=48_231, frequency_count=3),
        }
    )
    first = review_document(load(source), provider=provider, min_count=2, max_items=1)
    second = review_document(load(source), provider=provider, min_count=2, max_items=1)

    assert first == second
    assert [item.normalized for item in first.findings] == ["siobhan"]
    assert render_review(first, "json") == render_review(second, "json")
    assert "Uncommon word candidates" in render_review(first, "md")


def test_lexical_context_resolves_finding_and_preserves_sentence_and_paragraph(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, "We met Siobhan after lunch.")
    provider = FakeProvider({"siobhan": Evidence(False)})
    review = review_document(load(source), provider=provider)
    finding = next(item for item in review.findings if item.normalized == "siobhan")
    conversion = prepare(load(source), apply_spokenform=False).report
    assert conversion is not None

    payload = lexical_context_payload(conversion, finding.id, paragraph=True)
    occurrence = payload["occurrences"][0]

    assert occurrence["sentence_text"] == "We met Siobhan after lunch."
    assert occurrence["paragraph_text"] == "We met Siobhan after lunch."
    assert "We met Siobhan after lunch." in format_lexical_context(payload)
    assert json.loads(render_context_json(payload))["lexical_finding"]["id"] == finding.id


def test_review_cli_outputs_json_and_context_accepts_lexical_id(
    tmp_path: Path, monkeypatch
) -> None:
    source = _source(tmp_path, "We met Siobhan after lunch.")
    monkeypatch.setenv("TTSREADY_CACHE_DIR", str(tmp_path / "cache"))
    cached = runner.invoke(app, ["report", str(source), "--no-titles"])
    assert cached.exit_code == 0, cached.output
    reviewed = runner.invoke(app, ["review", str(source), "--format", "json"])

    assert reviewed.exit_code == 0, reviewed.output
    report = json.loads(reviewed.output)
    finding = next(item for item in report["findings"] if item["normalized"] == "siobhan")
    context = runner.invoke(app, ["context", str(source), finding["id"]])

    assert context.exit_code == 0, context.output
    assert "Lexical finding:" in context.output
    assert "We met Siobhan after lunch." in context.output


def test_lexhint_is_only_loaded_when_explicitly_requested(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path, "We met Siobhan.")
    calls = []

    def load_provider(language, *, variant, dataset_version):
        calls.append((language, variant, dataset_version))
        return FakeProvider({"siobhan": Evidence(False)})

    monkeypatch.setattr("ttsready.cli._load_lexhint", load_provider)
    default = runner.invoke(app, ["review", str(source), "--format", "json"])
    assert default.exit_code == 0, default.output
    assert calls == []

    explicit = runner.invoke(
        app,
        [
            "review",
            str(source),
            "--lexhint",
            "--lexhint-variant",
            "small",
            "--lexhint-dataset-version",
            "v2",
            "--format",
            "json",
        ],
    )

    assert explicit.exit_code == 0, explicit.output
    assert calls == [("en", "small", "v2")]
    assert "unknown_to_lexicon" in explicit.output
