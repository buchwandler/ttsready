# Releasing ttsready

Use this checklist for a release candidate. PyPI publishing is performed by the GitHub Actions release workflow and will stop unless its verification jobs pass.

1. Confirm the exact release commit has green required CI checks, including the Python and operating-system test matrix and warning-free documentation build.
2. Install the development and documentation dependencies, then run the source, lint, formatting, test, and documentation checks:

   ```bash
   python -m pip install -e ".[dev]"
   python -m pip install -r docs/requirements.txt
   python -m compileall -q ttsready tests
   python -m ruff check .
   python -m ruff format --check .
   python -m pytest
   sphinx-build -W -b html docs docs/_build/html
   ```

3. Review and commit the release notes and any intended documentation changes.
4. Build clean distributions, check them, and verify that their versions match the intended tag:

   ```bash
   rm -rf build dist *.egg-info
   python -m build
   python -m twine check dist/*
   RELEASE_TAG=v0.1.0 python tools/check_release_artifacts.py
   ```

5. Install the wheel in a clean virtual environment from outside the checkout. Check `import ttsready`, `ttsready --version`, `ttsready --help`, and that `ttsready/py.typed` is installed.
6. Create tag `v0.1.0` on the verified commit and publish the GitHub Release. The publish workflow reruns verification, validates the release-tag version, and only then uploads the verified distributions to PyPI.
7. After the workflow completes, install `ttsready==0.1.0` in a fresh environment outside the checkout and repeat the import and CLI smoke checks.

Do not publish when any required CI, documentation, artifact, or clean-wheel check fails. Resolve the failing check and repeat the release-candidate verification before creating the tag or release.
