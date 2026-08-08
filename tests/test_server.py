from __future__ import annotations

import contextlib
import http.client
import json
import os
import socket
import threading

from endless_vgm.library import MusicLibrary
from endless_vgm.server import (
    PlayerApplication,
    PlayerUnixServer,
    _parse_range,
    _track_route,
)


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def analyze(self, track, *, force: bool = False) -> dict[str, object]:
        self.calls.append((track.id, force))
        return {"trackId": track.id, "candidateCount": 0, "candidates": []}


class FakeArtwork:
    def artwork(self, track):
        return None


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str) -> None:
        super().__init__("localhost")
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


def request(
    socket_path: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, http.client.HTTPMessage]:
    connection = UnixHTTPConnection(socket_path)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read(), response.headers
    finally:
        connection.close()


def request_json(socket_path: str, path: str, *, method: str = "GET") -> dict[str, object]:
    status, body, _ = request(socket_path, path, method=method)
    assert status == 200
    return json.loads(body)


def test_range_parser() -> None:
    assert _parse_range("bytes=0-4", 10) == (0, 4)
    assert _parse_range("bytes=5-", 10) == (5, 9)
    assert _parse_range("bytes=-3", 10) == (7, 9)
    assert _parse_range("bytes=20-30", 10) is None
    assert _parse_range("invalid", 10) is None


def test_track_route() -> None:
    track_id = "a" * 24
    assert _track_route(f"/api/tracks/{track_id}/audio") == (track_id, "audio")
    assert _track_route(f"/api/tracks/{track_id}/reanalyze") == (
        track_id,
        "reanalyze",
    )
    assert _track_route("/api/tracks/not-an-id/audio") is None


def test_http_api_over_local_web_socket(tmp_path) -> None:
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
    library = MusicLibrary(cache, tmp_path / "export.js", fallback_cache_path=tmp_path / "none")
    library.load()
    analyzer = FakeAnalyzer()
    app = PlayerApplication(
        library=library,
        analyzer=analyzer,
        artwork=FakeArtwork(),
    )
    socket_path = f"/tmp/endless-vgm-test-{os.getpid()}.sock"
    with contextlib.suppress(FileNotFoundError):
        os.unlink(socket_path)
    server = PlayerUnixServer(socket_path, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        playlists = request_json(socket_path, "/api/playlists")
        assert playlists["playlists"][0]["name"] == "GAME"
        assert playlists["playlists"][0]["isLibrary"] is False
        playlist = request_json(socket_path, "/api/playlist?name=GAME")
        track = playlist["tracks"][0]
        assert track["name"] == "Track"
        assert playlist["albums"][0]["trackIds"] == [track["id"]]
        analysis = request_json(
            socket_path,
            f"/api/tracks/{track['id']}/analyze",
            method="POST",
        )
        assert analysis["candidateCount"] == 0
        request_json(
            socket_path,
            f"/api/tracks/{track['id']}/reanalyze",
            method="POST",
        )
        assert analyzer.calls == [(track["id"], False), (track["id"], True)]

        status, body, headers = request(
            socket_path,
            f"/{track['audioUrl']}",
            headers={"Range": "bytes=2-5"},
        )
        assert status == 206
        assert body == b"2345"
        assert headers["Content-Range"] == "bytes 2-5/10"

        status, _, _ = request(socket_path, "/api/playlist?name=UNKNOWN")
        assert status == 404

        status, _, _ = request(socket_path, "/missing-route")
        assert status == 404

        original_mtime = cache.stat().st_mtime_ns
        cache.write_text(
            json.dumps([{"name": "UPDATED", "tracks": []}]),
            encoding="utf-8",
        )
        os.utime(cache, ns=(original_mtime + 1, original_mtime + 1))
        updated = request_json(socket_path, "/api/playlists")
        assert [item["name"] for item in updated["playlists"]] == ["UPDATED"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(socket_path)
