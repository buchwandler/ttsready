#!/usr/bin/env python
"""Build Sphinx documentation for ttsready.

Run ``python docs/make.py [target]`` from any working directory.

Targets include ``clean``, ``html``, ``dirhtml``, ``latex``, ``all``, and
``help``.
"""

import shutil
import subprocess
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
BUILD_DIR = DOCS_DIR / "_build"
VALID_TARGETS = {
    "html",
    "dirhtml",
    "latex",
    "latexpdf",
    "text",
    "man",
    "changes",
    "linkcheck",
    "doctest",
    "all",
}


def build(target):
    """Run Sphinx for one builder, treating warnings as errors."""
    output_dir = BUILD_DIR / target
    command = ["sphinx-build", "-W", "-b", target, str(DOCS_DIR), str(output_dir)]
    print(f"Building {target} documentation...")
    subprocess.run(command, check=True)


def main():
    """Run the requested documentation target."""
    target = "html" if len(sys.argv) < 2 else sys.argv[1]

    if target == "clean":
        if BUILD_DIR.exists():
            print(f"Cleaning {BUILD_DIR}...")
            shutil.rmtree(BUILD_DIR)
        return 0

    if target == "help":
        print(__doc__)
        return 0

    if target not in VALID_TARGETS:
        print(f"Unknown target: {target}")
        print("Use 'help' target for help")
        return 1

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if target == "all":
        for builder in ["html", "dirhtml", "latex"]:
            build(builder)
    else:
        build(target)

    print(f"Build finished. Documentation is in {BUILD_DIR / target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
