from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from .models import Track


class ArtworkExporter:
    def __init__(
        self,
        cache_dir: Path,
        export_script: Path,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.cache_dir = cache_dir
        self.export_script = export_script
        self.command_runner = command_runner
        self._lock = threading.Lock()

    def artwork(self, track: Track) -> Path | None:
        cached = self.cache_dir / f"{track.id}.artwork"
        if cached.is_file() and cached.stat().st_size > 0:
            return cached
        with self._lock:
            if cached.is_file() and cached.stat().st_size > 0:
                return cached
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if track.location is not None:
                completed = self.command_runner(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(track.location),
                        "-map",
                        "0:v:0",
                        "-frames:v",
                        "1",
                        "-f",
                        "image2",
                        str(cached),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if completed.returncode == 0 and cached.is_file() and cached.stat().st_size > 0:
                    return cached
                cached.unlink(missing_ok=True)
            completed = self.command_runner(
                [
                    "osascript",
                    str(self.export_script),
                    track.playlist,
                    str(track.playlist_index),
                    str(cached),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0 or not cached.is_file() or cached.stat().st_size == 0:
                cached.unlink(missing_ok=True)
                return None
            return cached


def artwork_content_type(path: Path) -> str:
    prefix = path.read_bytes()[:12]
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if prefix[0:4] in {b"II*\x00", b"MM\x00*"}:
        return "image/tiff"
    return "application/octet-stream"
