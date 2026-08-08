from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from endless_vgm.library import MusicLibrary, playlist_fingerprint, run_command_with_progress


def playlist_payload(audio_path: str) -> list[dict[str, object]]:
    return [
        {
            "name": "GAME",
            "tracks": [
                {
                    "name": "Opening",
                    "artist": "Composer",
                    "album_artist": "Various",
                    "album": "Known Album",
                    "location": audio_path,
                }
            ],
        }
    ]


def test_loads_export_cache_and_builds_public_urls(tmp_path) -> None:
    audio = tmp_path / "opening.m4a"
    audio.write_bytes(b"audio")
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps(playlist_payload(str(audio))), encoding="utf-8")
    library = MusicLibrary(cache, tmp_path / "export.js", fallback_cache_path=tmp_path / "none")

    library.load()

    playlist = library.playlist("GAME")
    assert playlist is not None
    assert playlist.summary_dict() == {
        "name": "GAME",
        "trackCount": 1,
        "availableTrackCount": 1,
        "isLibrary": False,
    }
    track = playlist.tracks[0]
    assert track.name == "Opening"
    assert track.available is True
    assert len(track.id) == 24
    assert track.public_dict()["audioUrl"] == f"api/tracks/{track.id}/audio"
    assert library.track(track.id) == track


def test_loads_music_bridge_cache_wrapper(tmp_path) -> None:
    fallback = tmp_path / "music-bridge.json"
    fallback.write_text(
        json.dumps(
            {
                "playlists": {
                    "GAME": {
                        "playlist": {
                            "name": "GAME",
                            "tracks": [{"name": "Missing", "location": ""}],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    library = MusicLibrary(tmp_path / "none", tmp_path / "export.js", fallback_cache_path=fallback)

    library.load()

    playlist = library.playlist("GAME")
    assert playlist is not None
    assert playlist.tracks[0].available is False
    assert playlist.tracks[0].public_dict()["artworkUrl"] is None


def test_loads_playlist_with_null_tracks_as_empty(tmp_path) -> None:
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps([{"name": "Favorites", "tracks": None}]), encoding="utf-8")
    library = MusicLibrary(cache, tmp_path / "export.js", fallback_cache_path=tmp_path / "none")

    library.load()

    playlist = library.playlist("Favorites")
    assert playlist is not None
    assert playlist.tracks == ()


def test_marks_music_library_as_all_tracks_playlist(tmp_path) -> None:
    cache = tmp_path / "library.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "name": "すべての楽曲",
                    "is_library": True,
                    "tracks": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    library = MusicLibrary(cache, tmp_path / "export.js", fallback_cache_path=tmp_path / "none")

    library.load()

    playlist = library.playlist("すべての楽曲")
    assert playlist is not None
    assert playlist.is_library is True
    assert playlist.summary_dict()["isLibrary"] is True


def test_infers_disc_and_track_numbers_from_filename(tmp_path) -> None:
    audio = tmp_path / "2-07 Battle.m4a"
    audio.write_bytes(b"audio")
    cache = tmp_path / "library.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "name": "GAME",
                    "tracks": [
                        {
                            "name": "Battle",
                            "album": "Album",
                            "location": str(audio),
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    library = MusicLibrary(cache, tmp_path / "export.js", fallback_cache_path=tmp_path / "none")

    library.load()

    track = library.playlist("GAME").tracks[0]
    assert track.disc_number == 2
    assert track.track_number == 7


def test_load_or_refresh_exports_on_clean_install(tmp_path) -> None:
    audio = tmp_path / "track.aac"
    audio.write_bytes(b"audio")
    payload = playlist_payload(str(audio))
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    library = MusicLibrary(
        tmp_path / "cache" / "library.json",
        tmp_path / "export.js",
        fallback_cache_path=tmp_path / "missing",
        command_runner=runner,
    )

    library.load_or_refresh()

    assert len(calls) == 1
    assert library.playlist("GAME") is not None


def test_load_or_refresh_uses_existing_cache_without_blocking_startup(tmp_path) -> None:
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps(playlist_payload("")), encoding="utf-8")
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        fallback_cache_path=tmp_path / "none",
        command_runner=runner,
    )

    library.load_or_refresh()

    assert calls == []
    assert library.playlist("GAME") is not None


def test_reload_if_changed_replaces_in_memory_library(tmp_path) -> None:
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps(playlist_payload("")), encoding="utf-8")
    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        fallback_cache_path=tmp_path / "none",
    )
    library.load()
    original_mtime = cache.stat().st_mtime_ns
    cache.write_text(
        json.dumps([{"name": "UPDATED", "tracks": []}]),
        encoding="utf-8",
    )
    os.utime(cache, ns=(original_mtime + 1, original_mtime + 1))

    assert library.reload_if_changed() is True
    assert library.playlist("GAME") is None
    assert library.playlist("UPDATED") is not None
    assert library.reload_if_changed() is False


def test_refresh_runs_export_and_replaces_cache(tmp_path) -> None:
    audio = tmp_path / "track.aac"
    audio.write_bytes(b"audio")
    payload = playlist_payload(str(audio))
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    cache = tmp_path / "cache" / "library.json"
    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        fallback_cache_path=tmp_path / "none",
        command_runner=runner,
    )

    library.refresh()

    assert calls == [["osascript", "-l", "JavaScript", str(tmp_path / "export.js")]]
    assert cache.is_file()
    assert library.playlist("GAME") is not None


def test_refresh_reports_music_export_error(tmp_path) -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "Music access denied")

    library = MusicLibrary(
        tmp_path / "library.json",
        tmp_path / "export.js",
        fallback_cache_path=tmp_path / "none",
        command_runner=runner,
    )

    with pytest.raises(RuntimeError, match="Music access denied"):
        library.refresh()


def test_refresh_can_stream_progress_to_terminal(tmp_path) -> None:
    received: dict[str, object] = {}

    def progress_runner(
        command: list[str],
        **options: object,
    ) -> subprocess.CompletedProcess[str]:
        received.update(options)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        tmp_path / "library.json",
        tmp_path / "export.js",
        fallback_cache_path=tmp_path / "none",
        progress_runner=progress_runner,
    )

    library.refresh(show_progress=True)

    assert received["timeout"] == 3600
    assert received["log_path"] is None


