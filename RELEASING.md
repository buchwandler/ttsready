# Releasing ttsready

Use this checklist for release candidates. The Git tag is the package-version source of truth; maintainers do not edit `pyproject.toml` to bump a release version. PyPI publishing is performed by the GitHub Actions release workflow after all verification jobs pass.

1. Commit the intended release contents and confirm the exact commit has green required CI checks, including the supported Python/OS test matrix, static typing, and warning-free documentation build.
2. Create an **annotated** tag `vX.Y.Z` for that exact commit, then build from the tagged checkout with its full Git history and tags available. `setuptools-scm` derives package metadata from the tag and generates `ttsready/_version.py`; do not commit that generated file or set a pretend SCM version.
3. Install development and documentation dependencies and run the checks:

   ```bash
   python -m pip install -e ".[dev]"
   python -m pip install -r docs/requirements.txt
   python -m compileall -q ttsready tests
   python -m ruff check .
   python -m ruff format --check .
   python -m pytest
   python -m mypy ttsready examples
   sphinx-build -W -b html docs docs/_build/html
   ```

4. Build clean distributions from the exact tagged commit and verify their versions match the tag:

   ```bash
   rm -rf build dist *.egg-info
   python -m build
   python -m twine check dist/*
   export RELEASE_TAG=vX.Y.Z
   python tools/check_release_artifacts.py
   ```

   Both wheel and sdist metadata must be exactly `X.Y.Z`. A `0+unknown` fallback is never acceptable for a release artifact.

5. Install the wheel in a clean virtual environment outside the checkout. Verify the installed distribution metadata and imported `ttsready.__version__` both equal the tag without its leading `v`; confirm the source-neutral root API imports and `ttsready/py.typed` is installed. There is no CLI entry point.
6. Publish the GitHub Release for that tag using the project's release process. The publish workflow rechecks the tag, artifacts, runtime version, and typing marker before uploading to PyPI.
7. After publishing, install the exact release in a fresh environment outside the checkout and repeat the metadata, API, and `py.typed` checks.

Do not publish if any required CI, documentation, artifact, version-equality, or clean-wheel check fails. Resolve the failing check and repeat release-candidate verification.
