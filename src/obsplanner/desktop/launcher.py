from __future__ import annotations

import argparse
import logging
import multiprocessing
import sys
from pathlib import Path
from typing import Sequence

from .paths import DesktopPaths
from .server import DesktopServerError, StreamlitServer, run_streamlit_child

LOGGER = logging.getLogger("obsplanner.desktop")


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
        url = server.start()
        LOGGER.info("Streamlit is ready at %s", url)
        if options.server_only:
            print(url, flush=True)
            try:
                server.process.wait()
            except KeyboardInterrupt:
                return 0
            return int(server.process.returncode or 0)

        import webview

        webview.create_window(
            "ObsPlanner",
            url,
            width=1400,
            height=900,
            min_size=(1000, 700),
            resizable=True,
            text_select=True,
        )
        webview.start(debug=options.debug)
        return 0
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
