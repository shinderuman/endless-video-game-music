from __future__ import annotations

import json
from pathlib import Path

import pytest

from stage1_poc.evaluation_builder import build_evaluation_cache


def cached_playlist(name: str, tracks: list[dict[str, str]]) -> dict[str, object]:
    return {"playlist": {"name": name, "tracks": tracks}}


def test_build_evaluation_cache_is_reproducible_and_preserves_labels(tmp_path: Path) -> None:
    audio_paths = [tmp_path / f"track-{index}.m4a" for index in range(5)]
    for path in audio_paths:
        path.write_bytes(b"audio")
    source_path = tmp_path / "source.json"
    cache = {
        "playlists": {
            "GAME": cached_playlist(
                "GAME",
                [
                    {"name": "One", "album": "Known", "location": str(audio_paths[0])},
                    {"name": "Two", "album": "Known", "location": str(audio_paths[1])},
                    {"name": "Other", "album": "Other", "location": str(audio_paths[2])},
                ],
            ),
            "VOCAL": cached_playlist(
                "VOCAL",
                [
                    {"name": "Vocal 1", "album": "Single", "location": str(audio_paths[3])},
                    {"name": "Vocal 2", "album": "Single", "location": str(audio_paths[4])},
                ],
            ),
        }
    }
    source_path.write_text(json.dumps(cache), encoding="utf-8")
    config = {
        "seed": 10,
        "outputPlaylist": "CURATED",
        "groups": [
            {
                "id": "known",
                "sourcePlaylist": "GAME",
                "albums": ["Known"],
                "sampleSize": 2,
                "defaultLabel": None,
            },
            {
                "id": "negative",
                "sourcePlaylist": "VOCAL",
                "albums": [],
                "sampleSize": 2,
                "defaultLabel": "non_loop",
            },
        ],
    }

    first = build_evaluation_cache(cache, source_path, config)
    second = build_evaluation_cache(cache, source_path, config)
    tracks = first["playlists"]["CURATED"]["playlist"]["tracks"]

    assert first == second
    assert first["evaluationSet"]["trackCount"] == 4
    assert [track["_evaluationGroup"] for track in tracks].count("known") == 2
    assert [track["_defaultLabel"] for track in tracks].count("non_loop") == 2


def test_build_evaluation_cache_rejects_insufficient_group(tmp_path: Path) -> None:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"audio")
    source_path = tmp_path / "source.json"
    cache = {
        "playlists": {
            "GAME": cached_playlist(
                "GAME",
                [{"name": "One", "album": "Known", "location": str(audio)}],
            )
        }
    }
    source_path.write_text(json.dumps(cache), encoding="utf-8")
    config = {
        "seed": 10,
        "outputPlaylist": "CURATED",
        "groups": [
            {
                "id": "known",
                "sourcePlaylist": "GAME",
                "albums": ["Known"],
                "sampleSize": 2,
                "defaultLabel": None,
            }
        ],
    }

    with pytest.raises(ValueError, match="1 eligible tracks"):
        build_evaluation_cache(cache, source_path, config)
