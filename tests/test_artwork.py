from __future__ import annotations

import subprocess

from endless_vgm.artwork import ArtworkExporter, artwork_content_type
from endless_vgm.models import Track


def make_track(tmp_path) -> Track:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"audio")
    return Track(
        id="b" * 24,
        playlist="GAME",
        playlist_index=7,
        name="Track",
        artist="Artist",
        album_artist="Artist",
        album="Album",
        location=audio,
    )


def test_exports_and_caches_artwork(tmp_path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output = command[-1]
        with open(output, "wb") as target:
            target.write(b"\x89PNG\r\n\x1a\ncontent")
        return subprocess.CompletedProcess(command, 0, "", "")

    exporter = ArtworkExporter(
        tmp_path / "artwork",
        tmp_path / "export.applescript",
        command_runner=runner,
    )

    first = exporter.artwork(make_track(tmp_path))
    second = exporter.artwork(make_track(tmp_path))

    assert first == second
    assert first is not None
    assert artwork_content_type(first) == "image/png"
    assert len(calls) == 1
    assert calls[0][0] == "ffmpeg"


def test_falls_back_to_music_app_artwork(tmp_path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "ffmpeg":
            return subprocess.CompletedProcess(command, 1, "", "no video stream")
        with open(command[-1], "wb") as target:
            target.write(b"\xff\xd8\xffcontent")
        return subprocess.CompletedProcess(command, 0, "", "")

    exporter = ArtworkExporter(
        tmp_path / "artwork",
        tmp_path / "export.applescript",
        command_runner=runner,
    )

    artwork = exporter.artwork(make_track(tmp_path))

    assert artwork is not None
    assert artwork_content_type(artwork) == "image/jpeg"
    assert calls[1][2:4] == ["GAME", "7"]


def test_failed_export_returns_none(tmp_path) -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "denied")

    exporter = ArtworkExporter(
        tmp_path / "artwork",
        tmp_path / "export.applescript",
        command_runner=runner,
    )

    assert exporter.artwork(make_track(tmp_path)) is None


def test_detects_supported_artwork_types(tmp_path) -> None:
    samples = {
        "jpg": (b"\xff\xd8\xffdata", "image/jpeg"),
        "gif": (b"GIF89adata", "image/gif"),
        "tiff": (b"II*\x00data", "image/tiff"),
        "unknown": (b"something", "application/octet-stream"),
    }
    for name, (content, expected) in samples.items():
        path = tmp_path / name
        path.write_bytes(content)
        assert artwork_content_type(path) == expected
