from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal

END_SEARCH_RADIUS_SECONDS = 1.0
END_CONTEXT_SECONDS = 0.1
PAIR_SEARCH_RADIUS_SECONDS = 0.5
PAIR_CONTEXT_SECONDS = 0.02
LOOPMUSIC_SAMPLE_RADIUS = 2
LOOP_AUDITIONEER_WINDOW = 5
PAIR_SHORTLIST_SIZE = 1_000


@dataclass(frozen=True)
class RefinedLoopBoundary:
    rank: int
    loop_start_sample: int
    loop_end_sample: int
    similarity: float
    method: str

    def public_dict(self, sample_rate: int) -> dict[str, float | int | str]:
        return {
            "rank": self.rank,
            "loopStartSample": self.loop_start_sample,
            "loopEndSample": self.loop_end_sample,
            "loopStartSeconds": self.loop_start_sample / sample_rate,
            "loopEndSeconds": self.loop_end_sample / sample_rate,
            "noteDifference": 1.0 - self.similarity,
            "loudnessDifference": 0.0,
            "score": self.similarity,
            "method": self.method,
        }


def find_refined_loop_boundaries(
    path: Path,
    loop_start_sample: int,
    loop_end_sample: int,
    sample_rate: int,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> list[RefinedLoopBoundary]:
    completed = command_runner(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "2",
            "-ar",
            str(sample_rate),
            "-f",
            "f32le",
            "pipe:1",
        ],
        capture_output=True,
        timeout=300,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(message or f"ffmpeg exited with code {completed.returncode}")
    audio = np.frombuffer(completed.stdout, dtype="<f4")
    if audio.size % 2:
        return []
    return find_refined_loop_boundaries_from_audio(
        audio.reshape(-1, 2),
        sample_rate,
        loop_start_sample,
        loop_end_sample,
    )


def find_refined_loop_boundaries_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    loop_start_sample: int,
    loop_end_sample: int,
) -> list[RefinedLoopBoundary]:
    if audio.ndim != 2:
        raise ValueError("Loop boundary analysis requires channel-separated audio")
    if audio.shape[1] < 1:
        raise ValueError("Loop boundary analysis requires at least one channel")
    if loop_start_sample < 0 or loop_end_sample <= loop_start_sample:
        return []
    if loop_end_sample >= audio.shape[0] or not np.any(audio):
        return []

    mono = np.mean(audio.astype(np.float64), axis=1)
    refined_end, correlation = _find_matching_end(
        mono,
        sample_rate,
        loop_start_sample,
        loop_end_sample,
    )
    if refined_end is None:
        return []

    duration_refined = RefinedLoopBoundary(
        rank=0,
        loop_start_sample=loop_start_sample,
        loop_end_sample=refined_end,
        similarity=correlation,
        method="pmlDurationLocalWaveform",
    )
    loopmusic_pair = _find_loopmusic_pair(
        audio.astype(np.float64),
        sample_rate,
        loop_start_sample,
        refined_end,
    )
    auditioneer_pair = _find_auditioneer_pair(
        audio.astype(np.float64),
        sample_rate,
        loop_start_sample,
        refined_end,
    )
    return [
        duration_refined,
        *([loopmusic_pair] if loopmusic_pair is not None else []),
        *([auditioneer_pair] if auditioneer_pair is not None else []),
    ]


def _find_matching_end(
    mono: np.ndarray,
    sample_rate: int,
    loop_start_sample: int,
    target_end_sample: int,
) -> tuple[int | None, float]:
    half_window = round(END_CONTEXT_SECONDS * sample_rate / 2)
    search_radius = round(END_SEARCH_RADIUS_SECONDS * sample_rate)
    search_start = target_end_sample - search_radius
    search_end = target_end_sample + search_radius
    if (
        loop_start_sample < half_window
        or search_start < half_window
        or search_end + half_window >= mono.size
    ):
        return None, 0.0

    reference = mono[loop_start_sample - half_window : loop_start_sample + half_window]
    search_audio = mono[search_start - half_window : search_end + half_window]
    scores = _normalized_correlation(reference, search_audio)
    if scores.size == 0:
        return None, 0.0
    best_offset = int(np.argmax(scores))
    return search_start + best_offset, float(scores[best_offset])


