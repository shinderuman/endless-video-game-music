from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from stage1_poc.review_server import ReviewStore, parse_byte_range


def write_analysis(path: Path, source_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "sampleSeed": 20260728,
                "pymusiclooperVersion": "pymusiclooper 3.6.0",
                "tracks": [
                    {
                        "title": "Track",
                        "artist": "Artist",
                        "album": "Album",
                        "sourcePath": str(source_path),
                        "analysisStatus": "candidate",
                        "loopStartSample": 22050,
                        "loopEndSample": 88200,
                        "sampleRate": 44100,
                        "scoreRaw": "0.9",
                        "userLabel": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_review_store_exposes_loop_times_and_summary(tmp_path: Path) -> None:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"audio")
    analysis = tmp_path / "analysis.json"
    write_analysis(analysis, audio)

    snapshot = ReviewStore(analysis, tmp_path / "review.csv").snapshot()

    assert snapshot["summary"] == {
        "total": 1,
        "labeled": 0,
        "loop": 0,
        "nonLoop": 0,
        "loopBadPoints": 0,
    }
    assert snapshot["tracks"][0]["loopStartSeconds"] == 0.5
    assert snapshot["tracks"][0]["loopEndSeconds"] == 2.0
    assert snapshot["tracks"][0]["sourceFile"] == "track.m4a"


def test_review_store_persists_label_to_json_and_csv(tmp_path: Path) -> None:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"audio")
    analysis = tmp_path / "analysis.json"
    review = tmp_path / "review.csv"
    write_analysis(analysis, audio)
    store = ReviewStore(analysis, review)

    updated = store.set_label(0, "loop")

    assert updated["userLabel"] == "loop"
    assert json.loads(analysis.read_text(encoding="utf-8"))["tracks"][0]["userLabel"] == "loop"
    with review.open(encoding="utf-8", newline="") as source:
        assert next(csv.DictReader(source))["userLabel"] == "loop"


def test_review_store_persists_bad_loop_points_label(tmp_path: Path) -> None:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"audio")
    analysis = tmp_path / "analysis.json"
    write_analysis(analysis, audio)
    store = ReviewStore(analysis, tmp_path / "review.csv")

    updated = store.set_label(0, "loop_bad_points")

    assert updated["userLabel"] == "loop_bad_points"
    assert store.snapshot()["summary"]["loopBadPoints"] == 1


def test_review_store_rejects_invalid_label_and_index(tmp_path: Path) -> None:
    audio = tmp_path / "track.m4a"
    audio.write_bytes(b"audio")
    analysis = tmp_path / "analysis.json"
    write_analysis(analysis, audio)
    store = ReviewStore(analysis, tmp_path / "review.csv")

    with pytest.raises(ValueError, match="label must be"):
        store.set_label(0, "maybe")
    with pytest.raises(IndexError, match="out of range"):
        store.set_label(1, "loop")


@pytest.mark.parametrize(
    ("header", "size", "expected"),
    [
        (None, 100, None),
        ("bytes=0-", 100, (0, 99)),
        ("bytes=10-19", 100, (10, 19)),
        ("bytes=-10", 100, (90, 99)),
        ("bytes=95-200", 100, (95, 99)),
    ],
)
def test_parse_byte_range(
    header: str | None,
    size: int,
    expected: tuple[int, int] | None,
) -> None:
    assert parse_byte_range(header, size) == expected


def test_parse_byte_range_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        parse_byte_range("items=0-1", 100)
    with pytest.raises(ValueError):
        parse_byte_range("bytes=100-", 100)
