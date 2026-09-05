"""Self-update support for the frozen ObsPlanner application.

The updater checks the project's GitHub releases for a newer macOS bundle,
downloads the release ZIP with digest verification, and swaps the running
``ObsPlanner.app`` bundle for the new one.

The Streamlit script (running as the frozen executable's child process)
performs the interactive part: checking for updates and downloading the
verified ZIP. It then stages an update request file in the user data
directory. The desktop launcher watches for that request from the parent
process, applies the bundle swap, relaunches the new app, and exits the old
process tree. The previous bundle is kept beside the new one as a backup and
removed on the next successful launch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .paths import is_frozen

RELEASE_REPO = "jyshangguan/ObsPlanner"
RELEASE_TIMEOUT_SECONDS = 15.0
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60.0
REQUEST_FILENAME = "update-request.json"
BACKUP_PREFIX = "ObsPlanner.app.old-"
ASSET_NAME_PATTERN = re.compile(r"^ObsPlanner-\d[\w.+-]*-macOS-arm64\.zip$")
_VERSION_PATTERN = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-+][\w.]+)?$")

LOGGER = logging.getLogger("obsplanner.desktop")


@dataclass(frozen=True)
class UpdateInfo:
    """A newer release that can be downloaded and applied."""

    version: str
    download_url: str
    asset_name: str
    size: int | None = None
    digest: str | None = None
    published_at: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class UpdateRequest:
    """Instructions staged by the Streamlit UI for the desktop launcher."""

    zip_path: str
    app_path: str
    target_version: str


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse ``v0.2.1``-style release labels into a comparable tuple."""
    if not text:
        return None
    match = _VERSION_PATTERN.match(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer_version(candidate: str, current: str) -> bool:
    """Return true when ``candidate`` is strictly newer than ``current``."""
    candidate_parts = parse_version(candidate)
    current_parts = parse_version(current)
    if candidate_parts is None or current_parts is None:
        return False
    width = max(len(candidate_parts), len(current_parts))
    padded_candidate = candidate_parts + (0,) * (width - len(candidate_parts))
    padded_current = current_parts + (0,) * (width - len(current_parts))
    return padded_candidate > padded_current


def current_version() -> str | None:
    """Return the running application's version, when it is known."""
    try:
        return version("obsplanner")
    except PackageNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Release discovery
# ---------------------------------------------------------------------------


def fetch_latest_release(
    repo: str = RELEASE_REPO,
    *,
    timeout: float = RELEASE_TIMEOUT_SECONDS,
) -> dict:
    """Fetch the latest GitHub release description as a dictionary.

    Network and HTTP errors propagate to the caller.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ObsPlanner-self-updater",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def find_update(release: dict, current: str) -> UpdateInfo | None:
    """Extract a macOS update from a release description.

    Returns ``None`` when the release is not newer than ``current`` or does
    not carry a matching ``ObsPlanner-*-macOS-arm64.zip`` asset.
    """
    if not isinstance(release, dict):
        return None
    tag = str(release.get("tag_name") or "").strip()
    if not tag or not is_newer_version(tag, current):
        return None
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not ASSET_NAME_PATTERN.match(name):
            continue
        size = asset.get("size")
        return UpdateInfo(
            version=tag.lstrip("v"),
            download_url=str(asset["browser_download_url"]),
            asset_name=name,
            size=int(size) if isinstance(size, int) else None,
            digest=str(asset["digest"]) if asset.get("digest") else None,
            published_at=str(release.get("published_at") or "") or None,
            notes=release.get("body") or None,
        )
    return None


# ---------------------------------------------------------------------------
# Download and verification
# ---------------------------------------------------------------------------


def _expected_digest_hex(digest: str | None) -> str | None:
    if not digest:
        return None
    algorithm, _, hex_value = digest.partition(":")
    if algorithm.lower() != "sha256" or not hex_value:
        return None
    return hex_value.strip().lower()


def download_file(
    url: str,
    destination: Path,
    *,
    expected_size: int | None = None,
    digest: str | None = None,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    chunk_bytes: int = DOWNLOAD_CHUNK_BYTES,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    """Download ``url`` to ``destination`` and verify size and digest.

    The download streams to a ``.part`` file that replaces the destination
    only after verification succeeds. Raises ``ValueError`` on a size or
    digest mismatch; the partial file is removed on any failure.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_name(destination.name + ".part")
    digest_hex = _expected_digest_hex(digest)
    hash_accumulator = hashlib.sha256() if digest_hex else None
    downloaded = 0

    try:
        with urlopen(url, timeout=timeout) as response, partial_path.open(
            "wb"
        ) as output:
            total_bytes = expected_size
            if total_bytes is None:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    total_bytes = int(content_length)
            while True:
                chunk = response.read(chunk_bytes)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if hash_accumulator is not None:
                    hash_accumulator.update(chunk)
                if progress is not None:
                    progress(downloaded, total_bytes)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    if expected_size is not None and downloaded != expected_size:
        partial_path.unlink(missing_ok=True)
        raise ValueError(
            f"Downloaded size {downloaded} does not match the expected "
            f"{expected_size} bytes."
        )
    if digest_hex is not None and hash_accumulator.hexdigest() != digest_hex:
        partial_path.unlink(missing_ok=True)
        raise ValueError(
            "Downloaded file digest does not match the release digest."
        )
    partial_path.replace(destination)
    return destination


# ---------------------------------------------------------------------------
# Frozen-bundle helpers
# ---------------------------------------------------------------------------


def running_app_bundle() -> Path | None:
    """Return the running ``.app`` bundle path, or ``None`` outside one."""
    if not is_frozen():
        return None
    executable = Path(sys.executable).resolve()
    contents = executable.parent.parent
    bundle = contents.parent
    if (
        executable.parent.name == "MacOS"
        and contents.name == "Contents"
        and bundle.suffix == ".app"
        and bundle.is_dir()
    ):
        return bundle
    return None


def is_updatable_app() -> bool:
    """True when the current process runs from a swappable ``.app`` bundle."""
    return running_app_bundle() is not None


# ---------------------------------------------------------------------------
# Update requests staged by the Streamlit UI
# ---------------------------------------------------------------------------


def write_update_request(
    data_dir: Path, zip_path: Path, app_path: Path, target_version: str
) -> Path:
    """Stage the launcher-side update request in the user data directory."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    request_path = data_dir / REQUEST_FILENAME
    payload = {
        "zip_path": str(zip_path),
        "app_path": str(app_path),
        "target_version": target_version,
    }
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return request_path


def read_update_request(data_dir: Path) -> UpdateRequest | None:
    """Read a staged update request, or ``None`` when none is pending."""
    request_path = Path(data_dir) / REQUEST_FILENAME
    if not request_path.is_file():
        return None
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        return UpdateRequest(
            zip_path=str(payload["zip_path"]),
            app_path=str(payload["app_path"]),
            target_version=str(payload.get("target_version") or ""),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_update_request(data_dir: Path) -> None:
    (Path(data_dir) / REQUEST_FILENAME).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Applying an update
# ---------------------------------------------------------------------------


def _is_finder_junk(name: str) -> bool:
    """Skip the resource-fork and metadata entries Finder-style zips add."""
    parts = Path(name).parts
    return "__MACOSX" in parts or Path(name).name.startswith("._")


def _extract_release(zip_path: Path, destination: Path) -> None:
    """Extract a release ZIP, restoring symlinks and permissions.

    ``zipfile``'s built-in extraction turns symlinks into regular files,
    which corrupts an app bundle. This extractor recreates symlinks (after
    checking their targets stay inside the extraction), applies stored
    permissions, and rejects members that escape the destination.
    """
    destination.mkdir(parents=True, exist_ok=True)
    resolved_root = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if _is_finder_junk(member.filename):
                continue
            member_path = (destination / member.filename).resolve()
            if not member_path.is_relative_to(resolved_root):
                raise ValueError(
                    "Release archive member escapes its directory: "
                    f"{member.filename}"
                )
            member_path.parent.mkdir(parents=True, exist_ok=True)
            mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                link_target = archive.read(member).decode("utf-8")
                link_destination = (member_path.parent / link_target).resolve()
                if not link_destination.is_relative_to(resolved_root):
                    raise ValueError(
                        "Release archive symlink escapes its directory: "
                        f"{member.filename} -> {link_target}"
                    )
                member_path.unlink(missing_ok=True)
                os.symlink(link_target, member_path)
            elif member.is_dir():
                member_path.mkdir(exist_ok=True)
            else:
                if member_path.exists() and member_path.is_dir():
                    continue
                with archive.open(member) as source, member_path.open(
                    "wb"
                ) as target:
                    shutil.copyfileobj(source, target)
                if mode:
                    os.chmod(member_path, mode & 0o777)


def _find_extracted_app(extraction_root: Path) -> Path:
    """Locate the ``.app`` bundle inside an extracted release."""
    for candidate in sorted(extraction_root.iterdir()):
        if candidate.suffix != ".app" or not candidate.is_dir():
            continue
        if (candidate / "Contents" / "MacOS" / candidate.stem).exists():
            return candidate
    raise ValueError("The release archive does not contain an app bundle.")


def apply_update(
    zip_path: Path,
    app_path: Path,
    extraction_root: Path,
) -> Path:
    """Replace ``app_path`` with the app bundle from a release ZIP.

    The previous bundle is renamed to a sibling backup first, so a failed
    swap is rolled back. Returns the new bundle path (equal to
    ``app_path``).
    """
    zip_path = Path(zip_path)
    app_path = Path(app_path).resolve()
    if not app_path.is_dir():
        raise ValueError(f"Cannot update a missing app bundle: {app_path}")
    extraction_root = Path(extraction_root)
    extraction_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=extraction_root) as temp_name:
        _extract_release(zip_path, Path(temp_name))
        new_app = _find_extracted_app(Path(temp_name))
        backup_path = app_path.with_name(
            f"{BACKUP_PREFIX}{int(time.time())}"
        )
        app_path.rename(backup_path)
        try:
            shutil.move(str(new_app), str(app_path))
        except Exception:
            shutil.rmtree(app_path, ignore_errors=True)
            if backup_path.is_dir() and not app_path.exists():
                backup_path.rename(app_path)
            raise
    return app_path


def relaunch_app(app_path: Path) -> None:
    """Launch the app bundle at ``app_path`` as a detached process."""
    app_path = Path(app_path)
    executable = app_path / "Contents" / "MacOS" / app_path.stem
    if not executable.is_file():
        raise ValueError(f"App executable not found: {executable}")
    subprocess.Popen(
        [str(executable)],
        cwd=str(app_path.parent),
        start_new_session=True,
    )


def cleanup_old_backups(app_path: Path) -> None:
    """Remove leftover bundle backups from earlier updates."""
    app_path = Path(app_path)
    if not app_path.parent.is_dir():
        return
    for sibling in app_path.parent.glob(f"{BACKUP_PREFIX}*"):
        if sibling == app_path or not sibling.is_dir():
            continue
        shutil.rmtree(sibling, ignore_errors=True)


# ---------------------------------------------------------------------------
# Launcher-side watcher
# ---------------------------------------------------------------------------


class UpdateWatcher:
    """Watch for staged update requests and apply them.

    Runs a daemon thread in the desktop launcher process. When a request
    appears it verifies the target bundle matches the running app, checks
    the staged version is still newer, swaps the bundle, relaunches the new
    app, and calls ``exit_callback`` so the launcher can terminate the old
    process tree.
    """

    def __init__(
        self,
        data_dir: Path,
        app_path: Path,
        cache_dir: Path,
        exit_callback: Callable[[], None],
        *,
        poll_interval_seconds: float = 1.5,
        applier: Callable[[Path, Path, Path], Path] = apply_update,
        version_of_running_app: str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.app_path = Path(app_path).resolve()
        self.cache_dir = Path(cache_dir)
        self.exit_callback = exit_callback
        self.poll_interval_seconds = poll_interval_seconds
        self._applier = applier
        self._current_version = (
            version_of_running_app
            if version_of_running_app is not None
            else current_version()
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="obsplanner-update-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval_seconds):
            try:
                self._process_once()
            except Exception:
                LOGGER.exception("Applying a staged update failed")

    def _process_once(self) -> None:
        request = read_update_request(self.data_dir)
        if request is None:
            return
        if (
            Path(request.app_path).resolve() != self.app_path
            or not Path(request.zip_path).is_file()
        ):
            clear_update_request(self.data_dir)
            LOGGER.warning(
                "Discarded an update request that does not match this app."
            )
            return
        if self._current_version and not is_newer_version(
            request.target_version, self._current_version
        ):
            clear_update_request(self.data_dir)
            LOGGER.info(
                "Skipped a staged update to %s; the running app is not "
                "older.",
                request.target_version,
            )
            return
        try:
            new_app = self._applier(
                Path(request.zip_path),
                self.app_path,
                self.cache_dir / "updates",
            )
        except Exception:
            # The failed swap was rolled back, so keep running and drop the
            # request instead of retrying it forever.
            clear_update_request(self.data_dir)
            raise
        clear_update_request(self.data_dir)
        LOGGER.info("Applied update %s to %s", request.target_version, new_app)
        relaunch_app(new_app)
        self.exit_callback()
