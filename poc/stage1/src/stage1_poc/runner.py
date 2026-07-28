from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
SELECTION_ALGORITHM = "sha256(seed NUL originalIndex NUL sourcePath), ascending"
COMMAND_OPTIONS = [
    "--samples",
    "export-points",
    "--alt-export-top",
    "1",
    "--fmt",
    "samples",
    "--export-to",
    "stdout",
]


@dataclass(frozen=True)
class Track:
    original_index: int
    title: str
    artist: str
    album: str
    source_path: str
    selection_key: str
    evaluation_group: str | None = None
    default_label: str | None = None


@dataclass(frozen=True)
class Candidate:
    loop_start_sample: int
    loop_end_sample: int
    note_difference_raw: str
    loudness_difference_raw: str
    score_raw: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_playlist(cache_path: Path, playlist_name: str) -> list[dict[str, str]]:
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    try:
        playlist = data["playlists"][playlist_name]["playlist"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"playlist not found in cache: {playlist_name}") from error
    tracks = playlist.get("tracks")
    if playlist.get("name") != playlist_name or not isinstance(tracks, list):
        raise ValueError(f"invalid cached playlist: {playlist_name}")
    return tracks


def selection_key(seed: int, original_index: int, source_path: str) -> str:
    value = f"{seed}\0{original_index}\0{source_path}".encode()
    return hashlib.sha256(value).hexdigest()


def eligible_tracks(tracks: list[dict[str, str]], seed: int) -> list[Track]:
    return [
        Track(
            original_index=index,
            title=track.get("name", ""),
            artist=track.get("artist", ""),
            album=track.get("album", ""),
            source_path=track.get("location", ""),
            selection_key=selection_key(seed, index, track.get("location", "")),
            evaluation_group=track.get("_evaluationGroup"),
            default_label=track.get("_defaultLabel"),
        )
        for index, track in enumerate(tracks)
        if track.get("location", "")
    ]


def select_tracks(tracks: list[dict[str, str]], seed: int, size: int) -> list[Track]:
    candidates = eligible_tracks(tracks, seed)
    if size <= 0 or size > len(candidates):
        raise ValueError(f"sample size must be between 1 and {len(candidates)}")
    return sorted(candidates, key=lambda track: track.selection_key)[:size]


def command_version(command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


def probe_audio(source_path: str) -> tuple[int, float]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate:format=duration",
        "-of",
        "json",
        source_path,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return int(data["streams"][0]["sample_rate"]), float(data["format"]["duration"])


def parse_candidates(output: str) -> list[Candidate]:
    if "No loop points found for" in output:
        return []
    candidates: list[Candidate] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"unexpected PyMusicLooper output: {line}")
        candidates.append(
            Candidate(
                loop_start_sample=int(fields[0]),
                loop_end_sample=int(fields[1]),
                note_difference_raw=fields[2],
                loudness_difference_raw=fields[3],
                score_raw=fields[4],
            )
        )
    return candidates


def run_analysis(track: Track) -> tuple[dict[str, Any], dict[str, Any]]:
    command = ["pymusiclooper", *COMMAND_OPTIONS[:2], "--path", track.source_path]
    command.extend(COMMAND_OPTIONS[2:])
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    log = {
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exitCode": result.returncode,
        "analysisDurationSeconds": elapsed,
    }
    return build_track_result(track, result.returncode, result.stdout, result.stderr, elapsed), log


def build_track_result(
    track: Track,
    exit_code: int,
    stdout: str,
    stderr: str,
    elapsed: float,
) -> dict[str, Any]:
    result = asdict(track)
    result["sourcePath"] = result.pop("source_path")
    result["originalIndex"] = result.pop("original_index")
    result["selectionKey"] = result.pop("selection_key")
    result["evaluationGroup"] = result.pop("evaluation_group")
    default_label = result.pop("default_label")
    result.update(
        {
            "durationSeconds": elapsed,
            "analysisDurationSeconds": elapsed,
            "exitCode": exit_code,
            "userLabel": default_label,
        }
    )
    if exit_code != 0:
        result.update(_failed_result(stderr))
        return result
    try:
        candidates = parse_candidates(stdout)
    except ValueError as error:
        result.update(_failed_result(str(error)))
        return result
    result.update(_candidate_result(candidates))
    return result


def _failed_result(message: str) -> dict[str, Any]:
    return {
        "analysisStatus": "failed",
        "failureReason": message.strip(),
        "loopStartSample": None,
        "loopEndSample": None,
        "scoreRaw": None,
        "candidates": [],
    }