def test_progress_runner_renders_carriage_return_eta_and_writes_log(
    capsys,
    tmp_path,
) -> None:
    log_path = tmp_path / "refresh.log"
    completed = run_command_with_progress(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('進捗 0%: 準備中', file=sys.stderr); "
                "print('進捗 50.5%: 5 / 10曲', file=sys.stderr); "
                "print('進捗 100%: 完了', file=sys.stderr); "
                "print('[]')"
            ),
        ],
        timeout=10,
        log_path=log_path,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "[]"
    terminal = capsys.readouterr().out
    assert "\r進捗 50.5%: 5 / 10曲 | ETA " in terminal
    assert "\r進捗 100%: 完了 | ETA 00:00" in terminal
    saved = log_path.read_text(encoding="utf-8")
    assert "\r" not in saved
    assert "進捗 0%: 準備中\n" in saved
    assert "進捗 50.5%: 5 / 10曲\n" in saved
    assert "進捗 100%: 完了\n" in saved


def _manifest_runner(payload: list[dict[str, object]]):
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return runner


def test_playlist_fingerprint_normalizes_playlist_order() -> None:
    manifest = [
        {"id": "P2", "name": "Beta", "tracks": ["T3"]},
        {"id": "P1", "name": "Alpha", "tracks": ["T1", "T2"]},
    ]
    reversed_manifest = list(reversed(manifest))
    assert playlist_fingerprint(manifest) == playlist_fingerprint(reversed_manifest)
    assert len(playlist_fingerprint(manifest)) == 64


def test_playlist_fingerprint_detects_structural_changes() -> None:
    base = [{"id": "P1", "name": "Alpha", "tracks": ["T1", "T2"]}]
    fingerprint = playlist_fingerprint(base)
    changes = {
        "add track": [{"id": "P1", "name": "Alpha", "tracks": ["T1", "T2", "T3"]}],
        "remove track": [{"id": "P1", "name": "Alpha", "tracks": ["T1"]}],
        "reorder tracks": [{"id": "P1", "name": "Alpha", "tracks": ["T2", "T1"]}],
        "same-count swap": [{"id": "P1", "name": "Alpha", "tracks": ["T1", "T9"]}],
        "rename": [{"id": "P1", "name": "Alpha2", "tracks": ["T1", "T2"]}],
        "add playlist": [base[0], {"id": "P2", "name": "Beta", "tracks": []}],
        "remove playlist": [],
    }
    for label, changed in changes.items():
        assert playlist_fingerprint(changed) != fingerprint, label


