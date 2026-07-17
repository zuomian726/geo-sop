#!/usr/bin/env python3
"""Validate the complete cloud distribution against disposable MySQL and PHP."""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = ROOT / "server" / "geo.allgood.cn"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required command is unavailable: {name}")
    return path


def run(command: list[str], *, env=None, timeout=120, capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        timeout=timeout,
        check=True,
        text=True,
        capture_output=capture,
    )


def wait_for_mysql(mysqladmin: str, socket_path: Path) -> None:
    for _ in range(80):
        result = subprocess.run(
            [mysqladmin, f"--socket={socket_path}", "-uroot", "ping"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.25)
    raise RuntimeError("temporary MySQL did not become ready")


def wait_for_php(base_url: str) -> None:
    import urllib.request

    for _ in range(60):
        try:
            with urllib.request.urlopen(base_url + "/", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("temporary PHP server did not become ready")


def main() -> None:
    mysqld = require_command("mysqld")
    mysql = require_command("mysql")
    mysqladmin = require_command("mysqladmin")
    php = require_command("php")
    python = str(ROOT / ".venv-desktop" / "bin" / "python")
    if not Path(python).is_file():
        raise RuntimeError("desktop virtual environment is unavailable")

    mysql_process = None
    php_process = None
    with tempfile.TemporaryDirectory(prefix="geo-sop-fresh-cloud-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "mysql-data"
        storage_dir = temp / "storage"
        socket_path = temp / "mysql.sock"
        mysql_log = temp / "mysql.log"
        php_log_path = temp / "php.log"
        data_dir.mkdir()
        storage_dir.mkdir()
        mysql_port = free_port()
        php_port = free_port()
        db_password = secrets.token_hex(16)

        try:
            run([
                mysqld,
                "--no-defaults",
                "--initialize-insecure",
                f"--datadir={data_dir}",
                f"--log-error={mysql_log}",
            ])
            mysql_process = subprocess.Popen(
                [
                    mysqld,
                    "--no-defaults",
                    f"--datadir={data_dir}",
                    f"--socket={socket_path}",
                    f"--port={mysql_port}",
                    "--bind-address=127.0.0.1",
                    f"--pid-file={temp / 'mysql.pid'}",
                    f"--log-error={mysql_log}",
                ],
                cwd=ROOT,
            )
            wait_for_mysql(mysqladmin, socket_path)
            setup_sql = (
                "CREATE DATABASE geo_cloud_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                f"CREATE USER 'geo_test'@'127.0.0.1' IDENTIFIED BY '{db_password}';"
                "GRANT ALL ON geo_cloud_test.* TO 'geo_test'@'127.0.0.1'; FLUSH PRIVILEGES;"
            )
            run([mysql, f"--socket={socket_path}", "-uroot", "-e", setup_sql])

            env = os.environ.copy()
            env.update(
                {
                    "GEO_SYNC_CONFIG": str(SERVER_ROOT / "storage" / "sync_config.example.php"),
                    "GEO_STORAGE_DIR": str(storage_dir),
                    "GEO_DB_HOST": "127.0.0.1",
                    "GEO_DB_PORT": str(mysql_port),
                    "GEO_DB_NAME": "geo_cloud_test",
                    "GEO_DB_USER": "geo_test",
                    "GEO_DB_PASSWORD": db_password,
                    "GEO_LEGACY_SYNC_TOKEN": secrets.token_hex(32),
                    "GEO_PUBLIC_BASE_URL": f"http://127.0.0.1:{php_port}",
                    "GEO_DEMO_USERNAME": "tuke",
                }
            )
            run(
                [
                    php,
                    "-r",
                    'require "server/geo.allgood.cn/api/common.php"; '
                    '$pdo=geo_pdo(); geo_ensure_schema($pdo); '
                    'geo_create_user($pdo,"tuke","temporary-demo-password");',
                ],
                env=env,
            )
            run([php, "server/geo.allgood.cn/demo/seed.php"], env=env)

            with php_log_path.open("w", encoding="utf-8") as php_log:
                php_process = subprocess.Popen(
                    [php, "-S", f"127.0.0.1:{php_port}", "-t", str(SERVER_ROOT)],
                    cwd=ROOT,
                    env=env,
                    stdout=php_log,
                    stderr=subprocess.STDOUT,
                )
                base_url = f"http://127.0.0.1:{php_port}"
                wait_for_php(base_url)
                run([python, "tools/smoke_cloud_site.py", base_url], env=env)
                run(
                    [
                        python,
                        "tools/smoke_cloud_client_pipeline.py",
                        "--base-url",
                        base_url,
                        "--keep",
                    ],
                    env=env,
                )
        finally:
            if php_process and php_process.poll() is None:
                php_process.terminate()
                try:
                    php_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    php_process.kill()
            if mysql_process and mysql_process.poll() is None:
                subprocess.run(
                    [mysqladmin, f"--socket={socket_path}", "-uroot", "shutdown"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                try:
                    mysql_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    mysql_process.kill()

    print("Fresh cloud deployment acceptance passed; disposable data removed")


if __name__ == "__main__":
    main()
