from __future__ import annotations

import json
import logging
import mimetypes
import re
import shutil
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .analysis import LoopAnalyzer
from .artwork import ArtworkExporter, artwork_content_type
from .library import MusicLibrary

LOGGER = logging.getLogger(__name__)
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


@dataclass(frozen=True)
class PlayerApplication:
    library: MusicLibrary
    analyzer: LoopAnalyzer
    artwork: ArtworkExporter
    static_dir: Path


class PlayerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], app: PlayerApplication) -> None:
        self.app = app
        super().__init__(address, PlayerRequestHandler)


class PlayerRequestHandler(BaseHTTPRequestHandler):
    server: PlayerServer

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except Exception as error:  # noqa: BLE001
            LOGGER.exception("GET %s failed", self.path)
            self._send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_HEAD(self) -> None:
        try:
            self._handle_get(head_only=True)
        except Exception as error:  # noqa: BLE001
            LOGGER.exception("HEAD %s failed", self.path)
            self._send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        try:
            self._handle_post()
        except FileNotFoundError as error:
            self._send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except (RuntimeError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # noqa: BLE001
            LOGGER.exception("POST %s failed", self.path)
            self._send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format_: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.client_address[0], format_ % args)

    def _handle_get(self, *, head_only: bool = False) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/status":
            self._send_json(
                {
                    "ready": True,
                    "playlistCount": len(self.server.app.library.playlists()),
                    "pymusiclooperAvailable": shutil.which("pymusiclooper") is not None,
                    "ffmpegAvailable": shutil.which("ffmpeg") is not None,
                    "ffprobeAvailable": shutil.which("ffprobe") is not None,
                },
                head_only=head_only,
            )
            return
        if parsed.path == "/api/playlists":
            playlists = [
                playlist.summary_dict() for playlist in self.server.app.library.playlists()
            ]
            self._send_json({"playlists": playlists}, head_only=head_only)
            return
        if parsed.path == "/api/playlist":
            name = parse_qs(parsed.query).get("name", [""])[0]
            playlist = self.server.app.library.playlist(name)
            if playlist is None:
                self._send_json({"error": "Playlist not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(
                {
                    "name": playlist.name,
                    "tracks": [track.public_dict() for track in playlist.tracks],
                },
                head_only=head_only,
            )
            return
        track_route = _track_route(parsed.path)
        if track_route is not None:
            track_id, action = track_route
            track = self.server.app.library.track(track_id)
            if track is None:
                self._send_json({"error": "Track not found"}, HTTPStatus.NOT_FOUND)
                return
            if action == "audio":
                if not track.available or track.location is None:
                    self._send_json({"error": "Audio file is unavailable"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_file(track.location, allow_range=True, head_only=head_only)
                return
            if action == "artwork":
                artwork = self.server.app.artwork.artwork(track)
                if artwork is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_file(
                    artwork,
                    content_type=artwork_content_type(artwork),
                    head_only=head_only,
                )
                return
        self._send_static(parsed.path, head_only=head_only)

    def _handle_post(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/library/refresh":
            self.server.app.library.refresh()
            self._send_json(
                {
                    "playlistCount": len(self.server.app.library.playlists()),
                    "refreshed": True,
                }
            )
            return
        track_route = _track_route(parsed.path)
        if track_route is not None and track_route[1] == "analyze":
            track = self.server.app.library.track(track_route[0])
            if track is None:
                raise FileNotFoundError("Track not found")
            self._send_json(self.server.app.analyzer.analyze(track))
            return
        self._send_json({"error": "Endpoint not found"}, HTTPStatus.NOT_FOUND)

    def _send_static(self, request_path: str, *, head_only: bool) -> None:
        relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
        candidate = (self.server.app.static_dir / relative).resolve()
        static_root = self.server.app.static_dir.resolve()
        if static_root not in candidate.parents and candidate != static_root:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            candidate = static_root / "index.html"
        self._send_file(candidate, head_only=head_only, cache_control="no-cache")

    def _send_json(
        self,
        payload: object,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        head_only: bool = False,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _send_file(
        self,
        path: Path,
        *,
        content_type: str | None = None,
        allow_range: bool = False,
        head_only: bool = False,
        cache_control: str = "private, max-age=86400",
    ) -> None:
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        if allow_range and (range_header := self.headers.get("Range")):
            parsed_range = _parse_range(range_header, size)
            if parsed_range is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            start, end = parsed_range
            status = HTTPStatus.PARTIAL_CONTENT
        length = max(end - start + 1, 0)
        self.send_response(status)
        self.send_header(
            "Content-Type",
            content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache_control)
        if allow_range:
            self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head_only:
            return
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining > 0:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def _track_route(path: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"/api/tracks/([0-9a-f]{24})/(audio|artwork|analyze)", path)
    return (match.group(1), match.group(2)) if match else None


def _parse_range(value: str, size: int) -> tuple[int, int] | None:
    match = RANGE_PATTERN.fullmatch(value.strip())
    if match is None or size <= 0:
        return None
    start_value, end_value = match.groups()
    if not start_value:
        if not end_value:
            return None
        suffix = int(end_value)
        if suffix <= 0:
            return None
        return max(size - suffix, 0), size - 1
    start = int(start_value)
    end = int(end_value) if end_value else size - 1
    if start >= size or start > end:
        return None
    return start, min(end, size - 1)
