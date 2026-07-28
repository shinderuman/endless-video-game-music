from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Track:
    id: str
    playlist: str
    playlist_index: int
    name: str
    artist: str
    album_artist: str
    album: str
    location: Path | None
    disc_number: int | None = None
    track_number: int | None = None

    @property
    def available(self) -> bool:
        return self.location is not None and self.location.is_file()

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "playlist": self.playlist,
            "playlistIndex": self.playlist_index,
            "name": self.name,
            "artist": self.artist,
            "albumArtist": self.album_artist,
            "album": self.album,
            "discNumber": self.disc_number,
            "trackNumber": self.track_number,
            "available": self.available,
            "audioUrl": f"/api/tracks/{self.id}/audio" if self.available else None,
            "artworkUrl": f"/api/tracks/{self.id}/artwork" if self.available else None,
        }


@dataclass(frozen=True)
class Playlist:
    name: str
    tracks: tuple[Track, ...]

    def summary_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "trackCount": len(self.tracks),
            "availableTrackCount": sum(track.available for track in self.tracks),
        }
