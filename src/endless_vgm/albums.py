from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from .models import Track

DISC_PATTERN = re.compile(
    r"(?:^|[\s\[\(【_-])(?:disc|disk|dicc|cd)\s*[._-]*\s*(\d{1,2})"
    r"(?=\s*[.\]\)】_-]|\s|$)",
    re.IGNORECASE,
)
GENERIC_SUFFIX_PATTERN = re.compile(
    r"\s*(?:original\s*sound\s*(?:track|version)|original\s*soundtrack|"
    r"オリジナル[・\s]*(?:サウンドトラック|サウンド・トラック))\s*$",
    re.IGNORECASE,
)
KEY_SEPARATOR_PATTERN = re.compile(r"[\s・･:：._\-–—/\\]+")


@dataclass(frozen=True)
class AlbumGroup:
    id: str
    name: str
    tracks: tuple[Track, ...]
    disc_count: int
    first_playlist_index: int

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "discCount": self.disc_count,
            "trackCount": len(self.tracks),
            "trackIds": [track.id for track in self.tracks],
        }


@dataclass(frozen=True)
class ParsedAlbumName:
    disc_number: int
    display_base: str
    comparison_key: str


@dataclass(frozen=True)
class _AlbumEntry:
    name: str
    tracks: tuple[Track, ...]
    disc_number: int | None
    explicit_disc: bool
    display_base: str
    comparison_key: str

    @property
    def first_playlist_index(self) -> int:
        return min(track.playlist_index for track in self.tracks)


def build_album_groups(tracks: tuple[Track, ...]) -> tuple[AlbumGroup, ...]:
    albums: dict[str, list[Track]] = {}
    for track in tracks:
        albums.setdefault(track.album, []).append(track)
    entries = tuple(_album_entry(name, values) for name, values in albums.items())
    buckets: dict[str, list[_AlbumEntry]] = {}
    for entry in entries:
        buckets.setdefault(entry.comparison_key, []).append(entry)

    groups: list[AlbumGroup] = []
    consumed: set[str] = set()
    for comparison_key, bucket in buckets.items():
        numbered = [entry for entry in bucket if entry.disc_number is not None]
        distinct_discs = {entry.disc_number for entry in numbered}
        has_explicit_disc = any(entry.explicit_disc for entry in numbered)
        if (
            len(numbered) < 2
            or len(numbered) != len(distinct_discs)
            or len(distinct_discs) < 2
            or not has_explicit_disc
        ):
            continue
        groups.append(_merged_group(comparison_key, numbered))
        consumed.update(entry.name for entry in numbered)

    for entry in entries:
        if entry.name not in consumed:
            groups.append(_single_group(entry))
    groups.sort(key=lambda group: group.first_playlist_index)
    return tuple(groups)


def parse_album_name(name: str) -> ParsedAlbumName | None:
    normalized = unicodedata.normalize("NFKC", name)
    match = DISC_PATTERN.search(normalized)
    if match is None:
        return None
    display_base = normalized[: match.start()].rstrip(" \t[（(【_-")
    if not display_base:
        return None
    return ParsedAlbumName(
        disc_number=int(match.group(1)),
        display_base=display_base,
        comparison_key=album_comparison_key(display_base),
    )


def album_comparison_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name)
    without_generic_suffix = GENERIC_SUFFIX_PATTERN.sub("", normalized)
    return KEY_SEPARATOR_PATTERN.sub("", without_generic_suffix.casefold())


def _album_entry(name: str, tracks: list[Track]) -> _AlbumEntry:
    parsed = parse_album_name(name)
    disc_numbers = {track.disc_number for track in tracks if track.disc_number is not None}
    inferred_disc = next(iter(disc_numbers)) if len(disc_numbers) == 1 else None
    return _AlbumEntry(
        name=name,
        tracks=tuple(tracks),
        disc_number=parsed.disc_number if parsed is not None else inferred_disc,
        explicit_disc=parsed is not None,
        display_base=parsed.display_base if parsed is not None else name,
        comparison_key=(
            parsed.comparison_key if parsed is not None else album_comparison_key(name)
        ),
    )


def _merged_group(comparison_key: str, entries: list[_AlbumEntry]) -> AlbumGroup:
    ordered_entries = sorted(entries, key=lambda entry: entry.disc_number or 0)
    ordered_tracks = tuple(
        track
        for entry in ordered_entries
        for track in sorted(entry.tracks, key=lambda track: track.playlist_index)
    )
    display_entry = next(
        (entry for entry in ordered_entries if entry.disc_number == 1),
        ordered_entries[0],
    )
    return AlbumGroup(
        id=_group_id("merged", comparison_key),
        name=display_entry.display_base,
        tracks=ordered_tracks,
        disc_count=len(ordered_entries),
        first_playlist_index=min(entry.first_playlist_index for entry in entries),
    )


def _single_group(entry: _AlbumEntry) -> AlbumGroup:
    return AlbumGroup(
        id=_group_id("single", entry.name),
        name=entry.name,
        tracks=entry.tracks,
        disc_count=1,
        first_playlist_index=entry.first_playlist_index,
    )


def _group_id(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{value}".encode()).hexdigest()[:16]
    return f"{kind}-{digest}"
