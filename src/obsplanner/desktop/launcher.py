from __future__ import annotations

import argparse
import base64
import html
import logging
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Sequence

from .paths import DesktopPaths
from .server import DesktopServerError, StreamlitServer, run_streamlit_child

LOGGER = logging.getLogger("obsplanner.desktop")


def _startup_html(logo_path: Path) -> str:
    logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          html, body {{
            height: 100%;
            margin: 0;
          }}
          body {{
            background: #020817;
            overflow: hidden;
            position: relative;
          }}
          img {{
            height: 100%;
            inset: 0;
            object-fit: contain;
            position: absolute;
            width: 100%;
          }}
          p {{
            backdrop-filter: blur(8px);
            background: rgba(2, 8, 23, 0.72);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 999px;
            bottom: 24px;
            color: rgba(255, 255, 255, 0.9);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 14px;
            left: 50%;
            margin: 0;
            padding: 8px 16px;
            position: absolute;
            transform: translateX(-50%);
            white-space: nowrap;
          }}
          @media (prefers-reduced-transparency: reduce) {{
            p {{
              backdrop-filter: none;
            }}
          }}
        </style>
      </head>
      <body>
        <img src="data:image/png;base64,{logo_data}" alt="ObsPlanner observatories">
        <p>Starting astronomical visibility planner…</p>
      </body>
    </html>
    """


def _wait_for_app_render(window, timeout: float = 20.0) -> None:
    """Wait until ObsPlanner has rendered its initial UI or an error message."""
    deadline = time.monotonic() + timeout
    window.events.loaded.wait(timeout=timeout)
    while time.monotonic() < deadline:
        if window.evaluate_js(
            "Boolean("
            "document.querySelector('#obsplanner-app-ready') || "
            "document.querySelector('[data-testid=\"stAlert\"]')"
            ")"
        ):
            return
        time.sleep(0.1)
    LOGGER.warning("Timed out waiting for the Streamlit interface to render")


def _start_application(
    startup_window,
    app_window,
    server: StreamlitServer,
    failures: list[Exception],
) -> None:
    try:
        url = server.start()
        LOGGER.info("Streamlit is ready at %s", url)
        app_window.events.loaded.clear()
        app_window.load_url(url)
        _wait_for_app_render(app_window)
        startup_window.destroy()
    except Exception as exc:
        LOGGER.exception("ObsPlanner could not start")
        failures.append(exc)
        message = html.escape(str(exc))
        startup_window.load_html(
            "<html><body style='font-family:-apple-system;padding:3rem'>"
            "<h2>ObsPlanner could not start</h2>"
            f"<p>{message}</p></body></html>"
        )


def _configure_logging(log_path: Path, debug: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _show_native_error(message: str) -> None:
    LOGGER.exception(message)
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("ObsPlanner", message)
        root.destroy()
    except Exception:
        print(f"ObsPlanner: {message}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch ObsPlanner as a desktop app.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable pywebview debug tools and verbose logging.",
    )
    parser.add_argument(
        "--server-only",
        action="store_true",
        help="Start the local Streamlit server without opening a window.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    multiprocessing.freeze_support()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--streamlit-child":
        return run_streamlit_child(arguments[1:])

    options = _parser().parse_args(arguments)
    paths = DesktopPaths.discover()
    paths.ensure_writable_directories()
    log_path = paths.log_dir / "ObsPlanner.log"
    _configure_logging(log_path, options.debug)

    server = StreamlitServer(
        app_path=paths.app_script,
        log_path=paths.log_dir / "streamlit.log",
    )
    try:
        paths.validate_resources()
        if options.server_only:
            url = server.start()
            LOGGER.info("Streamlit is ready at %s", url)
            print(url, flush=True)
            try:
                server.process.wait()
            except KeyboardInterrupt:
                return 0
            return int(server.process.returncode or 0)

        import webview

        app_window = webview.create_window(
            "ObsPlanner",
            html="<html><body style='background:#020817'></body></html>",
            width=1400,
            height=900,
            min_size=(1000, 700),
            resizable=True,
            text_select=True,
        )
        startup_window = webview.create_window(
            "ObsPlanner",
            html=_startup_html(paths.app_logo),
            width=1400,
            height=900,
            min_size=(1000, 700),
            resizable=True,
            text_select=True,
        )
        startup_failures: list[Exception] = []
        webview.start(
            _start_application,
            (startup_window, app_window, server, startup_failures),
            debug=options.debug,
        )
        return 1 if startup_failures else 0
    except (DesktopServerError, FileNotFoundError) as exc:
        if options.server_only:
            LOGGER.exception(str(exc))
            print(f"ObsPlanner: {exc}", file=sys.stderr)
        else:
            _show_native_error(str(exc))
        return 1
    except Exception as exc:
        message = f"ObsPlanner could not start: {exc}"
        if options.server_only:
            LOGGER.exception(message)
            print(message, file=sys.stderr)
        else:
            _show_native_error(message)
        return 1
    finally:
        server.stop()