def _find_loopmusic_pair(
    audio: np.ndarray,
    sample_rate: int,
    loop_start_sample: int,
    loop_end_sample: int,
) -> RefinedLoopBoundary | None:
    loop_length = loop_end_sample - loop_start_sample
    starts = _valid_pair_starts(
        audio.shape[0],
        sample_rate,
        loop_start_sample,
        loop_length,
        LOOPMUSIC_SAMPLE_RADIUS,
    )
    if starts.size == 0:
        return None

    endpoint_differences = np.zeros(starts.size, dtype=np.float64)
    for offset in range(-LOOPMUSIC_SAMPLE_RADIUS, LOOPMUSIC_SAMPLE_RADIUS + 1):
        differences = np.max(
            np.abs(audio[starts + offset] - audio[starts + loop_length + offset]),
            axis=1,
        )
        endpoint_differences = np.maximum(endpoint_differences, differences)

    shortlist_size = min(PAIR_SHORTLIST_SIZE, starts.size)
    shortlist = np.argpartition(endpoint_differences, shortlist_size - 1)[:shortlist_size]
    context_radius = max(1, round(PAIR_CONTEXT_SECONDS * sample_rate / 2))
    best_index: int | None = None
    best_score = np.inf
    best_mse = np.inf
    for index in shortlist:
        start = int(starts[index])
        end = start + loop_length
        mse = _normalized_window_mse(audio, start, end, context_radius)
        score = mse + endpoint_differences[index] * 0.02
        if score < best_score:
            best_index = int(index)
            best_score = score
            best_mse = mse
    if best_index is None:
        return None

    start = int(starts[best_index])
    return RefinedLoopBoundary(
        rank=-1,
        loop_start_sample=start,
        loop_end_sample=start + loop_length,
        similarity=1.0 / (1.0 + best_mse),
        method="loopMusicEndpointPair",
    )


def _find_auditioneer_pair(
    audio: np.ndarray,
    sample_rate: int,
    loop_start_sample: int,
    loop_end_sample: int,
) -> RefinedLoopBoundary | None:
    loop_length = loop_end_sample - loop_start_sample
    starts = _valid_pair_starts(
        audio.shape[0],
        sample_rate,
        loop_start_sample,
        loop_length,
        LOOP_AUDITIONEER_WINDOW,
    )
    if starts.size == 0:
        return None

    quality = np.zeros(starts.size, dtype=np.float64)
    for offset in range(1, LOOP_AUDITIONEER_WINDOW + 1):
        quality += np.max(
            np.abs(audio[starts - offset] - audio[starts + loop_length - offset]),
            axis=1,
        )
    best_index = int(np.argmin(quality))
    start = int(starts[best_index])
    end = start + loop_length
    context_radius = max(1, round(PAIR_CONTEXT_SECONDS * sample_rate / 2))
    mse = _normalized_window_mse(audio, start, end, context_radius)
    return RefinedLoopBoundary(
        rank=-2,
        loop_start_sample=start,
        loop_end_sample=end,
        similarity=1.0 / (1.0 + mse),
        method="loopAuditioneerFiveSample",
    )


def _valid_pair_starts(
    audio_length: int,
    sample_rate: int,
    loop_start_sample: int,
    loop_length: int,
    margin: int,
) -> np.ndarray:
    radius = round(PAIR_SEARCH_RADIUS_SECONDS * sample_rate)
    first = max(margin, loop_start_sample - radius)
    last = min(
        audio_length - loop_length - margin - 1,
        loop_start_sample + radius,
    )
    if last < first:
        return np.array([], dtype=np.int64)
    return np.arange(first, last + 1, dtype=np.int64)


def _normalized_window_mse(
    audio: np.ndarray,
    start: int,
    end: int,
    radius: int,
) -> float:
    start_window = audio[start - radius : start + radius]
    end_window = audio[end - radius : end + radius]
    power = (np.mean(np.square(start_window)) + np.mean(np.square(end_window))) / 2
    return float(np.mean(np.square(start_window - end_window)) / max(power, 1e-9))


def _normalized_correlation(reference: np.ndarray, search_audio: np.ndarray) -> np.ndarray:
    centered_reference = reference - np.mean(reference)
    reference_energy = float(np.sum(np.square(centered_reference)))
    if reference_energy <= 0:
        return np.array([], dtype=np.float64)

    correlation = signal.fftconvolve(
        search_audio,
        centered_reference[::-1],
        mode="valid",
    )
    ones = np.ones(centered_reference.size, dtype=np.float64)
    window_sum = signal.fftconvolve(search_audio, ones, mode="valid")
    window_square_sum = signal.fftconvolve(
        np.square(search_audio),
        ones,
        mode="valid",
    )
    window_energy = window_square_sum - np.square(window_sum) / centered_reference.size
    denominator = np.sqrt(reference_energy * np.maximum(window_energy, 1e-12))
    return correlation / denominator
