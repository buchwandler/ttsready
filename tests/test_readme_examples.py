from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "examples" / "basic.ssmd.md"
PYTHON_EXAMPLE = ROOT / "examples" / "basic_preview.py"


def test_python_api_example_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(PYTHON_EXAMPLE)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "A young reader opened a book.\nShe found a quiet story.\n"


def test_quickstart_cli_commands_run(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["TTSREADY_CACHE_DIR"] = str(tmp_path / "cache")
    export_path = tmp_path / "basic.txt"
    lock_path = tmp_path / "basic.lock.json"
    commands = [
        ["preflight", str(SOURCE)],
        ["report", str(SOURCE)],
        ["preview", str(SOURCE)],
        ["lock", str(SOURCE), "-o", str(lock_path)],
        ["verify", str(SOURCE), "--lock", str(lock_path)],
        ["export", str(SOURCE), "--format", "txt", "-o", str(export_path)],
    ]

    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "ttsready", *command],
            cwd=ROOT,
            capture_output=True,
            check=False,
            env=env,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    assert export_path.read_text(encoding="utf-8") == (
        "A young reader opened a book.\nShe found a quiet story.\n"
    )
