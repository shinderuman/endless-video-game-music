from __future__ import annotations

import json
import subprocess

from endless_vgm.library import MusicLibrary


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
    assert track.public_dict()["audioUrl"] == f"/api/tracks/{track.id}/audio"
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
