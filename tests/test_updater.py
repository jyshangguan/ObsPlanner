import hashlib
import json
import shutil
import threading
import time
import zipfile
from pathlib import Path

import pytest

from obsplanner.desktop import updater


RELEASE_FIXTURE = {
    "tag_name": "v0.2.1",
    "published_at": "2026-09-06T02:00:00Z",
    "body": "- Adds in-app self-updates.",
    "assets": [
        {
            "name": "ObsPlanner-0.2.1-macOS-arm64.zip",
            "size": 107_000_000,
            "digest": (
                "sha256:e6d024d62da11c85ed8e33d9b9b37eded"
                "3ee828754bb244978de051486ab51dd"
            ),
            "browser_download_url": (
                "https://github.com/jyshangguan/ObsPlanner/releases/download/"
                "v0.2.1/ObsPlanner-0.2.1-macOS-arm64.zip"
            ),
        }
    ],
}


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.headers = {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v0.2.1", (0, 2, 1)),
        ("0.2", (0, 2)),
        ("1.10.0", (1, 10, 0)),
        ("v1.0.0-beta", (1, 0, 0)),
        ("", None),
        ("unknown", None),
        ("v", None),
    ],
)
def test_parse_version(text, expected):
    assert updater.parse_version(text) == expected


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("0.2.1", "0.2.0", True),
        ("v0.3.0", "v0.2.9", True),
        ("0.10.0", "0.9.9", True),
        ("0.2.0", "0.2.0", False),
        ("v0.2.0", "0.2.0", False),
        ("0.2.0", "0.2.1", False),
        ("1.0", "1.0.0", False),
        ("not-a-version", "0.2.0", False),
        ("0.3.0", "garbage", False),
    ],
)
def test_is_newer_version(candidate, current, expected):
    assert updater.is_newer_version(candidate, current) is expected


def test_current_version_is_available_and_parseable():
    version = updater.current_version()
    assert version is not None
    assert updater.parse_version(version) is not None


def test_find_update_extracts_the_macos_asset():
    update = updater.find_update(RELEASE_FIXTURE, "0.2.0")

    assert update is not None
    assert update.version == "0.2.1"
    assert update.asset_name == "ObsPlanner-0.2.1-macOS-arm64.zip"
    assert update.size == 107_000_000
    assert update.digest == RELEASE_FIXTURE["assets"][0]["digest"]
    assert update.download_url.endswith("ObsPlanner-0.2.1-macOS-arm64.zip")
    assert update.published_at == "2026-09-06T02:00:00Z"
    assert update.notes == "- Adds in-app self-updates."


def test_find_update_ignores_equal_or_older_releases():
    assert updater.find_update(RELEASE_FIXTURE, "0.2.1") is None
    assert updater.find_update(RELEASE_FIXTURE, "0.3.0") is None


def test_find_update_requires_a_macos_arm64_asset():
    release = json.loads(json.dumps(RELEASE_FIXTURE))
    release["assets"][0]["name"] = "ObsPlanner-0.2.1-Linux-x64.zip"
    assert updater.find_update(release, "0.2.0") is None

    release["assets"] = []
    assert updater.find_update(release, "0.2.0") is None

    assert updater.find_update({}, "0.2.0") is None


def test_fetch_latest_release_parses_the_github_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["accept"] = request.headers.get("Accept")
        captured["agent"] = request.headers.get("User-agent")
        return _FakeResponse(json.dumps(RELEASE_FIXTURE).encode("utf-8"))

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)

    release = updater.fetch_latest_release(timeout=5.0)

    assert release == RELEASE_FIXTURE
    assert captured["url"] == (
        "https://api.github.com/repos/jyshangguan/ObsPlanner/releases/latest"
    )
    assert captured["accept"] == "application/vnd.github+json"
    assert captured["agent"]


def test_download_file_verifies_size_and_digest(tmp_path):
    payload = b"obsplanner release bytes"
    source = tmp_path / "source.zip"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    destination = tmp_path / "updates" / "release.zip"
    progress_calls = []

    updater.download_file(
        source.as_uri(),
        destination,
        expected_size=len(payload),
        digest=f"sha256:{digest}",
        progress=lambda done, total: progress_calls.append((done, total)),
    )

    assert destination.read_bytes() == payload
    assert not destination.with_name(destination.name + ".part").exists()
    assert progress_calls == [(len(payload), len(payload))]


def test_download_file_rejects_a_bad_digest(tmp_path):
    source = tmp_path / "source.zip"
    source.write_bytes(b"obsplanner release bytes")
    destination = tmp_path / "release.zip"

    with pytest.raises(ValueError):
        updater.download_file(
            source.as_uri(),
            destination,
            expected_size=24,
            digest="sha256:" + "0" * 64,
        )

    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()


def test_download_file_rejects_a_wrong_size(tmp_path):
    source = tmp_path / "source.zip"
    source.write_bytes(b"obsplanner release bytes")
    destination = tmp_path / "release.zip"

    with pytest.raises(ValueError):
        updater.download_file(source.as_uri(), destination, expected_size=5)

    assert not destination.exists()


