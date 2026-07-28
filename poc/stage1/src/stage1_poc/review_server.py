from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from stage1_poc.runner import atomic_write_json, write_review_csv

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_LABELS = {"loop", "non_loop", "loop_bad_points", None}


class ReviewStore:
    def __init__(self, analysis_path: Path, review_path: Path) -> None:
        self.analysis_path = analysis_path
        self.review_path = review_path
        self.lock = threading.Lock()
        self.state = json.loads(analysis_path.read_text(encoding="utf-8"))
        if not isinstance(self.state.get("tracks"), list):
            raise ValueError("analysis JSON does not contain a tracks list")

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            tracks = [self._public_track(index, track) for index, track in enumerate(self.tracks)]
        return {
            "sampleSeed": self.state.get("sampleSeed"),
            "pymusiclooperVersion": self.state.get("pymusiclooperVersion"),
            "tracks": tracks,
            "summary": self._summary(tracks),
        }

    def set_label(self, index: int, label: str | None) -> dict[str, Any]:
        if label not in ALLOWED_LABELS:
            raise ValueError("label must be loop, non_loop, loop_bad_points, or null")
        with self.lock:
            if index < 0 or index >= len(self.tracks):
                raise IndexError("track index is out of range")
            self.tracks[index]["userLabel"] = label
            atomic_write_json(self.analysis_path, self.state)
            write_review_csv(self.review_path, self.tracks)
            return self._public_track(index, self.tracks[index])

    def source_path(self, index: int) -> Path:
        with self.lock:
            if index < 0 or index >= len(self.tracks):
                raise IndexError("track index is out of range")
            source = Path(self.tracks[index]["sourcePath"])
        if not source.is_file():
            raise FileNotFoundError(source)
        return source

    @property
    def tracks(self) -> list[dict[str, Any]]:
        return self.state["tracks"]

    @staticmethod
    def _public_track(index: int, track: dict[str, Any]) -> dict[str, Any]:
        sample_rate = track.get("sampleRate")
        loop_start = track.get("loopStartSample")
        loop_end = track.get("loopEndSample")
        return {
            "index": index,
            "title": track.get("title"),
            "artist": track.get("artist"),
            "album": track.get("album"),
            "evaluationGroup": track.get("evaluationGroup"),
            "sourceFile": Path(track.get("sourcePath", "")).name,
            "analysisStatus": track.get("analysisStatus"),
            "scoreRaw": track.get("scoreRaw"),
            "loopStartSeconds": loop_start / sample_rate if loop_start is not None else None,
            "loopEndSeconds": loop_end / sample_rate if loop_end is not None else None,
            "audioDurationSeconds": track.get("audioDurationSeconds"),
            "userLabel": track.get("userLabel"),
        }

    @staticmethod
    def _summary(tracks: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "total": len(tracks),
            "labeled": sum(track["userLabel"] is not None for track in tracks),
            "loop": sum(track["userLabel"] == "loop" for track in tracks),
            "nonLoop": sum(track["userLabel"] == "non_loop" for track in tracks),
            "loopBadPoints": sum(track["userLabel"] == "loop_bad_points" for track in tracks),
        }


def parse_byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header:
        return None
    if not header.startswith("bytes=") or "," in header:
        raise ValueError("unsupported range")
    start_text, end_text = header[6:].split("-", maxsplit=1)
    if not start_text:
        length = int(end_text)
        if length <= 0:
            raise ValueError("invalid suffix range")
        return max(size - length, 0), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError("range is outside the file")
    return start, min(end, size - 1)


def handler_for(store: ReviewStore) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            if route == "/api/review":
                self._send_json(store.snapshot())
                return
            if route.startswith("/audio/"):
                self._send_audio(route)
                return
            self._send_static(route)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/label":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                track = store.set_label(int(payload["index"]), payload.get("label"))
            except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(track)

        def _send_json(
            self,
            payload: dict[str, Any],
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, route: str) -> None:
            names = {
                "/": "review.html",
                "/review.css": "review.css",
                "/review.js": "review.js",
            }
            name = names.get(route)
            if name is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            path = STATIC_DIR / name
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_audio(self, route: str) -> None:
            try:
                index = int(route.removeprefix("/audio/"))
                path = store.source_path(index)
                byte_range = parse_byte_range(self.headers.get("Range"), path.stat().st_size)
            except (FileNotFoundError, IndexError, ValueError):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._stream_file(path, byte_range)

        def _stream_file(self, path: Path, byte_range: tuple[int, int] | None) -> None:
            size = path.stat().st_size
            start, end = byte_range or (0, size - 1)
            self.send_response(HTTPStatus.PARTIAL_CONTENT if byte_range else HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "audio/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if byte_range:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    remaining -= len(chunk)

        def log_message(self, format_string: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), format_string % args)

    return ReviewHandler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Stage 1 listening review UI.")
    parser.add_argument("-a", "--analysis", type=Path, required=True)
    parser.add_argument("-r", "--review", type=Path)
    parser.add_argument("-H", "--host", default="127.0.0.1")
    parser.add_argument("-p", "--port", type=int, default=8765)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    review_path = args.review or args.analysis.with_name("review.csv")
    store = ReviewStore(args.analysis, review_path)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(store))
    LOGGER.info("review UI: http://%s:%d", *server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("stopping review UI")
    finally:
        server.server_close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(parse_args())
    except (OSError, ValueError) as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from error
