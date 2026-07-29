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
        app_logo=tmp_path / "ObsPlanner.png",
        observatory_catalog=catalog_path,
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    paths.app_logo.write_bytes(b"test-logo")
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

    class FakeEvent:
        def clear(self):
            events.append(("loaded-cleared",))

        def wait(self, timeout=None):
            events.append(("loaded-waited", timeout))
            return True

    class FakeWindow:
        def __init__(self, name):
            self.name = name
            self.events = SimpleNamespace(loaded=FakeEvent())

        def load_url(self, url):
            events.append(("url-loaded", self.name, url))

        def load_html(self, content):
            events.append(("html-loaded", self.name, content))

        def evaluate_js(self, script):
            events.append(("js-evaluated", self.name, script))
            return True

        def show(self):
            events.append(("window-shown", self.name))

        def destroy(self):
            events.append(("window-destroyed", self.name))

    def create_window(*args, **kwargs):
        events.append(("window-created", args, kwargs))
        name = "app" if len([event for event in events if event[0] == "window-created"]) == 1 else "startup"
        return FakeWindow(name)

    def start(function, arguments, **kwargs):
        events.append(("window-started", kwargs))
        function(*arguments)

    fake_webview = SimpleNamespace(create_window=create_window, start=start)
    monkeypatch.setattr(launcher, "StreamlitServer", FakeServer)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    assert launcher.main([]) == 0
    assert ("server-started",) in events
    assert ("url-loaded", "app", "http://127.0.0.1:54321") in events
    window_events = [event for event in events if event[0] == "window-created"]
    assert len(window_events) == 2
    assert "Starting astronomical visibility planner" in window_events[1][2]["html"]
    assert "hidden" not in window_events[0][2]
    assert ("window-destroyed", "startup") in events
    assert any(
        event[0] == "js-evaluated" and "#obsplanner-app-ready" in event[2]
        for event in events
    )
    assert any(event[0] == "window-started" for event in events)
    assert events[-1] == ("server-stopped",)
