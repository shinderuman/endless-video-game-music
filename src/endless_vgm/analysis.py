from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .boundary import RefinedLoopBoundary, find_refined_loop_boundaries
from .models import Track

LOGGER = logging.getLogger(__name__)
MAX_LOOP_CANDIDATES = 20
ANALYSIS_CACHE_VERSION = 7

BoundaryFinder = Callable[
    [Path, int, int, int],
    list[RefinedLoopBoundary],
]


@dataclass(frozen=True)
class LoopCandidate:
    loop_start_sample: int
    loop_end_sample: int
    note_difference: float
    loudness_difference: float
    score: float
    sample_rate: int

    @property
    def loop_start_seconds(self) -> float:
        return self.loop_start_sample / self.sample_rate

    @property
    def loop_end_seconds(self) -> float:
        return self.loop_end_sample / self.sample_rate

    def public_dict(self) -> dict[str, float | int]:
        return {
            "loopStartSample": self.loop_start_sample,
            "loopEndSample": self.loop_end_sample,
            "loopStartSeconds": self.loop_start_seconds,
            "loopEndSeconds": self.loop_end_seconds,
            "noteDifference": self.note_difference,
            "loudnessDifference": self.loudness_difference,
            "score": self.score,
        }


class LoopAnalyzer:
    def __init__(
        self,
        cache_dir: Path,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        boundary_finder: BoundaryFinder = find_refined_loop_boundaries,
    ) -> None:
        self.cache_dir = cache_dir
        self.command_runner = command_runner
        self.boundary_finder = boundary_finder
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def analyze(self, track: Track, *, force: bool = False) -> dict[str, object]:
        if not track.available or track.location is None:
            raise FileNotFoundError("The track does not have an available local audio file")
        source = track.location
        fingerprint = _source_fingerprint(source)
        cache_path = self.cache_dir / f"{track.id}.json"
        lock = self._track_lock(track.id)
        with lock:
            if not force:
                cached = _read_cache(cache_path, fingerprint)
                if cached is not None:
                    return _limit_candidates(cached)
            result = self._run(track, fingerprint)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return result

    def _run(self, track: Track, fingerprint: dict[str, int]) -> dict[str, object]:
        assert track.location is not None
        started = time.monotonic()
        sample_rate = _probe_sample_rate(track.location, self.command_runner)
        command = [
            "pymusiclooper",
            "--samples",
            "export-points",
            "--path",
            str(track.location),
            "--alt-export-top",
            "-1",
            "--fmt",
            "samples",
            "--export-to",
            "stdout",
        ]
        completed = self.command_runner(
            command,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            fallback = f"PyMusicLooper failed with exit code {completed.returncode}"
            raise RuntimeError(message or fallback)
        candidates = parse_candidates(completed.stdout, sample_rate)
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        refined_candidates = (
            self._refine_top_candidate(track.location, candidates[0]) if candidates else []
        )
        candidates = candidates[:MAX_LOOP_CANDIDATES]
        return {
            "analysisVersion": ANALYSIS_CACHE_VERSION,
            "trackId": track.id,
            "source": fingerprint,
            "analysisDurationSeconds": time.monotonic() - started,
            "candidateCount": len(candidates),
            "refinedCandidates": refined_candidates,
            "candidates": [
                {**candidate.public_dict(), "rank": rank}
                for rank, candidate in enumerate(candidates, start=1)
            ],
        }

    def _refine_top_candidate(
        self,
        path: Path,
        candidate: LoopCandidate,
    ) -> list[dict[str, float | int | str]]:
        refined = self.boundary_finder(
            path,
            candidate.loop_start_sample,
            candidate.loop_end_sample,
            candidate.sample_rate,
        )
        return [boundary.public_dict(candidate.sample_rate) for boundary in refined]

    def _track_lock(self, track_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(track_id, threading.Lock())


def parse_candidates(output: str, sample_rate: int) -> list[LoopCandidate]:
    if "No loop points found for" in output:
        return []
    candidates: list[LoopCandidate] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"Unexpected PyMusicLooper output: {line}")
        candidates.append(
            LoopCandidate(
                loop_start_sample=int(fields[0]),
                loop_end_sample=int(fields[1]),
                note_difference=float(fields[2]),
                loudness_difference=float(fields[3]),
                score=float(fields[4]),
                sample_rate=sample_rate,
            )
        )
    return candidates


def _probe_sample_rate(
    path: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> int:
    completed = runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout)
    return int(payload["streams"][0]["sample_rate"])


def _source_fingerprint(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns}


def _read_cache(cache_path: Path, fingerprint: dict[str, int]) -> dict[str, object] | None:
    if not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("analysisVersion") != ANALYSIS_CACHE_VERSION:
        return None
    return payload if payload.get("source") == fingerprint else None


def _limit_candidates(result: dict[str, object]) -> dict[str, object]:
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return result
    limited = candidates[:MAX_LOOP_CANDIDATES]
    return {**result, "candidateCount": len(limited), "candidates": limited}
