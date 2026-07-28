import sys
from pathlib import Path
from types import SimpleNamespace

from obsplanner.desktop import launcher
from obsplanner.desktop.paths import DesktopPaths


def test_launcher_opens_window_and_stops_server(monkeypatch, tmp_path: Path):
    app_path = tmp_path / "app.py"
    catalog_path = tmp_path / "observatories.yaml"
    app_path.write_text("", encoding="utf-8")
    catalog_path.write_text("site: {}\n", encoding="utf-8")
    paths = DesktopPaths(
        resource_root=tmp_path,
        app_script=app_path,
        observatory_catalog=catalog_path,
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    monkeypatch.setattr(
        launcher.DesktopPaths, "discover", classmethod(lambda cls: paths)
    )

    events = []

    class FakeServer:
        def __init__(self, **kwargs):
            events.append(("server-created", kwargs))

        def start(self):
            events.append(("server-started",))
            return "http://127.0.0.1:54321"

        def stop(self):
            events.append(("server-stopped",))

    fake_webview = SimpleNamespace(
        create_window=lambda *args, **kwargs: events.append(
            ("window-created", args, kwargs)
        ),
        start=lambda **kwargs: events.append(("window-started", kwargs)),
    )
    monkeypatch.setattr(launcher, "StreamlitServer", FakeServer)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    assert launcher.main([]) == 0
    assert ("server-started",) in events
    assert any(event[0] == "window-created" for event in events)
    assert any(event[0] == "window-started" for event in events)
    assert events[-1] == ("server-stopped",)