def test_update_request_round_trip(tmp_path):
    zip_path = tmp_path / "update.zip"
    app_path = tmp_path / "ObsPlanner.app"
    zip_path.touch()

    updater.write_update_request(
        tmp_path, zip_path, app_path, "0.2.1"
    )

    request = updater.read_update_request(tmp_path)
    assert request is not None
    assert request.zip_path == str(zip_path)
    assert request.app_path == str(app_path)
    assert request.target_version == "0.2.1"

    updater.clear_update_request(tmp_path)
    assert updater.read_update_request(tmp_path) is None


def test_read_update_request_ignores_corrupt_files(tmp_path):
    (tmp_path / updater.REQUEST_FILENAME).write_text("{not json", "utf-8")
    assert updater.read_update_request(tmp_path) is None


def _write_app_bundle(root: Path, name: str, marker: str) -> Path:
    bundle = root / name
    executable = bundle / "Contents" / "MacOS" / Path(name).stem
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(marker)
    (bundle / "Contents" / "Info.plist").write_text(f"<plist>{marker}</plist>")
    return bundle


def _write_release_zip(path: Path, marker: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "ObsPlanner.app/Contents/Info.plist", f"<plist>{marker}</plist>"
        )
        executable_info = zipfile.ZipInfo(
            "ObsPlanner.app/Contents/MacOS/ObsPlanner"
        )
        executable_info.external_attr = 0o100755 << 16
        archive.writestr(executable_info, marker)
        # Model the real bundle layout: Resources holds relative symlinks
        # into the sibling Frameworks directory.
        link_info = zipfile.ZipInfo("ObsPlanner.app/Contents/Resources/WebKit")
        link_info.external_attr = 0o120755 << 16
        archive.writestr(link_info, "../Frameworks/WebKit")
        archive.writestr(
            "ObsPlanner.app/Contents/Frameworks/WebKit/marker.txt", marker
        )
        archive.writestr("__MACOSX/ObsPlanner.app/._Contents", "junk")
        archive.writestr("ObsPlanner.app/._Info.plist", "junk")


def test_running_outside_a_frozen_app_is_not_updatable():
    assert updater.running_app_bundle() is None
    assert updater.is_updatable_app() is False


def test_apply_update_swaps_the_bundle_and_keeps_a_backup(tmp_path):
    import os
    import stat as stat_module

    current_app = _write_app_bundle(tmp_path, "ObsPlanner.app", "old build")
    release_zip = tmp_path / "release.zip"
    _write_release_zip(release_zip, "new build")
    extraction_root = tmp_path / "cache" / "updates"

    new_app = updater.apply_update(release_zip, current_app, extraction_root)

    assert new_app == current_app.resolve()
    new_executable = current_app / "Contents" / "MacOS" / "ObsPlanner"
    assert new_executable.read_text() == "new build"
    # Permissions, symlinks, and Finder junk are handled correctly.
    assert stat_module.S_IMODE(os.stat(new_executable).st_mode) & 0o111
    webkit_link = current_app / "Contents" / "Resources" / "WebKit"
    assert webkit_link.is_symlink()
    assert os.readlink(webkit_link) == "../Frameworks/WebKit"
    assert (webkit_link / "marker.txt").read_text() == "new build"
    assert not (current_app / "Contents" / "_Info.plist").exists()
    backups = list(tmp_path.glob(updater.BACKUP_PREFIX + "*"))
    assert len(backups) == 1
    assert (
        backups[0] / "Contents" / "MacOS" / "ObsPlanner"
    ).read_text() == "old build"
    # Extraction scratch space is cleaned up.
    assert not any(extraction_root.iterdir())


def test_extract_release_rejects_escaping_symlinks(tmp_path):
    release_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(release_zip, "w") as archive:
        link_info = zipfile.ZipInfo("ObsPlanner.app/Contents/Resources/evil")
        link_info.external_attr = 0o120755 << 16
        archive.writestr(link_info, "../../../../escape")

    with pytest.raises(ValueError):
        updater._extract_release(release_zip, tmp_path / "out")


def test_apply_update_rejects_an_archive_without_an_app(tmp_path):
    current_app = _write_app_bundle(tmp_path, "ObsPlanner.app", "old build")
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("README.txt", "no app here")

    with pytest.raises(ValueError):
        updater.apply_update(empty_zip, current_app, tmp_path / "cache")

    assert (
        current_app / "Contents" / "MacOS" / "ObsPlanner"
    ).read_text() == "old build"
    assert not list(tmp_path.glob(updater.BACKUP_PREFIX + "*"))


def test_apply_update_rejects_unsafe_archive_members(tmp_path):
    current_app = _write_app_bundle(tmp_path, "ObsPlanner.app", "old build")
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as archive:
        archive.writestr("../escape.txt", "evil")

    with pytest.raises(ValueError):
        updater.apply_update(evil_zip, current_app, tmp_path / "cache")

    assert (tmp_path / "escape.txt").exists() is False


