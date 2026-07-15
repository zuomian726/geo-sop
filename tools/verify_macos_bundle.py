#!/usr/bin/env python3
"""Verify architecture and deployment targets for a packaged macOS app."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def deployment_target(path: Path) -> str | None:
    output = command("xcrun", "vtool", "-show-build", str(path))
    match = re.search(r"^\s*minos\s+([0-9.]+)\s*$", output, re.MULTILINE)
    if match:
        return match.group(1)
    legacy = re.search(
        r"LC_VERSION_MIN_MACOSX.*?^\s*version\s+([0-9.]+)\s*$",
        output,
        re.MULTILINE | re.DOTALL,
    )
    return legacy.group(1) if legacy else None


def verify(app_path: Path, expected_arch: str, maximum_macos: str) -> int:
    if not app_path.is_dir():
        raise SystemExit(f"Application bundle does not exist: {app_path}")

    checked = 0
    failures = []
    maximum = version_tuple(maximum_macos)
    for path in app_path.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        kind = command("file", "-b", str(path))
        if "Mach-O" not in kind:
            continue

        checked += 1
        architectures = set(command("lipo", "-archs", str(path)).strip().split())
        if expected_arch not in architectures:
            failures.append(f"{path}: missing {expected_arch}; found {sorted(architectures)}")
            continue

        target = deployment_target(path)
        if target and version_tuple(target) > maximum:
            failures.append(f"{path}: requires macOS {target}, maximum allowed is {maximum_macos}")

    if checked == 0:
        failures.append(f"{app_path}: no Mach-O files were found")
    if failures:
        raise SystemExit("macOS bundle verification failed:\n" + "\n".join(failures))

    print(f"Verified {checked} Mach-O files: architecture={expected_arch}, macOS<={maximum_macos}")
    return checked


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify_macos_bundle.py APP_PATH ARCH MAXIMUM_MACOS")
    verify(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
