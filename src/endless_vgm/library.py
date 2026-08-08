from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import re
import subprocess
import sys
import threading
import time
import unicodedata
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .models import Playlist, Track

LOGGER = logging.getLogger(__name__)
MUSIC_BRIDGE_CACHE = Path.home() / "Library" / "Caches" / "Music Bridge" / "library-cache.json"
FILE_TRACK_PATTERN = re.compile(r"^(\d{1,2})-(\d{1,3})(?:\D|$)")
LEADING_TRACK_PATTERN = re.compile(r"^(\d{1,3})(?:\s|[._-])")
PROGRESS_PATTERN = re.compile(r"^進捗 (\d+(?:\.\d+)?)%: (.+)$")


def run_command_with_progress(
    command: list[str],
    *,
    timeout: float,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    started_at = time.monotonic()
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")

    def read_stdout() -> None:
        if process.stdout is not None:
            stdout_parts.append(process.stdout.read())

    def relay_stderr() -> None:
        if process.stderr is None:
            return
        progress_active = False
        for line in process.stderr:
            stderr_parts.append(line)
            message = line.rstrip("\r\n")
            if log_path is not None:
                with log_path.open("a", encoding="utf-8") as output:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    output.write(f"{timestamp} {message}\n")
            match = PROGRESS_PATTERN.fullmatch(message)
            if match is None:
                if progress_active:
                    print(file=sys.stdout, flush=True)
                    progress_active = False
                print(message, file=sys.stdout, flush=True)
                continue
            percent = float(match.group(1))
            elapsed = time.monotonic() - started_at
            eta = _format_eta(elapsed, percent)
            print(
                f"\r{message} | ETA {eta}\033[K",
                end="",
                file=sys.stdout,
                flush=True,
            )
            progress_active = True
        if progress_active:
            print(file=sys.stdout, flush=True)

    stdout_thread = threading.Thread(target=read_stdout)
    stderr_thread = threading.Thread(target=relay_stderr)
    stdout_thread.start()
    stderr_thread.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        stdout_thread.join()
        stderr_thread.join()
    return subprocess.CompletedProcess(
        command,
        returncode,
        "".join(stdout_parts),
        "".join(stderr_parts),
    )


def _format_eta(elapsed: float, percent: float) -> str:
    if percent <= 0:
        return "--:--"
    remaining = max(elapsed * (100 - min(percent, 100)) / percent, 0)
    seconds = round(remaining)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class MusicLibrary:
    def __init__(
        self,
        cache_path: Path,
        export_script: Path,
        *,
        fallback_cache_path: Path = MUSIC_BRIDGE_CACHE,
        manifest_script: Path | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        progress_runner: Callable[..., subprocess.CompletedProcess[str]] = (
            run_command_with_progress
        ),
        manifest_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.cache_path = cache_path
        self.export_script = export_script
        self.fallback_cache_path = fallback_cache_path
        self.manifest_script = manifest_script
        self.command_runner = command_runner
        self.progress_runner = progress_runner
        self.manifest_runner = manifest_runner
        self._lock = threading.RLock()
        self._lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
        self._fingerprint_path = cache_path.with_suffix(cache_path.suffix + ".fingerprint")
        self._playlists: dict[str, Playlist] = {}
        self._tracks: dict[str, Track] = {}
        self._loaded_source: Path | None = None
        self._loaded_mtime_ns: int | None = None

    def load(self) -> None:
        source = self.cache_path if self.cache_path.is_file() else self.fallback_cache_path
        if not source.is_file():
            LOGGER.info("Music library cache is not available yet")
            return
        self._replace_from_payload(json.loads(source.read_text(encoding="utf-8")))
        with self._lock:
            self._loaded_source = source
            self._loaded_mtime_ns = source.stat().st_mtime_ns
        LOGGER.info("Loaded %d playlists from %s", len(self._playlists), source)

    def reload_if_changed(self) -> bool:
        source = self.cache_path if self.cache_path.is_file() else self.fallback_cache_path
        if not source.is_file():
            return False
        modified_ns = source.stat().st_mtime_ns
        with self._lock:
            if source == self._loaded_source and modified_ns == self._loaded_mtime_ns:
                return False
        self.load()
        return True

    def load_or_refresh(self) -> None:
        self.load()
        if self.playlists():
            return
        try:
            self.refresh()
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as error:
            LOGGER.warning(
                "Music.app library could not be loaded automatically: %s",
                error,
            )

    def refresh(
        self,
        *,
        show_progress: bool = False,
        progress_log_path: Path | None = None,
        fingerprint: str | None = None,
    ) -> None:
        # Inter-process lock shared by the watchdog (auto) and `make library`
        # (manual). Both construct MusicLibrary against the same cache path, so
        # they share this lock file and never run the slow export concurrently.
        with self._inter_process_lock():
            # Skip only when another process provably already refreshed the cache
            # to this exact fingerprint: library.json must be present and parse as
            # a valid cache, and the sidecar must match. Anything less certain
            # fails open (refresh again); an update is never silently dropped.
            if (
                fingerprint is not None
                and self._cache_is_loadable()
                and self._read_sidecar() == fingerprint
            ):
                self.load()
                LOGGER.info(
                    "Skipped Music.app refresh; cache already reflects fingerprint %s",
                    fingerprint,
                )
                return
            # Invalidate the sidecar BEFORE exporting or touching the data. While
            # it is empty no observer can falsely skip against a stale value, so a
            # crash or failure below can never leave fresh data described by an old
            # fingerprint. If this write fails we abort with the data untouched and
            # still consistent with the sidecar.
            self._invalidate_sidecar()
            command = ["osascript", "-l", "JavaScript", str(self.export_script)]
            if show_progress:
                result = self.progress_runner(
                    command,
                    timeout=3600,
                    log_path=progress_log_path,
                )
            else:
                result = self.command_runner(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
            if result.returncode != 0:
                stdout = result.stdout.strip()
                stderr = (result.stderr or "").strip()
                LOGGER.error(
                    "Music.app export failed with exit code %d\nstdout: %s\nstderr: %s",
                    result.returncode,
                    stdout,
                    stderr,
                )
                detail = stderr or stdout or f"osascript exited with code {result.returncode}"
                raise RuntimeError(detail)
            payload = json.loads(result.stdout)
            if fingerprint is None:
                # Manual path: derive the fingerprint now. On failure we leave the
                # sidecar empty (invalidated above) so the next caller fail-opens.
                fingerprint = self._safe_manifest_fingerprint()
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Write the data first, then sync in-memory state to what is on disk.
            self._atomic_write_text(
                self.cache_path,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
            self._replace_from_payload(payload)
            # Publish the matching sidecar only after the data is durable. If this
            # write fails the sidecar stays empty, which fail-opens the next caller
            # (an extra refresh); it never claims a state the data does not have.
            self._publish_sidecar(fingerprint)
            with self._lock:
                self._loaded_source = self.cache_path
                self._loaded_mtime_ns = self.cache_path.stat().st_mtime_ns

    def read_manifest(self) -> list[dict[str, Any]]:
        """Read the lightweight playlist manifest from Music.app.

        Raises on any Music.app/osascript failure so the caller can keep the
        previous baseline instead of acting on partial data.
        """
        if self.manifest_script is None:
            raise RuntimeError("playlist manifest script is not configured")
        result = self.manifest_runner(
            ["osascript", "-l", "JavaScript", str(self.manifest_script)],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f"osascript exited with code {result.returncode}"
            raise RuntimeError(detail)
        return _unwrap_manifest(json.loads(result.stdout))

    @contextlib.contextmanager
    def _inter_process_lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _read_sidecar(self) -> str | None:
        """Fingerprint recorded for the current cache, or None if absent/invalid.

        None means "not proven", so callers refresh rather than risk skipping.
        """
        try:
            value = self._fingerprint_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if len(value) != 64:
            return None
        try:
            int(value, 16)
        except ValueError:
            return None
        return value

    def _cache_is_loadable(self) -> bool:
        if not self.cache_path.is_file():
            return False
        try:
            _unwrap_playlists(json.loads(self.cache_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return False
        return True

    def _atomic_write_text(self, path: Path, content: str) -> None:
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)

    def _invalidate_sidecar(self) -> None:
        # Must succeed before the data changes. A crash between the data write and
        # a failed invalidation would otherwise leave fresh data paired with a
        # stale sidecar; raising here keeps the on-disk data consistent with the
        # sidecar so the caller can simply retry.
        self._atomic_write_text(self._fingerprint_path, "")

    def _publish_sidecar(self, fingerprint: str | None) -> None:
        try:
            self._atomic_write_text(self._fingerprint_path, fingerprint or "")
        except OSError as error:
            # The data is already durable and the sidecar was invalidated, so the
            # worst case is an empty sidecar: the next caller fail-opens. Do not
            # let a sidecar hiccup negate a successful refresh.
            LOGGER.warning("Could not publish playlist fingerprint sidecar: %s", error)

    def _safe_manifest_fingerprint(self) -> str | None:
        if self.manifest_script is None:
            return None
        try:
            return playlist_fingerprint(self.read_manifest())
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            ValueError,
            RuntimeError,
        ) as error:
            LOGGER.warning("Could not read playlist manifest for fingerprint: %s", error)
            return None

    def playlists(self) -> tuple[Playlist, ...]:
        with self._lock:
            return tuple(self._playlists.values())

    def playlist(self, name: str) -> Playlist | None:
        with self._lock:
            return self._playlists.get(name)

    def track(self, track_id: str) -> Track | None:
        with self._lock:
            return self._tracks.get(track_id)

    def _replace_from_payload(self, payload: Any) -> None:
        raw_playlists = _unwrap_playlists(payload)
        playlists: dict[str, Playlist] = {}
        tracks: dict[str, Track] = {}
        for raw_playlist in raw_playlists:
            playlist = _parse_playlist(raw_playlist)
            playlists[playlist.name] = playlist
            for track in playlist.tracks:
                tracks[track.id] = track
        with self._lock:
            self._playlists = playlists
            self._tracks = tracks


def playlist_fingerprint(manifest: list[dict[str, Any]]) -> str:
    """Deterministic fingerprint of user-managed playlist structure.

    Playlists are normalized to a stable order (by persistent ID) so the
    fingerprint is independent of Music.app's enumeration order. Track order is
    preserved, so reordering or swapping tracks changes the fingerprint. Only
    identity (persistent ID), name and ordered track persistent IDs participate:
    metadata-only edits are intentionally not detected.
    """
    rows: list[str] = []
    for playlist in sorted(manifest, key=lambda item: _text(item.get("id"))):
        playlist_id = _text(playlist.get("id"))
        name = _text(playlist.get("name"))
        raw_tracks = playlist.get("tracks")
        track_ids = (
            [str(_text(value)) for value in raw_tracks]
            if isinstance(raw_tracks, list)
            else []
        )
        rows.append("\t".join([playlist_id, name, ",".join(track_ids)]))
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _unwrap_manifest(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("playlist manifest must be a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _unwrap_playlists(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [value for value in payload if isinstance(value, dict)]
    if not isinstance(payload, dict):
        raise ValueError("Music library cache must contain an object or array")
    cached_playlists = payload.get("playlists")
    if not isinstance(cached_playlists, dict):
        raise ValueError("Music library cache does not contain playlists")
    result: list[dict[str, Any]] = []
    for value in cached_playlists.values():
        if not isinstance(value, dict):
            continue
        playlist = value.get("playlist")
        if isinstance(playlist, dict):
            result.append(playlist)
    return result


def _parse_playlist(raw_playlist: dict[str, Any]) -> Playlist:
    name = _text(raw_playlist.get("name"))
    raw_tracks = raw_playlist.get("tracks")
    if not name:
        raise ValueError("Invalid playlist in Music library cache")
    if raw_tracks is None:
        raw_tracks = []
    if not isinstance(raw_tracks, list):
        raise ValueError("Invalid track list in Music library cache")
    tracks = tuple(
        _parse_track(name, index, value)
        for index, value in enumerate(raw_tracks, start=1)
        if isinstance(value, dict)
    )
    return Playlist(
        name=name,
        tracks=tracks,
        is_library=raw_playlist.get("is_library") is True,
    )


def _parse_track(playlist: str, index: int, raw_track: dict[str, Any]) -> Track:
    raw_location = _text(raw_track.get("location"))
    location = Path(raw_location) if raw_location else None
    identity = "\0".join(
        [
            playlist,
            str(index),
            raw_location,
            _text(raw_track.get("name")),
            _text(raw_track.get("album")),
        ]
    )
    track_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    album = _text(raw_track.get("album"))
    disc_number, track_number = _track_numbers(raw_track, album, location)
    return Track(
        id=track_id,
        playlist=playlist,
        playlist_index=index,
        name=_text(raw_track.get("name")),
        artist=_text(raw_track.get("artist")),
        album_artist=_text(raw_track.get("album_artist") or raw_track.get("albumArtist")),
        album=album,
        location=location,
        disc_number=disc_number,
        track_number=track_number,
    )


def _text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value))


def _track_numbers(
    raw_track: dict[str, Any],
    album: str,
    location: Path | None,
) -> tuple[int | None, int | None]:
    from .albums import parse_album_name

    disc_number = _positive_int(raw_track.get("disc_number") or raw_track.get("discNumber"))
    track_number = _positive_int(raw_track.get("track_number") or raw_track.get("trackNumber"))
    album_info = parse_album_name(album)
    if disc_number is None and album_info is not None:
        disc_number = album_info.disc_number
    if location is None:
        return disc_number, track_number
    filename = location.name
    file_match = FILE_TRACK_PATTERN.match(filename)
    if file_match is not None:
        disc_number = disc_number or int(file_match.group(1))
        track_number = track_number or int(file_match.group(2))
    elif track_number is None and (leading_match := LEADING_TRACK_PATTERN.match(filename)):
        track_number = int(leading_match.group(1))
    return disc_number, track_number


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