def _candidate_result(candidates: list[Candidate]) -> dict[str, Any]:
    if not candidates:
        return {
            "analysisStatus": "no_candidate",
            "failureReason": None,
            "loopStartSample": None,
            "loopEndSample": None,
            "scoreRaw": None,
            "candidates": [],
        }
    top = candidates[0]
    return {
        "analysisStatus": "candidate",
        "failureReason": None,
        "loopStartSample": top.loop_start_sample,
        "loopEndSample": top.loop_end_sample,
        "scoreRaw": top.score_raw,
        "candidates": [
            {
                "loopStartSample": candidate.loop_start_sample,
                "loopEndSample": candidate.loop_end_sample,
                "noteDifferenceRaw": candidate.note_difference_raw,
                "loudnessDifferenceRaw": candidate.loudness_difference_raw,
                "scoreRaw": candidate.score_raw,
            }
            for candidate in candidates
        ],
    }


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_log(path: Path, log: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_review_csv(path: Path, tracks: list[dict[str, Any]]) -> None:
    fields = [
        "sampleNumber",
        "title",
        "album",
        "artist",
        "scoreRaw",
        "analysisStatus",
        "loopStartSample",
        "loopEndSample",
        "sampleRate",
        "loopStartSeconds",
        "loopEndSeconds",
        "audioDurationSeconds",
        "evaluationGroup",
        "sourcePath",
        "userLabel",
    ]
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for index, track in enumerate(tracks, start=1):
            row = {field: track.get(field) for field in fields if field != "sampleNumber"}
            sample_rate = track.get("sampleRate")
            if sample_rate:
                row["loopStartSeconds"] = _sample_seconds(track.get("loopStartSample"), sample_rate)
                row["loopEndSeconds"] = _sample_seconds(track.get("loopEndSample"), sample_rate)
            writer.writerow(
                {
                    "sampleNumber": index,
                    **row,
                }
            )


def _sample_seconds(sample: int | None, sample_rate: int) -> float | None:
    return sample / sample_rate if sample is not None else None


def initial_state(
    args: argparse.Namespace,
    playlist_tracks: list[dict[str, str]],
    selected: list[Track],
) -> dict[str, Any]:
    eligible_count = len(eligible_tracks(playlist_tracks, args.seed))
    return {
        "sampleSeed": args.seed,
        "selectionAlgorithm": SELECTION_ALGORITHM,
        "sourceCache": str(args.cache),
        "sourceCacheSha256": file_sha256(args.cache),
        "playlist": args.playlist,
        "playlistTrackCount": len(playlist_tracks),
        "eligibleTrackCount": eligible_count,
        "excludedMissingLocationCount": len(playlist_tracks) - eligible_count,
        "sampleSize": args.size,
        "pymusiclooperVersion": command_version(["pymusiclooper", "--version"]),
        "ffprobeVersion": command_version(["ffprobe", "-version"]).splitlines()[0],
        "commandOptions": COMMAND_OPTIONS,
        "tracks": [
            {
                "originalIndex": track.original_index,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "sourcePath": track.source_path,
                "selectionKey": track.selection_key,
                "evaluationGroup": track.evaluation_group,
                "analysisStatus": "unprocessed",
                "userLabel": track.default_label,
            }
            for track in selected
        ],
    }


def validate_resume(state: dict[str, Any], args: argparse.Namespace, selected: list[Track]) -> None:
    expected_paths = [track.source_path for track in selected]
    actual_paths = [track.get("sourcePath") for track in state.get("tracks", [])]
    checks = [
        state.get("sampleSeed") == args.seed,
        state.get("selectionAlgorithm") == SELECTION_ALGORITHM,
        state.get("playlist") == args.playlist,
        state.get("sampleSize") == args.size,
        state.get("commandOptions") == COMMAND_OPTIONS,
        state.get("sourceCacheSha256") == file_sha256(args.cache),
        actual_paths == expected_paths,
    ]
    if not all(checks):
        raise ValueError("existing analysis state does not match the requested sample")


def run(args: argparse.Namespace) -> int:
    args.output.mkdir(parents=True, exist_ok=True)
    logs_dir = args.output / "logs"
    logs_dir.mkdir(exist_ok=True)
    playlist_tracks = load_playlist(args.cache, args.playlist)
    selected = select_tracks(playlist_tracks, args.seed, args.size)
    state_path = args.output / "analysis.json"
    state = load_or_create_state(state_path, args, playlist_tracks, selected)
    for index, track in enumerate(selected):
        if state["tracks"][index].get("analysisStatus") != "unprocessed":
            continue
        LOGGER.info("analyzing %d/%d: %s", index + 1, len(selected), track.title)
        result, log = analyze_with_probe(track)
        state["tracks"][index] = result
        write_log(logs_dir / f"{index + 1:03}-{track.selection_key[:12]}.json", log)
        atomic_write_json(state_path, state)
    write_review_csv(args.output / "review.csv", state["tracks"])
    return 0


def load_or_create_state(
    state_path: Path,
    args: argparse.Namespace,
    playlist_tracks: list[dict[str, str]],
    selected: list[Track],
) -> dict[str, Any]:
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        validate_resume(state, args, selected)
        return state
    state = initial_state(args, playlist_tracks, selected)
    atomic_write_json(state_path, state)
    return state


def analyze_with_probe(track: Track) -> tuple[dict[str, Any], dict[str, Any]]:
    if not Path(track.source_path).is_file():
        result = build_track_result(track, 1, "", "source file does not exist", 0.0)
        return result, {
            "command": [],
            "stdout": "",
            "stderr": result["failureReason"],
            "exitCode": 1,
        }
    result, log = run_analysis(track)
    if result["analysisStatus"] == "failed":
        return result, log
    try:
        sample_rate, audio_duration = probe_audio(track.source_path)
    except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError) as error:
        result.update(_failed_result(f"ffprobe failed: {error}"))
        return result, log
    result["sampleRate"] = sample_rate
    result["audioDurationSeconds"] = audio_duration
    return result, log


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--cache", type=Path, required=True)
    parser.add_argument("-p", "--playlist", required=True)
    parser.add_argument("-s", "--seed", type=int, required=True)
    parser.add_argument("-n", "--size", type=int, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        raise SystemExit(run(parse_args()))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from error
