from __future__ import annotations

from pathlib import Path

import pytest

from stage1_poc.evaluation import end_gap_seconds, evaluate, threshold_metrics


def track(
    label: str | None,
    score: float | None,
    *,
    end: float = 80.0,
    duration: float = 100.0,
) -> dict[str, object]:
    return {
        "analysisStatus": "candidate" if score is not None else "no_candidate",
        "scoreRaw": str(score) if score is not None else None,
        "loopEndSample": int(end * 100) if score is not None else None,
        "sampleRate": 100,
        "audioDurationSeconds": duration,
        "userLabel": label,
    }


def test_threshold_metrics_distinguishes_bad_points_from_valid_loops() -> None:
    tracks = [
        track("loop", 0.95),
        track("loop", 0.7),
        track("non_loop", 0.99),
        track("loop_bad_points", 0.92),
        track("non_loop", None),
    ]

    result = threshold_metrics(tracks, 0.9)

    assert result["trueAdoptions"] == 1
    assert result["falseAdoptionsNonLoop"] == 1
    assert result["falseAdoptionsBadPoints"] == 1
    assert result["falseExclusions"] == 1
    assert result["totalErrors"] == 3


def test_end_gap_margin_rejects_candidate_in_fadeout_region() -> None:
    near_end = track("loop_bad_points", 0.99, end=97.0)
    valid = track("loop", 0.95, end=90.0)

    result = threshold_metrics([near_end, valid], 0.9, end_gap_margin=5.0)

    assert end_gap_seconds(near_end) == 3.0
    assert result["adopted"] == 1
    assert result["trueAdoptions"] == 1
    assert result["falseAdoptionsBadPoints"] == 0


def test_evaluate_requires_all_labels(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="every track"):
        evaluate(tmp_path / "analysis.json", {"tracks": [track(None, 0.9)]})


def test_evaluate_reports_minimum_observed_error_and_end_gap_counts(tmp_path: Path) -> None:
    data = {
        "sampleSeed": 1,
        "tracks": [
            track("loop", 0.9, end=90.0),
            track("non_loop", 0.2, end=99.0),
            track("loop_bad_points", 0.8, end=97.0),
        ],
    }

    result = evaluate(tmp_path / "analysis.json", data)

    assert result["labels"] == {"loop": 1, "non_loop": 1, "loop_bad_points": 1}
    assert result["minimumObservedError"]["totalErrors"] == 0
    assert result["endGapLabelCounts"][1] == {
        "maximumEndGapSeconds": 5.0,
        "loop": 0,
        "non_loop": 1,
        "loop_bad_points": 1,
    }
