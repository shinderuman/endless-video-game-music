from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pytest

from stage1_poc.runner import (
    COMMAND_OPTIONS,
    SELECTION_ALGORITHM,
    Track,
    atomic_write_json,
    build_track_result,
    load_playlist,
    parse_candidates,
    select_tracks,
    validate_resume,
    write_review_csv,
)


def test_load_playlist_reads_named_cached_playlist(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "playlists": {
                    "GAME": {
                        "playlist": {
                            "name": "GAME",
                            "tracks": [{"name": "One", "location": "/one.m4a"}],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert load_playlist(cache, "GAME") == [{"name": "One", "location": "/one.m4a"}]


def test_load_playlist_rejects_missing_playlist(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text('{"playlists": {}}', encoding="utf-8")

    with pytest.raises(ValueError, match="playlist not found"):
        load_playlist(cache, "GAME")


def test_select_tracks_is_seeded_and_source_order_independent_after_selection() -> None:
    tracks = [{"name": f"Track {index}", "location": f"/track-{index}.m4a"} for index in range(20)]

    first = select_tracks(tracks, seed=20260728, size=5)
    second = select_tracks(tracks, seed=20260728, size=5)
    other_seed = select_tracks(tracks, seed=20260729, size=5)

    assert first == second
    assert first != other_seed
    assert [track.selection_key for track in first] == sorted(
        track.selection_key for track in first
    )


def test_select_tracks_rejects_invalid_size() -> None:
    with pytest.raises(ValueError, match="sample size"):
        select_tracks([{"location": "/one.m4a"}], seed=1, size=2)


def test_select_tracks_excludes_tracks_without_source_paths() -> None:
    tracks = [
        {"name": "Missing", "location": ""},
        {"name": "Available", "location": "/available.m4a"},
    ]

    selected = select_tracks(tracks, seed=1, size=1)

    assert [track.title for track in selected] == ["Available"]
    with pytest.raises(ValueError, match="between 1 and 1"):
        select_tracks(tracks, seed=1, size=2)


def test_parse_candidates_preserves_raw_scores() -> None:
    output = "58875 782171 0.12308817356824875 0.18089339240177083 0.9484530227537512\n"

    candidates = parse_candidates(output)

    assert candidates[0].loop_start_sample == 58875
    assert candidates[0].loop_end_sample == 782171
    assert candidates[0].score_raw == "0.9484530227537512"


def test_parse_candidates_rejects_unexpected_output() -> None:
    with pytest.raises(ValueError, match="unexpected PyMusicLooper output"):
        parse_candidates("not a candidate")


def test_parse_candidates_recognizes_wrapped_no_candidate_message() -> None:
    output = '\nERROR    No loop points found for "track.m4a" with\n         current parameters.\n'

    assert parse_candidates(output) == []


def test_build_track_result_uses_top_candidate() -> None:
    track = Track(10, "Title", "Artist", "Album", "/track.m4a", "abc")

    result = build_track_result(
        track,
        0,
        "10 20 0.1 0.2 0.9\n11 21 0.2 0.3 0.8\n",
        "",
        1.25,
    )

    assert result["analysisStatus"] == "candidate"
    assert result["loopStartSample"] == 10
    assert result["loopEndSample"] == 20
    assert result["scoreRaw"] == "0.9"
    assert result["durationSeconds"] == 1.25
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["loopStartSample"] == 10
    assert "loop_start_sample" not in result["candidates"][0]


def test_build_track_result_preserves_evaluation_group_and_default_label() -> None:
    track = Track(
        10,
        "Title",
        "Artist",
        "Album",
        "/track.m4a",
        "abc",
        "known-negative",
        "non_loop",
    )

    result = build_track_result(track, 0, "", "", 1.0)

    assert result["evaluationGroup"] == "known-negative"
    assert result["userLabel"] == "non_loop"


def test_build_track_result_distinguishes_no_candidate_and_failure() -> None:
    track = Track(10, "Title", "Artist", "Album", "/track.m4a", "abc")

    no_candidate = build_track_result(track, 0, "", "", 1.0)
    failed = build_track_result(track, 2, "", "bad input", 1.0)

    assert no_candidate["analysisStatus"] == "no_candidate"
    assert failed["analysisStatus"] == "failed"
    assert failed["failureReason"] == "bad input"


def test_atomic_write_json_replaces_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}\n', encoding="utf-8")

    atomic_write_json(destination, {"new": True})

    assert json.loads(destination.read_text(encoding="utf-8")) == {"new": True}
    assert not destination.with_suffix(".json.tmp").exists()


def test_write_review_csv_includes_loop_times_in_seconds(tmp_path: Path) -> None:
    destination = tmp_path / "review.csv"
    write_review_csv(
        destination,
        [
            {
                "title": "Track",
                "loopStartSample": 22050,
                "loopEndSample": 88200,
                "sampleRate": 44100,
            }
        ],
    )

    with destination.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source))

    assert row["loopStartSeconds"] == "0.5"
    assert row["loopEndSeconds"] == "2.0"


def test_validate_resume_rejects_changed_command_options(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text("{}", encoding="utf-8")
    track = Track(0, "Title", "Artist", "Album", "/track.m4a", "abc")
    args = argparse.Namespace(
        cache=cache,
        playlist="GAME",
        seed=1,
        size=1,
    )
    state = {
        "sampleSeed": 1,
        "selectionAlgorithm": SELECTION_ALGORITHM,
        "playlist": "GAME",
        "sampleSize": 1,
        "commandOptions": [*COMMAND_OPTIONS, "--changed"],
        "sourceCacheSha256": ("44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
        "tracks": [{"sourcePath": "/track.m4a"}],
    }

    with pytest.raises(ValueError, match="does not match"):
        validate_resume(state, args, [track])
