# Residual QA

Preparation includes non-mutating residual checks and attaches findings to each `PreparedUnit.issues` and aggregate `PreparationResult.issues`. Findings identify a code, severity, unit, optional source span, text, message, and JSON-safe provenance.

Use `check_units()` to inspect caller text without preparing or rewriting it:

```python
from ttsready import TextUnit, check_units

issues = check_units((TextUnit("caption-1", "Meet at 10:30.", "en-US"),))
for issue in issues:
    print(issue.code, issue.severity, issue.text, issue.message)
```

Checks flag residual digits when number expansion is enabled, date/time-like strings, uppercase initialisms, Roman numerals, operator-heavy text, suspicious symbols, and problematic Unicode/control characters. Protected spans are excluded. These are review signals, not assertions that every match is an error; interpret them in the caller's context.

Set `strict=True` on `prepare_text()` or `prepare_units()` to raise `PreparationError` when preparation returns error-severity issues. Warnings remain available on the result and do not by themselves fail strict preparation. `check_units()` itself never changes text.