def test_playlist_fingerprint_ignores_metadata_only_changes() -> None:
    # The manifest carries no metadata, so a metadata-only edit (e.g. album tag)
    # produces an identical fingerprint and is intentionally not detected.
    manifest = [{"id": "P1", "name": "Alpha", "tracks": ["T1"]}]
    assert playlist_fingerprint([manifest[0]]) == playlist_fingerprint(
        [{"id": "P1", "name": "Alpha", "tracks": ["T1"]}]
    )


def test_read_manifest_returns_parsed_playlists(tmp_path) -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["A", "B"]}]
    library = MusicLibrary(
        tmp_path / "library.json",
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        manifest_runner=_manifest_runner(manifest),
    )

    assert library.read_manifest() == manifest


def test_read_manifest_raises_on_osascript_failure(tmp_path) -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "Music access denied")

    library = MusicLibrary(
        tmp_path / "library.json",
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        manifest_runner=runner,
    )

    with pytest.raises(RuntimeError, match="Music access denied"):
        library.read_manifest()


def _sidecar(cache: Path) -> Path:
    return cache.with_suffix(cache.suffix + ".fingerprint")


def test_refresh_writes_fingerprint_sidecar_and_keeps_cache_bare(tmp_path) -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    export_payload = [{"name": "GAME", "tracks": [{"name": "Opening"}]}]

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(export_payload), "")

    cache = tmp_path / "library.json"
    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner(manifest),
    )

    library.refresh()

    # library.json keeps its original bare-list format (no fingerprint key).
    assert json.loads(cache.read_text(encoding="utf-8")) == export_payload
    # the fingerprint lives in the sidecar, written atomically alongside it.
    assert _sidecar(cache).read_text(encoding="utf-8").strip() == playlist_fingerprint(manifest)


def test_refresh_skips_when_sidecar_matches_fingerprint(tmp_path) -> None:
    # Another process already refreshed the cache to fingerprint F (e.g. manual
    # `make library` finished while we waited for the lock). With F in the sidecar
    # and matching data on disk, refresh(fingerprint=F) skips the export.
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    fingerprint = playlist_fingerprint(manifest)
    cache = tmp_path / "library.json"
    cache.write_text(
        json.dumps([{"name": "GAME", "tracks": [{"name": "Opening"}]}]), encoding="utf-8"
    )
    _sidecar(cache).write_text(fingerprint, encoding="utf-8")
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
    )

    library.refresh(fingerprint=fingerprint)

    assert export_calls == []
    assert library.playlist("GAME") is not None


def test_missing_sidecar_fails_open_and_refreshes(tmp_path) -> None:
    # No sidecar => we cannot prove the cache already matches, so refresh must
    # run (an extra refresh is acceptable) instead of skipping (a missed update
    # is not). This is the crash-window recovery case.
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    fingerprint = playlist_fingerprint(manifest)
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps([{"name": "OLD", "tracks": []}]), encoding="utf-8")
    # NOTE: no sidecar written.
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_calls.append(command)
        payload = json.dumps([{"name": "GAME", "tracks": []}])
        return subprocess.CompletedProcess(command, 0, payload, "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner(manifest),
    )

    library.refresh(fingerprint=fingerprint)

    assert export_calls != []
    assert _sidecar(cache).read_text(encoding="utf-8").strip() == fingerprint


def test_corrupt_sidecar_fails_open(tmp_path) -> None:
    fingerprint = playlist_fingerprint([{"id": "P1", "name": "GAME", "tracks": ["T1"]}])
    cache = tmp_path / "library.json"
    cache.write_text("[]", encoding="utf-8")
    _sidecar(cache).write_text("NOT-A-FINGERPRINT", encoding="utf-8")
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner([]),
    )

    library.refresh(fingerprint=fingerprint)

    assert export_calls != []


