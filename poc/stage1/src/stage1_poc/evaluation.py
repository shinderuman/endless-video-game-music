from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stage1_poc.runner import atomic_write_json

DEFAULT_THRESHOLDS = (0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99)
END_GAP_MARGINS = (3.0, 5.0, 10.0, 15.0)
LABELS = ("loop", "non_loop", "loop_bad_points")


def is_adopted(track: dict[str, Any], threshold: float, end_gap_margin: float = 0.0) -> bool:
    if track.get("analysisStatus") != "candidate" or track.get("scoreRaw") is None:
        return False
    if float(track["scoreRaw"]) < threshold:
        return False
    gap = end_gap_seconds(track)
    return gap is None or gap > end_gap_margin


def end_gap_seconds(track: dict[str, Any]) -> float | None:
    required = ("loopEndSample", "sampleRate", "audioDurationSeconds")
    if any(track.get(field) is None for field in required):
        return None
    return float(track["audioDurationSeconds"]) - (
        int(track["loopEndSample"]) / int(track["sampleRate"])
    )


def threshold_metrics(
    tracks: list[dict[str, Any]],
    threshold: float,
    end_gap_margin: float = 0.0,
) -> dict[str, Any]:
    adopted = [track for track in tracks if is_adopted(track, threshold, end_gap_margin)]
    rejected = [track for track in tracks if not is_adopted(track, threshold, end_gap_margin)]
    true_adoptions = sum(track["userLabel"] == "loop" for track in adopted)
    false_non_loop = sum(track["userLabel"] == "non_loop" for track in adopted)
    false_bad_points = sum(track["userLabel"] == "loop_bad_points" for track in adopted)
    false_exclusions = sum(track["userLabel"] == "loop" for track in rejected)
    false_adoptions = false_non_loop + false_bad_points
    precision_denominator = true_adoptions + false_adoptions
    recall_denominator = true_adoptions + false_exclusions
    return {
        "threshold": threshold,
        "minimumEndGapSeconds": end_gap_margin,
        "adopted": len(adopted),
        "trueAdoptions": true_adoptions,
        "falseAdoptions": false_adoptions,
        "falseAdoptionsNonLoop": false_non_loop,
        "falseAdoptionsBadPoints": false_bad_points,
        "falseExclusions": false_exclusions,
        "trueRejections": len(rejected) - false_exclusions,
        "precision": _ratio(true_adoptions, precision_denominator),
        "recall": _ratio(true_adoptions, recall_denominator),
        "totalErrors": false_adoptions + false_exclusions,
    }


def evaluate(analysis_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    tracks = data.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("analysis must contain at least one track")
    invalid_labels = [
        track.get("userLabel") for track in tracks if track.get("userLabel") not in LABELS
    ]
    if invalid_labels:
        raise ValueError("every track must have a valid userLabel")
    fixed_metrics = [threshold_metrics(tracks, threshold) for threshold in DEFAULT_THRESHOLDS]
    observed_metrics = [
        threshold_metrics(tracks, threshold) for threshold in _observed_thresholds(tracks)
    ]
    minimum_errors = min(metric["totalErrors"] for metric in observed_metrics)
    end_gap_summary = [
        {
            "maximumEndGapSeconds": margin,
            **{
                label: sum(
                    track["userLabel"] == label
                    and (gap := end_gap_seconds(track)) is not None
                    and gap <= margin
                    for track in tracks
                )
                for label in LABELS
            },
        }
        for margin in END_GAP_MARGINS
    ]
    return {
        "analysisFile": str(analysis_path),
        "sampleSeed": data.get("sampleSeed"),
        "trackCount": len(tracks),
        "labels": {label: sum(track["userLabel"] == label for track in tracks) for label in LABELS},
        "automaticAdoptionDefinition": {
            "acceptableLabel": "loop",
            "rejectedLabels": ["non_loop", "loop_bad_points"],
            "rule": "candidate and score >= threshold and loop-end gap > optional margin",
        },
        "fixedThresholdMetrics": fixed_metrics,
        "minimumObservedError": {
            "totalErrors": minimum_errors,
            "operatingPoints": [
                metric for metric in observed_metrics if metric["totalErrors"] == minimum_errors
            ],
        },
        "endGapLabelCounts": end_gap_summary,
        "scoreAndEndGapMetrics": [
            threshold_metrics(tracks, threshold, margin)
            for margin in END_GAP_MARGINS
            for threshold in DEFAULT_THRESHOLDS
        ],
    }


def _observed_thresholds(tracks: list[dict[str, Any]]) -> list[float]:
    scores = {
        float(track["scoreRaw"])
        for track in tracks
        if track.get("analysisStatus") == "candidate" and track.get("scoreRaw") is not None
    }
    return sorted({0.0, 1.0, *scores})


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate labeled Stage 1 loop candidates.")
    parser.add_argument("-a", "--analysis", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    data = json.loads(args.analysis.read_text(encoding="utf-8"))
    result = evaluate(args.analysis, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output, result)


def main() -> None:
    try:
        run(parse_args())
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
