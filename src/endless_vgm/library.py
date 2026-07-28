from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import threading
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import Playlist, Track

LOGGER = logging.getLogger(__name__)
MUSIC_BRIDGE_CACHE = Path.home() / "Library" / "Caches" / "Music Bridge" / "library-cache.json"
FILE_TRACK_PATTERN = re.compile(r"^(\d{1,2})-(\d{1,3})(?:\D|$)")
LEADING_TRACK_PATTERN = re.compile(r"^(\d{1,3})(?:\s|[._-])")


class MusicLibrary:
    def __init__(
        self,
        cache_path: Path,
        export_script: Path,
        *,
        fallback_cache_path: Path = MUSIC_BRIDGE_CACHE,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.cache_path = cache_path
        self.export_script = export_script
        self.fallback_cache_path = fallback_cache_path
        self.command_runner = command_runner
        self._lock = threading.RLock()
        self._playlists: dict[str, Playlist] = {}
        self._tracks: dict[str, Track] = {}

    def load(self) -> None:
        source = self.cache_path if self.cache_path.is_file() else self.fallback_cache_path
        if not source.is_file():
            LOGGER.info("Music library cache is not available yet")
            return
        self._replace_from_payload(json.loads(source.read_text(encoding="utf-8")))
        LOGGER.info("Loaded %d playlists from %s", len(self._playlists), source)

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

    def refresh(self) -> None:
        result = self.command_runner(
            ["osascript", "-l", "JavaScript", str(self.export_script)],
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        payload = json.loads(result.stdout)
        self._replace_from_payload(payload)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

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

    disc_number = _positive_int(
        raw_track.get("disc_number") or raw_track.get("discNumber")
    )
    track_number = _positive_int(
        raw_track.get("track_number") or raw_track.get("trackNumber")
    )
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