def test_stale_sidecar_does_not_skip_for_different_fingerprint(tmp_path) -> None:
    old = playlist_fingerprint([{"id": "P1", "name": "OLD", "tracks": ["T1"]}])
    new = playlist_fingerprint([{"id": "P1", "name": "NEW", "tracks": ["T1", "T2"]}])
    cache = tmp_path / "library.json"
    cache.write_text("[]", encoding="utf-8")
    _sidecar(cache).write_text(old, encoding="utf-8")
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner([]),
    )

    library.refresh(fingerprint=new)

    assert export_calls != []


def test_refresh_invalidates_sidecar_before_export(tmp_path) -> None:
    # The sidecar is invalidated before the export runs, so a stale value can
    # never accompany fresh data even mid-refresh. The export runner observes an
    # empty sidecar; the matching fingerprint is only (re)published afterwards.
    old_manifest = [{"id": "P0", "name": "OLD", "tracks": ["T0"]}]
    new_manifest = [{"id": "P1", "name": "NEW", "tracks": ["T1"]}]
    new_fingerprint = playlist_fingerprint(new_manifest)
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps([{"name": "OLD", "tracks": []}]), encoding="utf-8")
    _sidecar(cache).write_text(playlist_fingerprint(old_manifest), encoding="utf-8")
    observed: dict[str, str] = {}

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        observed["during_export"] = _sidecar(cache).read_text(encoding="utf-8").strip()
        return subprocess.CompletedProcess(
            command, 0, json.dumps([{"name": "NEW", "tracks": []}]), ""
        )

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner(new_manifest),
    )

    library.refresh(fingerprint=new_fingerprint)

    assert observed["during_export"] == ""
    assert _sidecar(cache).read_text(encoding="utf-8").strip() == new_fingerprint


def test_corrupt_library_json_forces_refresh_even_with_matching_sidecar(tmp_path) -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    fingerprint = playlist_fingerprint(manifest)
    cache = tmp_path / "library.json"
    cache.write_text("NOT-VALID-JSON", encoding="utf-8")
    _sidecar(cache).write_text(fingerprint, encoding="utf-8")
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner(manifest),
    )

    library.refresh(fingerprint=fingerprint)

    assert export_calls != []  # corrupt data => skip disallowed


def test_missing_library_json_forces_refresh_even_with_matching_sidecar(tmp_path) -> None:
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    fingerprint = playlist_fingerprint(manifest)
    cache = tmp_path / "library.json"
    # NOTE: no library.json on disk, yet the sidecar claims it is current.
    _sidecar(cache).write_text(fingerprint, encoding="utf-8")
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner(manifest),
    )

    library.refresh(fingerprint=fingerprint)

    assert export_calls != []  # missing data => skip disallowed


def test_manifest_failure_during_refresh_leaves_empty_sidecar(tmp_path) -> None:
    # Manual refresh (fingerprint=None) whose manifest read fails must not publish
    # a fingerprint for the freshly written data; the sidecar stays empty so the
    # next caller fail-opens instead of falsely skipping against stale data.
    old_fingerprint = playlist_fingerprint([{"id": "P0", "name": "OLD", "tracks": ["T0"]}])
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps([{"name": "OLD", "tracks": []}]), encoding="utf-8")
    _sidecar(cache).write_text(old_fingerprint, encoding="utf-8")

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, json.dumps([{"name": "NEW", "tracks": []}]), ""
        )

    def failing_manifest(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "manifest unavailable")

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=failing_manifest,
    )

    library.refresh()

    assert json.loads(cache.read_text(encoding="utf-8")) == [{"name": "NEW", "tracks": []}]
    assert _sidecar(cache).read_text(encoding="utf-8").strip() == ""


