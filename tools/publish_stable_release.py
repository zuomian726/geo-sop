#!/usr/bin/env python3
"""Prepare and atomically publish a signed GEO-SOP stable desktop release."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
APP_VERSION = str(runpy.run_path(str(ROOT / "version.py"))["APP_VERSION"])
PLATFORMS = {
    "macos": ("GEO-SOP-v{version}-macOS-Apple-Silicon.dmg", "GEO-SOP-macOS.dmg", ".dmg"),
    "macos_intel": ("GEO-SOP-v{version}-macOS-Intel.dmg", "GEO-SOP-macOS-Intel.dmg", ".dmg"),
    "windows": ("GEO-SOP-Setup-v{version}.exe", "GEO-SOP-Setup.exe", ".exe"),
}


def fail(message: str) -> None:
    raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_size(size: int) -> str:
    return f"{round(size / 1024 / 1024)} MB"


def run_checked(command: list[str]) -> None:
    subprocess.run(command, check=True)


def verify_macos(path: Path, expected_arch: str, version: str) -> None:
    if sys.platform != "darwin":
        fail("Stable macOS artifacts must be verified from macOS before publishing.")
    run_checked(["codesign", "--verify", "--verbose=2", str(path)])
    run_checked(["xcrun", "stapler", "validate", str(path)])
    run_checked([
        "bash",
        str(ROOT / "tools" / "smoke_macos_dmg.sh"),
        str(path),
        expected_arch,
        version,
    ])


def verify_windows_evidence(path: Path, installer_sha256: str, version: str) -> None:
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Windows signing evidence is invalid: {exc}")
    if evidence.get("status") != "Valid":
        fail("Windows Authenticode evidence does not report a Valid signature.")
    if str(evidence.get("sha256", "")).lower() != installer_sha256:
        fail("Windows signing evidence does not match the selected installer.")
    if str(evidence.get("version", "")) != version:
        fail("Windows signing evidence does not match the release version.")


def ensure_clean_worktree() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
    )
    if result.stdout.strip():
        fail("Refusing to publish from a dirty Git worktree. Commit and verify the release first.")


def publish(stage: Path, manifest: dict, ssh_host: str, server_root: str) -> None:
    token = datetime.now().strftime("%Y%m%d%H%M%S")
    remote_stage = f"{server_root}/storage/release-staging/{manifest['version']}-{token}"
    run_checked(["ssh", ssh_host, f"mkdir -p {shlex.quote(remote_stage)}"])
    upload_paths = [stage / item[0].format(version=manifest["version"]) for item in PLATFORMS.values()]
    upload_paths.append(stage / "update.json")
    run_checked(["scp", *map(str, upload_paths), f"{ssh_host}:{remote_stage}/"])

    checks = []
    versioned_installs = []
    alias_installs = []
    for key, (versioned_pattern, alias, _suffix) in PLATFORMS.items():
        versioned = versioned_pattern.format(version=manifest["version"])
        expected = manifest["downloads"][key]["sha256"]
        checks.append(f"echo {shlex.quote(expected + '  ' + remote_stage + '/' + versioned)} | sha256sum -c -")
        versioned_installs.append(f"install -m 0644 {shlex.quote(remote_stage + '/' + versioned)} {shlex.quote(server_root + '/downloads/' + versioned)}")
        alias_installs.append(f"cp {shlex.quote(remote_stage + '/' + versioned)} {shlex.quote(server_root + '/downloads/.' + alias + '.new')}")
        alias_installs.append(f"mv {shlex.quote(server_root + '/downloads/.' + alias + '.new')} {shlex.quote(server_root + '/downloads/' + alias)}")
    remote_script = "set -euo pipefail; " + "; ".join(
        [
            f"mkdir -p {shlex.quote(server_root + '/downloads')}",
            *checks,
            f"cp {shlex.quote(server_root + '/update.json')} {shlex.quote(server_root + '/storage/update.json.before-' + token)} 2>/dev/null || true",
            *versioned_installs,
            *alias_installs,
            f"install -m 0644 {shlex.quote(remote_stage + '/update.json')} {shlex.quote(server_root + '/.update.json.new')}",
            f"mv {shlex.quote(server_root + '/.update.json.new')} {shlex.quote(server_root + '/update.json')}",
            f"rm -rf {shlex.quote(remote_stage)}",
        ]
    )
    run_checked(["ssh", ssh_host, "bash", "-lc", shlex.quote(remote_script)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument("--macos", type=Path, required=True, help="Notarized Apple Silicon DMG")
    parser.add_argument("--macos-intel", type=Path, required=True, help="Notarized Intel DMG")
    parser.add_argument("--windows", type=Path, required=True, help="Signed Windows Setup EXE")
    parser.add_argument("--windows-evidence", type=Path, required=True)
    parser.add_argument("--minimum-supported-version", default="0.3.17-dev")
    parser.add_argument("--note", action="append", dest="notes", required=True)
    parser.add_argument("--base-url", default="https://geo.allgood.cn")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--ssh-host", default="server93")
    parser.add_argument("--server-root", default="/www/wwwroot/geo.allgood.cn")
    args = parser.parse_args()

    version = args.version.lstrip("v")
    if version != APP_VERSION:
        fail(f"Requested version {version} does not match version.py ({APP_VERSION}).")
    if not version or "dev" in version.lower() or "beta" in version.lower():
        fail("Stable publishing requires a non-development version such as 1.0.0.")

    inputs = {"macos": args.macos, "macos_intel": args.macos_intel, "windows": args.windows}
    metadata = {}
    for key, path in inputs.items():
        if not path.is_file() or path.suffix.lower() != PLATFORMS[key][2]:
            fail(f"Missing or invalid {key} artifact: {path}")
        size = path.stat().st_size
        if size < 50_000_000:
            fail(f"{key} artifact is unexpectedly small ({size} bytes).")
        metadata[key] = {"size_bytes": size, "sha256": sha256(path)}

    verify_macos(inputs["macos"], "arm64", version)
    verify_macos(inputs["macos_intel"], "x86_64", version)
    verify_windows_evidence(args.windows_evidence, metadata["windows"]["sha256"], version)

    output = args.output_dir or ROOT / "release" / f"publish-v{version}"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    downloads = {}
    base_url = args.base_url.rstrip("/")
    for key, path in inputs.items():
        versioned = PLATFORMS[key][0].format(version=version)
        shutil.copy2(path, output / versioned)
        downloads[key] = {
            "name": PLATFORMS[key][1],
            "version": version,
            "url": f"{base_url}/downloads/{PLATFORMS[key][1]}",
            "versioned_url": f"{base_url}/downloads/{versioned}",
            "size": display_size(metadata[key]["size_bytes"]),
            "sha256": metadata[key]["sha256"],
        }
    manifest = {
        "app": "GEO-SOP",
        "version": version,
        "channel": "stable",
        "released_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "minimum_supported_version": args.minimum_supported_version,
        "force": False,
        "notes": args.notes,
        "downloads": downloads,
    }
    (output / "update.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared signed release v{version} in {output}")

    if args.publish:
        ensure_clean_worktree()
        publish(output, manifest, args.ssh_host, args.server_root.rstrip("/"))
        print(f"Published v{version}; update.json was switched last.")
    else:
        print("Prepare-only mode: nothing was uploaded. Add --publish after final verification.")


if __name__ == "__main__":
    main()
