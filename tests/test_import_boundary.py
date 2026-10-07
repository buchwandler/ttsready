import subprocess
import sys


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