def test_sidecar_publish_failure_leaves_empty_sidecar_and_keeps_data(tmp_path) -> None:
    # If publishing the sidecar fails after the data is durable, the sidecar was
    # already invalidated, so it stays empty: refresh does not raise and the next
    # caller fail-opens rather than false-skipping against stale data.
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    fingerprint = playlist_fingerprint(manifest)
    cache = tmp_path / "library.json"
    cache.write_text(json.dumps([{"name": "OLD", "tracks": []}]), encoding="utf-8")

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, json.dumps([{"name": "NEW", "tracks": []}]), ""
        )

    library = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=export_runner,
        manifest_runner=_manifest_runner(manifest),
    )
    real_atomic_write = library._atomic_write_text
    call_count = {"n": 0}

    def flaky_atomic_write(path: Path, content: str) -> None:
        call_count["n"] += 1
        # Call order: invalidate(1), library.json(2), publish(3).
        if call_count["n"] == 3:
            raise OSError("publish failed")
        real_atomic_write(path, content)

    library._atomic_write_text = flaky_atomic_write  # type: ignore[method-assign]
    try:
        library.refresh(fingerprint=fingerprint)
    finally:
        library._atomic_write_text = real_atomic_write  # type: ignore[method-assign]

    assert json.loads(cache.read_text(encoding="utf-8")) == [{"name": "NEW", "tracks": []}]
    assert _sidecar(cache).read_text(encoding="utf-8").strip() == ""


def test_refresh_serializes_concurrent_calls_via_file_lock(tmp_path) -> None:
    cache = tmp_path / "library.json"
    active = {"count": 0, "max": 0}
    guard = threading.Lock()
    export_calls: list[list[str]] = []

    def export_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        with guard:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            export_calls.append(command)
        time.sleep(0.1)
        with guard:
            active["count"] -= 1
        return subprocess.CompletedProcess(command, 0, "[]", "")

    libraries = [
        MusicLibrary(
            cache,
            tmp_path / "export.js",
            manifest_script=tmp_path / "manifest.js",
            command_runner=export_runner,
            manifest_runner=_manifest_runner([]),
        )
        for _ in range(2)
    ]

    threads = [threading.Thread(target=library.refresh) for library in libraries]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert active["max"] == 1
    assert len(export_calls) == 2
    assert cache.is_file()


def test_refresh_skip_lets_manual_and_watchdog_share_one_lock(tmp_path) -> None:
    # Manual refresh (no fingerprint) runs a slow export and records fingerprint F
    # in the sidecar. The watchdog then calls refresh(fingerprint=F); it acquires
    # the shared lock after the manual one releases, sees F in the sidecar, and
    # skips its own export.
    manifest = [{"id": "P1", "name": "GAME", "tracks": ["T1"]}]
    fingerprint = playlist_fingerprint(manifest)
    cache = tmp_path / "library.json"
    export_started = threading.Event()
    release_export = threading.Event()
    watchdog_export_calls: list[list[str]] = []

    def manual_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        export_started.set()
        release_export.wait(timeout=5)
        return subprocess.CompletedProcess(
            command, 0, json.dumps([{"name": "GAME", "tracks": [{"name": "Opening"}]}]), ""
        )

    def watchdog_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        watchdog_export_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    manual = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=manual_runner,
        manifest_runner=_manifest_runner(manifest),
    )
    watchdog = MusicLibrary(
        cache,
        tmp_path / "export.js",
        manifest_script=tmp_path / "manifest.js",
        command_runner=watchdog_runner,
        manifest_runner=_manifest_runner(manifest),
    )
    results: dict[str, str] = {}

    def run_manual() -> None:
        try:
            manual.refresh()
            results["manual"] = "ok"
        except Exception as error:  # noqa: BLE001
            results["manual"] = repr(error)

    def run_watchdog() -> None:
        export_started.wait(timeout=5)
        try:
            watchdog.refresh(fingerprint=fingerprint)
            results["watchdog"] = "ok"
        except Exception as error:  # noqa: BLE001
            results["watchdog"] = repr(error)

    manual_thread = threading.Thread(target=run_manual)
    watchdog_thread = threading.Thread(target=run_watchdog)
    manual_thread.start()
    watchdog_thread.start()
    time.sleep(0.3)  # let the watchdog block on the shared lock
    release_export.set()
    manual_thread.join(timeout=5)
    watchdog_thread.join(timeout=5)

    assert results.get("manual") == "ok"
    assert results.get("watchdog") == "ok"
    assert watchdog_export_calls == []
    assert _sidecar(cache).read_text(encoding="utf-8").strip() == fingerprint
