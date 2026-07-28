from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Sequence


class DesktopServerError(RuntimeError):
    """Raised when the embedded Streamlit server cannot start."""


def find_free_port(host: str = "127.0.0.1") -> int:
    """Ask the operating system for a currently unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def streamlit_arguments(app_path: Path, host: str, port: int) -> list[str]:
    return [
        str(app_path),
        f"--server.address={host}",
        f"--server.port={port}",
        "--server.headless=true",
        "--server.runOnSave=false",
        "--browser.gatherUsageStats=false",
        "--server.fileWatcherType=none",
        "--global.developmentMode=false",
    ]


def build_server_command(
    app_path: Path,
    host: str,
    port: int,
    *,
    executable: str | None = None,
    frozen: bool | None = None,
) -> list[str]:
    executable = executable or sys.executable
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    arguments = streamlit_arguments(app_path, host, port)
    if frozen:
        return [executable, "--streamlit-child", *arguments]
    return [executable, "-m", "streamlit", "run", *arguments]


def run_streamlit_child(arguments: Sequence[str]) -> int:
    """Run Streamlit inside the frozen executable's dedicated child mode."""
    from streamlit.web import cli as streamlit_cli

    previous_argv = sys.argv
    try:
        sys.argv = ["streamlit", "run", *arguments]
        result = streamlit_cli.main(standalone_mode=False)
        return int(result or 0)
    finally:
        sys.argv = previous_argv


@dataclass
class StreamlitServer:
    app_path: Path
    log_path: Path
    host: str = "127.0.0.1"
    port: int | None = None
    startup_timeout: float = 30.0
    shutdown_timeout: float = 5.0
    process: subprocess.Popen | None = field(default=None, init=False)
    _log_stream: IO[str] | None = field(default=None, init=False, repr=False)

    @property
    def url(self) -> str:
        if self.port is None:
            raise DesktopServerError("The Streamlit server has not been started.")
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.url}/_stcore/health"

    def start(self) -> str:
        if self.process is not None:
            raise DesktopServerError("The Streamlit server is already running.")
        if not self.app_path.is_file():
            raise DesktopServerError(f"Streamlit app not found: {self.app_path}")

        self.port = self.port or find_free_port(self.host)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.log_path.open("a", encoding="utf-8")
        environment = os.environ.copy()
        environment.update(
            {
                "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
                "STREAMLIT_SERVER_HEADLESS": "true",
            }
        )
        command = build_server_command(self.app_path, self.host, self.port)
        self.process = subprocess.Popen(
            command,
            cwd=self.app_path.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            self.wait_until_ready()
        except Exception:
            self.stop()
            raise
        return self.url

    def wait_until_ready(self) -> None:
        if self.process is None:
            raise DesktopServerError("The Streamlit server has not been started.")
        deadline = time.monotonic() + self.startup_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            return_code = self.process.poll()
            if return_code is not None:
                raise DesktopServerError(
                    f"Streamlit exited during startup with status {return_code}. "
                    f"See {self.log_path}."
                )
            try:
                with urllib.request.urlopen(self.health_url, timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
            time.sleep(0.1)
        raise DesktopServerError(
            f"Streamlit did not become ready within {self.startup_timeout:.0f} "
            f"seconds. See {self.log_path}."
        ) from last_error

    def stop(self) -> None:
        process, self.process = self.process, None
        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self.shutdown_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=self.shutdown_timeout)
        finally:
            if self._log_stream is not None:
                self._log_stream.close()
                self._log_stream = None

    def __enter__(self) -> "StreamlitServer":
        self.start()
        return self

    def __exit__(self, *_exc_info) -> None:
        self.stop()
