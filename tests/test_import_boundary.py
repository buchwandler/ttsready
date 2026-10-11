import re
import subprocess
import sys
from pathlib import Path


def test_importing_ttsready_does_not_import_format_or_cli_packages():
    code = (
        "import sys; import ttsready; "
        "assert not {'ssmd', 'ssmdconvert', 'utterplan', 'typer'} & set(sys.modules); "
        "assert not any(name in sys.modules for name in ("
        "'ttsready.cli', 'ttsready.input', 'ttsready.output', 'ttsready.speakers')); "
        "assert not any(hasattr(ttsready, name) for name in ("
        "'main', 'preview', 'read_ssmd', 'write_ssmd', 'SpeakerConfig'))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_production_spokenform_language_preparation_has_one_owner():
    source_root = Path(__file__).resolve().parents[1] / "ttsready"
    calls = [
        path.relative_to(source_root).as_posix()
        for path in source_root.glob("*.py")
        if re.search(r"spokenform\.prepare_language\s*\(", path.read_text(encoding="utf-8"))
    ]
    assert calls == ["preparation.py"]
