"""Dev Container checks (07-TEST-PLAN.md §5). Run with: pytest -m container

The port tests reuse a server that is already running on the port; otherwise they start one.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from app.core.database import Database
from app.core.tools import ToolRegistry

pytestmark = pytest.mark.container

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("tool", ["exiftool", "tesseract", "ffmpeg", "ffprobe"])
def test_tool_is_installed(tool: str) -> None:
    status = ToolRegistry().status(tool)
    assert status.status == "ok", status
    assert status.version


def test_tesseract_has_english_language_data() -> None:
    assert "eng" in ToolRegistry().status("tesseract").languages


def test_sqlite_database_initializes(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.initialize()
    assert db.is_healthy()
    db.dispose()


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@contextmanager
def serving(command: list[str], port: int, cwd: Path, env: dict[str, str]) -> Iterator[None]:
    if _port_open(port):
        yield
        return
    # A new session lets us stop the whole process group: `npm run dev` starts vite as a child.
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 90
        while not _port_open(port):
            assert process.poll() is None, f"{command[0]} exited with code {process.returncode}"
            assert time.monotonic() < deadline, f"nothing listening on port {port}"
            time.sleep(0.5)
        yield
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=30)


def test_backend_serves_on_port_8400(tmp_path: Path) -> None:
    env = {**os.environ, "VESTIGO_DATA_DIR": str(tmp_path / "data")}
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8400"]
    with serving(command, 8400, REPO, env):
        body = httpx.get("http://localhost:8400/api/v1/health", timeout=10).json()

    assert body["database"] == "ok"
    assert body["storage"] == "ok"
    assert body["status"] == "ok"


def test_frontend_serves_on_port_5180() -> None:
    with serving(["npm", "run", "dev"], 5180, REPO / "web", dict(os.environ)):
        response = httpx.get("http://localhost:5180/", timeout=10)

    assert response.status_code == 200
    assert "Vestigo Media Forensics" in response.text
