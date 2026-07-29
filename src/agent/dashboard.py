"""Start or reuse the private local Dashboard for an Agent session."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from src.dashboard.cli import _port_available


def _dashboard_healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=0.5) as response:
            payload = json.load(response)
        return (
            response.status == 200
            and isinstance(payload.get("account_alias"), str)
        )
    except (OSError, ValueError, urllib.error.URLError):
        return False


def ensure_agent_dashboard(
    *,
    port: int,
    project_root: Path | None = None,
    open_browser: bool = True,
    timeout_seconds: float = 15.0,
) -> str:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    url = f"http://127.0.0.1:{port}"
    if _dashboard_healthy(url):
        return url
    if not _port_available("127.0.0.1", port):
        raise RuntimeError(
            f"port {port} is occupied by a non-JobsDB service"
        )
    log_path = root / "workspace" / "dashboard" / "agent-dashboard.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src.main",
                "dashboard",
                "start",
                "--port",
                str(port),
                "--no-browser",
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _dashboard_healthy(url):
            if open_browser:
                webbrowser.open(url)
            return url
        if process.poll() is not None:
            raise RuntimeError(
                "JobsDB Dashboard exited before becoming ready"
            )
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError("JobsDB Dashboard readiness timed out")
