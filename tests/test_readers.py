from __future__ import annotations

from pathlib import Path

import pytest

from ttsready.errors import UnsupportedInputError
from ttsready.input import load


@pytest.mark.parametrize("suffix", [".txt", ".text", ".md", ".html", ".epub", ".pdf"])
def test_load_rejects_noncanonical_sources(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"input{suffix}"
    source.write_text("Raw source text", encoding="utf-8")

    with pytest.raises(UnsupportedInputError, match="accepts standalone"):
        load(source)


def test_package_depends_on_ssmd_ingestion_not_raw_format_readers() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    dependencies = pyproject.read_text(encoding="utf-8").partition("dependencies = [")[2]
    dependencies = dependencies.partition("]")[0]

    assert '"ssmd>=' in dependencies
    assert '"ssmdconvert>=' in dependencies
    assert "epub2text" not in dependencies
    assert "pypdf" not in dependencies
