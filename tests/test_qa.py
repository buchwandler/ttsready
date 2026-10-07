from types import SimpleNamespace

import pytest

from ttsready.errors import PreparationError
from ttsready.models import ProtectedSpan, TextUnit
from ttsready.preparation import prepare_text
from ttsready.qa import check_units


def test_qa_reports_residual_unicode_symbols_digits_dates_times_and_initialisms():
    text = "� € 12/31/2024 at 12:30 ABC IV 2+2 \ue000 \ufdd0"
    issues = check_units((TextUnit("u", text, "en-US"),))
    codes = {issue.code for issue in issues}

    assert "qa.replacement_character" in codes
    assert "qa.currency_symbol" in codes
    assert "qa.residual_digits" in codes
    assert "qa.date_candidate" in codes
    assert "qa.time_candidate" in codes
    assert "qa.initialism_candidate" in codes
    assert "qa.roman_numeral_candidate" in codes
    assert "qa.operator_heavy" in codes
    assert "qa.private_use" in codes
    assert "qa.noncharacter" in codes
    assert all(issue.unit_id == "u" for issue in issues)
    assert all(
        issue.source_start is None or text[issue.source_start : issue.source_end] == issue.text
        for issue in issues
    )


def test_qa_skips_protected_suspicious_characters():
    issues = check_units((TextUnit("u", "� €", "en-US", protected_spans=(ProtectedSpan(0, 1),)),))

    assert "qa.replacement_character" not in {issue.code for issue in issues}
    assert "qa.currency_symbol" in {issue.code for issue in issues}


def test_strict_preparation_fails_on_residual_error_issue(monkeypatch):
    backend_result = SimpleNamespace(spoken_text="bad �", source_replacements=(), warnings=())
    monkeypatch.setattr(
        "ttsready.preparation.spokenform.prepare_language",
        lambda *args, **kwargs: backend_result,
    )

    with pytest.raises(PreparationError, match="strict preparation failed"):
        prepare_text("bad �", language="en-US", strict=True)


def test_strict_preparation_does_not_escalate_warnings(monkeypatch):
    backend_result = SimpleNamespace(spoken_text="€", source_replacements=(), warnings=())
    monkeypatch.setattr(
        "ttsready.preparation.spokenform.prepare_language",
        lambda *args, **kwargs: backend_result,
    )

    prepared = prepare_text("€", language="en-US", strict=True)
    assert "qa.currency_symbol" in {issue.code for issue in prepared.issues}
    assert not prepared.errors
