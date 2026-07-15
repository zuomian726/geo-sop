#!/usr/bin/env python3
"""Make the official python.org framework usable from a build cache."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(*args: str, check: bool = True) -> str:
    return subprocess.run(args, check=check, capture_output=True, text=True).stdout


def relocate(framework_root: Path, series: str) -> int:
    version_root = framework_root / "Python.framework" / "Versions" / series
    old_prefix = f"/Library/Frameworks/Python.framework/Versions/{series}"
    if not version_root.is_dir():
        raise SystemExit(f"Python framework is missing: {version_root}")

    changed_files = 0
    for path in version_root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if "Mach-O" not in run("file", "-b", str(path)):
            continue

        changes = []
        lines = run("otool", "-L", str(path)).splitlines()[1:]
        for line in lines:
            dependency = line.strip().split(" ", 1)[0]
            if dependency.startswith(old_prefix):
                replacement = str(version_root) + dependency[len(old_prefix):]
                changes.extend(["-change", dependency, replacement])

        dylib_ids = run("otool", "-D", str(path), check=False).splitlines()[1:]
        if dylib_ids:
            dylib_id = dylib_ids[0].strip()
            if dylib_id.startswith(old_prefix):
                replacement = str(version_root) + dylib_id[len(old_prefix):]
                changes.extend(["-id", replacement])

        if not changes:
            continue
        subprocess.run(["install_name_tool", *changes, str(path)], check=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(path)], check=True)
        changed_files += 1

    print(f"Relocated {changed_files} Python framework binaries under {version_root}")
    return changed_files


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: relocate_macos_python.py FRAMEWORK_ROOT PYTHON_SERIES")
    relocate(Path(sys.argv[1]).resolve(), sys.argv[2])
