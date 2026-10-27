import email
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def test_runtime_metadata_has_no_removed_dependencies_or_console_script():
    project_root = Path(__file__).resolve().parents[1]
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    project = pyproject.split("[project]", 1)[1].split("[project.optional-dependencies]", 1)[0]
    dependencies = re.search(r"dependencies\s*=\s*\[(.*?)\]", project, re.DOTALL)
    assert dependencies is not None
    runtime_dependencies = dependencies.group(1).lower()

    for removed in ("ssmd", "ssmdconvert", "utterplan", "pyyaml", "typer", "pyjev"):
        assert not re.search(rf"[\"']{removed}(?:[<>=!~]|[\"'])", runtime_dependencies)
    assert '"spokenform>=0.4.6,<0.5"' in runtime_dependencies
    assert '"phrasplit>=0.3.9,<1"' in runtime_dependencies
    assert "[project.scripts]" not in pyproject
    assert '"lexhint>=' in pyproject


def test_setuptools_scm_configuration_is_dynamic_and_uses_neutral_fallback():
    project_root = Path(__file__).resolve().parents[1]
    configuration = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" in configuration["project"]["dynamic"]
    assert "version" not in configuration["project"]
    assert "setuptools-scm[toml]>=8" in configuration["build-system"]["requires"]
    assert configuration["tool"]["setuptools_scm"]["version_file"] == "ttsready/_version.py"
    assert configuration["tool"]["setuptools_scm"]["fallback_version"] == "0+unknown"


def test_bare_source_without_generated_version_uses_neutral_fallback(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    bare_source = tmp_path / "bare-source"
    shutil.copytree(
        project_root / "ttsready",
        bare_source / "ttsready",
        ignore=shutil.ignore_patterns("_version.py", "__pycache__"),
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(bare_source)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['ttsready._version'] = None; "
            "import ttsready; assert ttsready.__version__ == '0+unknown'",
        ],
        check=False,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_built_wheel_version_matches_metadata_and_imported_distribution(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheel_dir),
            str(project_root),
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    wheels = tuple(wheel_dir.glob("ttsready-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        assert "ttsready/preparation.py" in names
        for removed_module in (
            "__main__",
            "analysis",
            "cli",
            "input",
            "materialization",
            "output",
            "pipeline",
            "planning",
            "reporting",
            "selection",
            "sidecar",
            "writers",
        ):
            assert f"ttsready/{removed_module}.py" not in names
        assert not any(name.startswith("ttsready/speakers/") for name in names)
        assert "ttsready/py.typed" in names
        assert not any(name.endswith("entry_points.txt") for name in names)
        metadata_path = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_path))
        metadata_version = metadata["Version"]
        assert metadata_version

        requirements = metadata.get_all("Requires-Dist") or []
        assert any("spokenform" in item.lower() and ">=0.4.6" in item for item in requirements)
        assert any("phrasplit" in item.lower() and ">=0.3.9" in item for item in requirements)
        assert "lexical" in (metadata.get_all("Provides-Extra") or [])

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(wheels[0])
    environment["EXPECTED_VERSION"] = metadata_version
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; from importlib.metadata import version; import ttsready; "
            "expected = os.environ['EXPECTED_VERSION']; "
            "assert ttsready.__version__ == expected, (ttsready.__version__, expected); "
            "assert version('ttsready') == expected; "
            "assert not {'ssmd', 'ssmdconvert', 'utterplan', 'typer'} & set(sys.modules)",
        ],
        check=False,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