def test_relaunch_app_requires_an_executable(tmp_path):
    bundle = tmp_path / "Fake.app"
    bundle.mkdir()
    with pytest.raises(ValueError):
        updater.relaunch_app(bundle)


def test_cleanup_old_backups_removes_only_backups(tmp_path):
    keep = _write_app_bundle(tmp_path, "ObsPlanner.app", "current")
    backup = tmp_path / (updater.BACKUP_PREFIX + "123")
    shutil.copytree(keep, backup)
    unrelated = _write_app_bundle(tmp_path, "Other.app", "keep me")

    updater.cleanup_old_backups(keep)

    assert keep.is_dir()
    assert unrelated.is_dir()
    assert not list(tmp_path.glob(updater.BACKUP_PREFIX + "*"))


def _wait_for_request_removal(data_dir: Path, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if updater.read_update_request(data_dir) is None:
            return
        time.sleep(0.05)
    pytest.fail("the watcher never removed the update request")


def test_update_watcher_applies_a_staged_request(tmp_path, monkeypatch):
    app_bundle = _write_app_bundle(tmp_path, "ObsPlanner.app", "old")
    zip_path = tmp_path / "update.zip"
    zip_path.touch()
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    applied = []
    exited = threading.Event()
    relaunched = []
    monkeypatch.setattr(
        updater, "relaunch_app", lambda app: relaunched.append(app)
    )

    def fake_applier(zip_arg, app_arg, extract_root):
        applied.append((zip_arg, app_arg, extract_root))
        return app_arg

    watcher = updater.UpdateWatcher(
        data_dir,
        app_bundle,
        cache_dir,
        exited.set,
        poll_interval_seconds=0.05,
        applier=fake_applier,
        version_of_running_app="0.2.0",
    )
    updater.write_update_request(data_dir, zip_path, app_bundle, "0.2.1")
    watcher.start()

    assert exited.wait(timeout=5.0), "watcher never applied the request"
    watcher.stop()

    assert applied == [
        (zip_path, app_bundle.resolve(), cache_dir / "updates")
    ]
    assert relaunched == [app_bundle.resolve()]
    assert updater.read_update_request(data_dir) is None


def test_update_watcher_discards_requests_for_other_apps(tmp_path):
    app_bundle = _write_app_bundle(tmp_path, "ObsPlanner.app", "old")
    zip_path = tmp_path / "update.zip"
    zip_path.touch()
    data_dir = tmp_path / "data"
    other_app = tmp_path / "Other.app"
    exited = threading.Event()

    watcher = updater.UpdateWatcher(
        data_dir,
        app_bundle,
        tmp_path / "cache",
        exited.set,
        poll_interval_seconds=0.05,
        applier=lambda *_: pytest.fail("applier must not run"),
        version_of_running_app="0.2.0",
    )
    updater.write_update_request(data_dir, zip_path, other_app, "0.2.1")
    watcher.start()
    _wait_for_request_removal(data_dir)
    watcher.stop()

    assert not exited.is_set()


def test_update_watcher_skips_stale_versions(tmp_path, monkeypatch):
    app_bundle = _write_app_bundle(tmp_path, "ObsPlanner.app", "old")
    zip_path = tmp_path / "update.zip"
    zip_path.touch()
    data_dir = tmp_path / "data"
    exited = threading.Event()
    monkeypatch.setattr(
        updater, "relaunch_app", lambda app: pytest.fail("no relaunch")
    )

    watcher = updater.UpdateWatcher(
        data_dir,
        app_bundle,
        tmp_path / "cache",
        exited.set,
        poll_interval_seconds=0.05,
        applier=lambda *_: pytest.fail("applier must not run"),
        version_of_running_app="0.2.1",
    )
    updater.write_update_request(data_dir, zip_path, app_bundle, "0.2.0")
    watcher.start()
    _wait_for_request_removal(data_dir)
    watcher.stop()

    assert not exited.is_set()


def test_update_watcher_survives_a_failing_applier(tmp_path):
    app_bundle = _write_app_bundle(tmp_path, "ObsPlanner.app", "old")
    zip_path = tmp_path / "update.zip"
    zip_path.touch()
    data_dir = tmp_path / "data"
    exited = threading.Event()

    def failing_applier(*_args):
        raise RuntimeError("swap failed")

    watcher = updater.UpdateWatcher(
        data_dir,
        app_bundle,
        tmp_path / "cache",
        exited.set,
        poll_interval_seconds=0.05,
        applier=failing_applier,
        version_of_running_app="0.2.0",
    )
    updater.write_update_request(data_dir, zip_path, app_bundle, "0.2.1")
    watcher.start()
    _wait_for_request_removal(data_dir)
    watcher.stop()

    # The failed update is dropped instead of retried forever, and the
    # old app keeps running.
    assert not exited.is_set()
    assert (
        app_bundle / "Contents" / "MacOS" / "ObsPlanner"
    ).read_text() == "old"
