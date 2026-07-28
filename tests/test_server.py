from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from endless_vgm.library import MusicLibrary
from endless_vgm.server import (
    PlayerApplication,
    PlayerServer,
    _parse_range,
    _track_route,
)


class FakeAnalyzer:
    def analyze(self, track) -> dict[str, object]:
        return {"trackId": track.id, "candidateCount": 0, "candidates": []}


class FakeArtwork:
    def artwork(self, track):
        return None


def request_json(url: str, *, method: str = "GET") -> dict[str, object]:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def test_range_parser() -> None:
    assert _parse_range("bytes=0-4", 10) == (0, 4)
    assert _parse_range("bytes=5-", 10) == (5, 9)
    assert _parse_range("bytes=-3", 10) == (7, 9)
    assert _parse_range("bytes=20-30", 10) is None
    assert _parse_range("invalid", 10) is None


def test_track_route() -> None:
    track_id = "a" * 24
    assert _track_route(f"/api/tracks/{track_id}/audio") == (track_id, "audio")
    assert _track_route("/api/tracks/not-an-id/audio") is None


def test_http_api_static_and_audio_range(tmp_path) -> None:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"0123456789")
    cache = tmp_path / "library.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "name": "GAME",
                    "tracks": [
                        {
                            "name": "Track",
                            "artist": "Artist",
                            "album": "Album",
                            "location": str(audio),
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Endless</h1>", encoding="utf-8")
    library = MusicLibrary(cache, tmp_path / "export.js", fallback_cache_path=tmp_path / "none")
    library.load()
    app = PlayerApplication(
        library=library,
        analyzer=FakeAnalyzer(),
        artwork=FakeArtwork(),
        static_dir=static,
    )
    server = PlayerServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        playlists = request_json(f"{base}/api/playlists")
        assert playlists["playlists"][0]["name"] == "GAME"
        playlist = request_json(f"{base}/api/playlist?name=GAME")
        track = playlist["tracks"][0]
        assert track["name"] == "Track"
        analysis = request_json(
            f"{base}/api/tracks/{track['id']}/analyze",
            method="POST",
        )
        assert analysis["candidateCount"] == 0

        range_request = urllib.request.Request(
            f"{base}{track['audioUrl']}",
            headers={"Range": "bytes=2-5"},
        )
        with urllib.request.urlopen(range_request) as response:
            assert response.status == 206
            assert response.read() == b"2345"
            assert response.headers["Content-Range"] == "bytes 2-5/10"

        with urllib.request.urlopen(f"{base}/missing-route") as response:
            assert b"Endless" in response.read()
            assert response.headers["Cache-Control"] == "no-cache"

        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{base}/api/playlist?name=UNKNOWN")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
