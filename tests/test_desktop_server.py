from pathlib import Path
from urllib.request import urlopen

from obsplanner.desktop.server import (
    StreamlitServer,
    build_server_command,
    find_free_port,
)


def test_find_free_port_returns_bindable_loopback_port():
    port = find_free_port()
    assert 0 < port < 65536


def test_development_server_command():
    command = build_server_command(
        Path("/tmp/app.py"),
        "127.0.0.1",
        54321,
        executable="/python",
        frozen=False,
    )
    assert command[:5] == [
        "/python",
        "-m",
        "streamlit",
        "run",
        "/tmp/app.py",
    ]
    assert "--server.address=127.0.0.1" in command
    assert "--server.port=54321" in command
    assert "--global.developmentMode=false" in command


def test_frozen_server_command():
    command = build_server_command(
        Path("/bundle/app.py"),
        "127.0.0.1",
        54321,
        executable="/ObsPlanner",
        frozen=True,
    )
    assert command[:3] == [
        "/ObsPlanner",
        "--streamlit-child",
        "/bundle/app.py",
    ]


def test_streamlit_server_health_and_shutdown(tmp_path: Path):
    app_path = tmp_path / "smoke_app.py"
    app_path.write_text(
        "import streamlit as st\nst.write('desktop smoke test')\n",
        encoding="utf-8",
    )
    server = StreamlitServer(
        app_path=app_path,
        log_path=tmp_path / "streamlit.log",
        startup_timeout=20,
    )
    server.start()
    process = server.process
    try:
        with urlopen(server.health_url, timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"ok"
    finally:
        server.stop()
    assert process is not None
    assert process.poll() is not None
